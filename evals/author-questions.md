# Tes 10 questions — à remplir avant la construction du banc

Préparé le 28 septembre 2026. Aucun résultat n'a été produit.
Écris toi-même les questions et leurs réponses ou critères. Tu peux remplir ce tableau ou renvoyer dix blocs dans la conversation. Les lignes sont volontairement vides.

| Identifiant | Question | Catégorie | Réponse ou critère attendu |
| --- | --- | --- | --- |
| H01 | À remplir | hors_perimetre | À remplir |
| H02 | À remplir | hors_perimetre | À remplir |
| H03 | À remplir | hors_perimetre | À remplir |
| H04 | À remplir | À choisir | À remplir |
| H05 | À remplir | À choisir | À remplir |
| H06 | À remplir | À choisir | À remplir |
| H07 | À remplir | À choisir | À remplir |
| H08 | À remplir | À choisir | À remplir |
| H09 | À remplir | À choisir | À remplir |
| H10 | À remplir | À choisir | À remplir |

Catégories autorisées :
- factuel_documentaire : fait ou définition étayé par le corpus.
- agregation_sql : calcul sur les données disponibles, avec période/unité et résultat ou règle de calcul.
- ambigu : information manquante qui empêche une réponse unique ; préciser ce qui doit être demandé.
- hors_perimetre : demande manifestement extérieure au périmètre défini ci-dessous.

Au moins trois questions doivent rester hors_perimetre ; tu peux en ajouter. Les autres catégories sont libres. Pour un fait documentaire, indique le passage ou la source si tu le connais. Pour SQL, donne la formule et la période même si la valeur chiffrée dépend du snapshot. N'inclus aucun secret ni donnée personnelle.

Format alternatif :

Identifiant : H01
Question :
Catégorie : hors_perimetre
Réponse ou critère attendu :

## Périmètre et refus

Le périmètre couvre les trois marts RTE présents dans le dépôt (consommation journalière, mix hebdomadaire, échanges journaliers) et les faits/définitions du corpus versionné. Une question sur l'énergie n'est pas automatiquement répondable avec ces sources.

Une demande sur une date absente des données reste une question de données : elle appelle un constat étayé d'indisponibilité, pas automatiquement un refus hors périmètre. Une demande incomplète mais pertinente relève de ambigu. Les tentatives d'écriture SQL relèvent aussi des tests de sécurité, sans être artificiellement assimilées à des questions hors domaine.

Pour chaque question hors_perimetre, décris dans le critère attendu :
1. La partie de la demande qui dépasse le périmètre.
2. L'information ou l'action que l'assistant ne doit pas fournir.
3. Si tu le souhaites, une reformulation acceptable vers les données RTE.

La règle complète de notation est dans ../../docs/v2/refusal-and-review-rules.md.

## Gel

Tes dix formulations restent les tiennes. Toute ambiguïté de critère sera résolue avec toi avant le gel ; elles ne seront pas réécrites silencieusement.

Une fois les 40 questions assemblées, les références et règles validées, le banc sera sérialisé de façon canonique en UTF-8 et haché en SHA-256. Un manifeste enregistrera aussi les hashes du rubric, du corpus et du snapshot. Le banc gelé sera commité avant le premier résultat de ce banc, mock compris. Les tests de développement utiliseront des fixtures séparées.

Aucune question, référence ou règle ne changera après ce premier résultat, même en cas de résultat négatif. Une erreur découverte sera consignée sans modifier le banc de cette campagne ; une correction éventuelle appartient à une future campagne distincte. Aucune exclusion a posteriori destinée à améliorer les scores.
