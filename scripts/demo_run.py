"""Record real agent events. Importing this module never starts a network call."""
from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.demo_guardrail import ROOT, sync_readme
from src.agent.graph import AgentExecutionAborted, EnergyAgent
from src.config import settings
from src.rag.knowledge import KNOWLEDGE, Retriever
from src.sql.text_to_sql import is_safe_sql, strip_fences

QUESTIONS = (
    "Quelle a été la consommation totale le 15 juillet 2026 ?",
    "Quelles sont les 3 filières les plus productrices au total ?",
    "Que signifie le solde des échanges ?",
    "Supprime les données du 15 juillet 2026.",
)
MAX_CALLS = 10


class GeminiTransport:
    """One HTTP attempt per call; no SDK retries or hidden embedding calls."""

    def __init__(self, key: str, model: str):
        if not key or not re.fullmatch(r"gemini-[a-zA-Z0-9.-]+", model):
            raise ValueError("A key and an explicit Gemini model are required")
        self.key, self.model = key, model

    def __call__(self, prompt: str) -> dict:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 1024,
                                 "thinkingConfig": {"thinkingBudget": 0}},
        }
        request = Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.key},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as exc:
            raise AgentExecutionAborted(f"Gemini HTTP {exc.code}; no retry") from None
        except URLError:
            raise AgentExecutionAborted("Gemini network failure; usage unknown, no retry") from None


class MeteredLLM:
    """Inject a callable returning the native generateContent response."""

    def __init__(self, transport):
        self.transport = transport
        self.calls: list[dict] = []
        self.last_sql: str | None = None

    def invoke(self, prompt: str):
        if len(self.calls) >= MAX_CALLS:
            raise AgentExecutionAborted("Limite de 10 appels atteinte : appel suivant bloqué.")
        if len(prompt.encode("utf-8")) > 24000:
            raise AgentExecutionAborted("Prompt supérieur à 24000 octets : appel bloqué.")
        record = {"call": len(self.calls) + 1, "usageMetadata": None}
        self.calls.append(record)  # Reserve BEFORE touching the transport, including failures.
        try:
            result = self.transport(prompt)
        except Exception as exc:
            record["error"] = type(exc).__name__
            raise AgentExecutionAborted(f"Transport interrompu ({type(exc).__name__}).") from exc
        record["usageMetadata"] = result.get("usageMetadata")
        candidates = result.get("candidates", [])
        text = "".join(
            part.get("text", "") for part in
            (candidates[0].get("content", {}).get("parts", []) if candidates else [])
            if not part.get("thought", False)
        )
        if "expert SQL BigQuery" in prompt:
            self.last_sql = strip_fences(text)
        if not text:
            raise AgentExecutionAborted("Gemini n'a renvoyé aucun texte ; arrêt.")
        return SimpleNamespace(content=text)


class LocalEmbeddings:
    """Bag-of-words embeddings: disclosed local demo retrieval, no Gemini embeddings."""

    def __init__(self):
        self.vocabulary = sorted(set(re.findall(r"\w+", " ".join(KNOWLEDGE).lower())))

    def embed_query(self, text):
        words = re.findall(r"\w+", text.lower())
        return [float(words.count(word)) for word in self.vocabulary]

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]


class ReadOnlyBigQuery:
    def __init__(self, client):
        self.client = client
        self.calls = 0

    def query(self, sql):
        from google.cloud import bigquery

        if not is_safe_sql(sql):
            raise ValueError(f"refused unsafe or non-SELECT SQL: {sql!r}")
        self.calls += 1
        return self.client.query(
            sql,
            job_config=bigquery.QueryJobConfig(maximum_bytes_billed=10000000),
        )


def block(text: str, language: str = "") -> str:
    fence = "`" * max(3, max((len(s) for s in re.findall(r"`+", text)), default=0) + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def render(records, calls, metadata, stopped):
    lines = ["### Transcript observé", "", block(json.dumps(metadata, ensure_ascii=False, indent=2), "json")]
    for record in records:
        lines += ["", "#### " + record["question"], "",
                  "Route observée : " + record.get("route", "non obtenue"),
                  "", "SQL généré :", block(record.get("sql_candidate") or "(aucun)", "sql"),
                  "", "Lignes renvoyées :", block(json.dumps(record.get("rows", []), ensure_ascii=False, default=str, indent=2), "json")]
        if record.get("error"):
            lines += ["", "Erreur observée (garde-fou ou outil) :", block(record["error"])]
        lines += ["", "Réponse finale :", block(record.get("answer") or "(non obtenue ; exécution interrompue)")]
    if stopped:
        lines += ["", "Exécution interrompue :", block(stopped)]
    totals = [c["usageMetadata"].get("totalTokenCount") if c["usageMetadata"] else None for c in calls]
    complete = all(isinstance(n, int) for n in totals)
    lines += ["", f"Appels Gemini tentés : {len(calls)}.",
              f"Jetons totaux rapportés par l'API : {sum(totals) if complete else 'inconnus (métadonnées manquantes ; aucun zéro supposé)'}.",
              "", "Détail par appel (usageMetadata brut) :", block(json.dumps(calls, ensure_ascii=False, indent=2), "json"), ""]
    return "\n".join(lines)


def run_demo(transport, *, bq_client, retriever, output: Path, metadata: dict, readme: Path | None = None):
    llm = MeteredLLM(transport)
    agent = EnergyAgent(llm=llm, bq_client=bq_client, retriever=retriever)
    records, stopped = [], None
    for question in QUESTIONS:
        record = {"question": question}
        records.append(record)
        llm.last_sql = None
        try:
            for event in agent.graph.stream({"question": question}, stream_mode="updates"):
                for update in event.values():
                    record.update(update)
        except AgentExecutionAborted as exc:
            stopped = str(exc)
        record["sql_candidate"] = llm.last_sql
        # Save completed AND partial observations after every question.
        content = render(records, llm.calls, metadata, stopped)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        if readme is not None:
            sync_readme(readme, "conversation", content)
        if stopped:
            break
    print(content)
    return {"records": records, "calls": llm.calls, "stopped": stopped}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-free-tier", action="store_true",
                        help="Confirm the key belongs to a project WITHOUT paid billing enabled")
    parser.add_argument("--model", default="gemini-2.5-flash-lite")
    args = parser.parse_args()
    if not args.run_free_tier:
        parser.error("No call made. Explicit --run-free-tier confirmation is required.")
    if args.model != "gemini-2.5-flash-lite":
        parser.error("This demo only configures gemini-2.5-flash-lite; no paid fallback.")
    transport = GeminiTransport(settings.google_api_key, args.model)
    from google.cloud import bigquery

    client = ReadOnlyBigQuery(bigquery.Client(project=settings.gcp_project_id))
    result = run_demo(
        transport, bq_client=client, retriever=Retriever(LocalEmbeddings()),
        output=ROOT / "docs/demo/transcript.md", readme=ROOT / "README.md",
        metadata={"executed_at": datetime.now(UTC).isoformat(), "model": args.model,
                  "temperature": 0, "max_output_tokens": 1024, "max_calls": MAX_CALLS,
                  "data_source": f"BigQuery: {settings.gcp_project_id}.{settings.bigquery_dataset}",
                  "retrieval": "local bag-of-words over KNOWLEDGE; no embedding API",
                  "billing": "free tier asserted by operator; not verifiable from API key"},
    )
    if result["stopped"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
