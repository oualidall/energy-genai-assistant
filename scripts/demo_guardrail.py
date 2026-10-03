"""Generate the guardrail demonstration without credentials or API calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.sql.text_to_sql import is_safe_sql, sql_safety_rule

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = (
    "SELECT total_mwh FROM consommation_journaliere",
    "WITH totals AS (SELECT SUM(total_mwh) AS total FROM consommation_journaliere) SELECT total FROM totals",
    "DELETE FROM consommation_journaliere",
    "DROP TABLE consommation_journaliere",
    "SELECT 1; SELECT 2",
    "SELECT total_mwh INTO backup FROM consommation_journaliere",
    "/* harmless SELECT */ DELETE FROM consommation_journaliere",
    "",
)


def sync_readme(readme: Path, name: str, content: str) -> None:
    text = readme.read_text(encoding="utf-8")
    start, end = f"<!-- demo:{name}:start -->", f"<!-- demo:{name}:end -->"
    if start not in text or end not in text:
        raise ValueError(f"Missing README markers for {name}")
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    readme.write_text(before + start + "\n" + content.rstrip() + "\n" + end + after, encoding="utf-8")


def render() -> str:
    lines = ["| Requête | Décision | Règle appliquée |", "|---|---|---|"]
    for sql in CANDIDATES:
        accepted = is_safe_sql(sql)
        explained, rule = sql_safety_rule(sql)
        if explained != accepted:
            raise RuntimeError("Explanation differs from the real guard decision")
        query = sql.replace("|", "&#124;") or "(chaîne vide)"
        decision = "acceptée" if accepted else "refusée"
        lines.append(f"| <code>{query}</code> | {decision} | {rule} |")
    return "\n".join(lines) + "\n"


def generate(output: Path) -> str:
    content = render()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/demo/guardrail.md")
    parser.add_argument("--no-readme", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print exact generated text for CI capture")
    args = parser.parse_args()
    content = generate(args.output)
    if not args.no_readme:
        sync_readme(ROOT / "README.md", "guardrail", content)
    print("DEMO_GUARDRAIL_JSON=" + json.dumps(content, ensure_ascii=True) if args.json else content)


if __name__ == "__main__":
    main()
