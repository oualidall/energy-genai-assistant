"""Small domain knowledge base + a lightweight semantic retriever.

The text-to-SQL model knows the *schema*, but not the *domain*: what the filière
codes mean, the units, the sign convention of the balance, the timezone. This
module holds that knowledge as short documents and retrieves the most relevant
ones for a question (cosine similarity over embeddings).

Embeddings are injected, so tests run with a deterministic fake and no API call.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

# Domain notes surfaced to the agent alongside the schema.
KNOWLEDGE: tuple[str, ...] = (
    "La table consommation_journaliere donne, par jour, la consommation "
    "électrique nationale française : total_mwh (énergie du jour en MWh), "
    "moyenne_mw / pic_mw / creux_mw (puissance en MW).",
    "La table mix_energetique_hebdomadaire donne, par semaine et par filière, "
    "la production (production_mwh) et sa part dans le mix (part_pct).",
    "La table solde_echanges_journalier donne, par jour, export_mwh, import_mwh "
    "et solde_mwh. solde_mwh = export - import : positif = la France exporte plus "
    "qu'elle n'importe (exportatrice nette), négatif = importatrice nette.",
    "Les codes de filière (colonne filiere) sont en majuscules, issus de l'API RTE : "
    "NUCLEAR = nucléaire, SOLAR = solaire, WIND_ONSHORE = éolien terrestre, "
    "WIND_OFFSHORE = éolien en mer.",
    "Autres filières : FOSSIL_GAS = gaz, FOSSIL_HARD_COAL = charbon, FOSSIL_OIL = fioul, "
    "BIOMASS = biomasse, WASTE = déchets.",
    "Filières hydrauliques : HYDRO_WATER_RESERVOIR = barrage/lac, "
    "HYDRO_RUN_OF_RIVER_AND_POUNDAGE = fil de l'eau, HYDRO_PUMPED_STORAGE = "
    "station de pompage-turbinage (STEP).",
    "Unités : l'énergie est en MWh (mégawattheure), la puissance en MW (mégawatt). "
    "1 GWh = 1000 MWh. Les dates sont dans le fuseau Europe/Paris ; semaine = lundi ISO.",
)


class Embeddings(Protocol):
    """Minimal embeddings interface (matches langchain embedding classes)."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def _cosine(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    matrix_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    vector_norm = vector / (np.linalg.norm(vector) + 1e-9)
    return matrix_norm @ vector_norm


class Retriever:
    """Cosine-similarity retriever over a fixed set of documents."""

    def __init__(self, embeddings: Embeddings, documents: tuple[str, ...] = KNOWLEDGE) -> None:
        self.documents = list(documents)
        self.embeddings = embeddings
        self._matrix = np.array(embeddings.embed_documents(self.documents), dtype=float)

    def retrieve(self, query: str, k: int = 3) -> list[str]:
        """Return the ``k`` documents most relevant to ``query``."""
        q = np.array(self.embeddings.embed_query(query), dtype=float)
        scores = _cosine(self._matrix, q)
        top = np.argsort(scores)[::-1][:k]
        return [self.documents[i] for i in top]


def get_embeddings() -> Embeddings:
    """Build the Gemini embeddings model."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")


def build_default_retriever(embeddings: Embeddings | None = None) -> Retriever:
    return Retriever(embeddings or get_embeddings())


if __name__ == "__main__":
    r = build_default_retriever()
    for doc in r.retrieve("c'est quoi le solde d'échanges négatif ?"):
        print("-", doc)
