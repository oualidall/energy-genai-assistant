| Requête | Décision | Règle appliquée |
|---|---|---|
| <code>SELECT total_mwh FROM consommation_journaliere</code> | acceptée | SELECT/WITH prefix, no internal semicolon or forbidden keyword |
| <code>WITH totals AS (SELECT SUM(total_mwh) AS total FROM consommation_journaliere) SELECT total FROM totals</code> | acceptée | SELECT/WITH prefix, no internal semicolon or forbidden keyword |
| <code>DELETE FROM consommation_journaliere</code> | refusée | statement must start with SELECT or WITH |
| <code>DROP TABLE consommation_journaliere</code> | refusée | statement must start with SELECT or WITH |
| <code>SELECT 1; SELECT 2</code> | refusée | multiple statements (internal semicolon) |
| <code>SELECT total_mwh INTO backup FROM consommation_journaliere</code> | refusée | forbidden keyword(s): INTO |
| <code>/* harmless SELECT */ DELETE FROM consommation_journaliere</code> | refusée | statement must start with SELECT or WITH |
| <code>(chaîne vide)</code> | refusée | empty SQL |
