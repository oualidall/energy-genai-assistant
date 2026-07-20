"""Canonical schema of the RTE energy tables served to the assistant.

This module is the single source of truth for:
  - ``load_bigquery`` (to create the BigQuery tables),
  - the text-to-SQL agent (``render_schema_prompt`` feeds the LLM the schema),
  - the tests and the golden-questions eval set.

The tables mirror the dbt *mart* models of the upstream `rte-pipeline` project
(https://github.com/oualidall/rte-pipeline), re-materialised in BigQuery.

Canonical column types are the small set we actually use; ``load_bigquery`` maps
them to BigQuery Standard-SQL types. Keeping this module free of any GCP import
means it can be imported (and tested) without credentials.
"""

from __future__ import annotations

from dataclasses import dataclass

# Canonical types understood by the loader. Kept intentionally tiny.
CANONICAL_TYPES = {"DATE", "FLOAT", "INT", "STRING"}


@dataclass(frozen=True)
class Column:
    name: str
    type: str  # one of CANONICAL_TYPES
    description: str


@dataclass(frozen=True)
class Table:
    name: str
    description: str
    columns: tuple[Column, ...]

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


CONSOMMATION = Table(
    name="consommation_journaliere",
    description="Indicateurs journaliers de consommation électrique nationale (France).",
    columns=(
        Column("date", "DATE", "Jour (fuseau Europe/Paris). Clé unique."),
        Column("total_mwh", "FLOAT", "Énergie consommée dans la journée, en MWh."),
        Column("moyenne_mw", "FLOAT", "Puissance moyenne appelée sur la journée, en MW."),
        Column("pic_mw", "FLOAT", "Puissance maximale (pic) atteinte dans la journée, en MW."),
        Column("creux_mw", "FLOAT", "Puissance minimale (creux) de la journée, en MW."),
        Column("nb_pics", "INT", "Nombre de pas de 15 min classés en heure de pointe."),
    ),
)

MIX = Table(
    name="mix_energetique_hebdomadaire",
    description="Répartition hebdomadaire de la production d'électricité par filière.",
    columns=(
        Column("semaine", "DATE", "Lundi de la semaine ISO."),
        Column(
            "filiere",
            "STRING",
            "Filière de production (valeurs API RTE en majuscules) : "
            "NUCLEAR, SOLAR, WIND_ONSHORE, WIND_OFFSHORE, FOSSIL_GAS, FOSSIL_HARD_COAL, "
            "FOSSIL_OIL, HYDRO_PUMPED_STORAGE, HYDRO_RUN_OF_RIVER_AND_POUNDAGE, "
            "HYDRO_WATER_RESERVOIR, BIOMASS, WASTE.",
        ),
        Column("production_mwh", "FLOAT", "Production de la filière sur la semaine, en MWh."),
        Column("part_pct", "FLOAT", "Part de la filière dans le mix de la semaine, en %."),
    ),
)

ECHANGES = Table(
    name="solde_echanges_journalier",
    description="Vue journalière des imports, exports et du solde net d'électricité (France).",
    columns=(
        Column("date", "DATE", "Jour (fuseau Europe/Paris). Clé unique."),
        Column("export_mwh", "FLOAT", "Électricité exportée depuis la France, en MWh."),
        Column("import_mwh", "FLOAT", "Électricité importée vers la France, en MWh."),
        Column(
            "solde_mwh",
            "FLOAT",
            "Solde net = export - import, en MWh. Positif = la France est exportatrice nette.",
        ),
    ),
)

TABLES: tuple[Table, ...] = (CONSOMMATION, MIX, ECHANGES)


def table_names() -> list[str]:
    return [t.name for t in TABLES]


def get_table(name: str) -> Table:
    for t in TABLES:
        if t.name == name:
            return t
    raise KeyError(f"unknown table: {name!r}. Known tables: {table_names()}")


def render_schema_prompt() -> str:
    """Render the schema as a compact text block to feed the text-to-SQL LLM."""
    lines: list[str] = []
    for t in TABLES:
        lines.append(f"Table {t.name} — {t.description}")
        for c in t.columns:
            lines.append(f"  - {c.name} ({c.type}): {c.description}")
        lines.append("")
    return "\n".join(lines).strip()


if __name__ == "__main__":
    print(render_schema_prompt())
