# RAG sur les guides CNIL / ANSSI

Assistant de questions-réponses sur trois guides publics de la CNIL et de l'ANSSI. Il répond uniquement à partir des documents, cite ses sources (document et page) et refuse de répondre quand l'information n'y est pas.

Tout tourne en local : LLM et embeddings via Ollama, stockage dans PostgreSQL avec pgvector.

<!-- Capture d'écran de l'interface : docs/interface.png -->

## Résultats

Évaluation sur 27 questions écrites à la main (`eval_questions.json`) : 15 questions directes, 7 reformulées (sans reprendre les mots du guide) et 5 questions hors corpus. Modèle : `qwen2.5:3b`, 4 extraits envoyés au LLM.

| Mesure | Résultat |
|---|---|
| Recherche : bon passage dans les 4 extraits (mode hybride) | 17/22 (directes 12/15, reformulées 5/7), MRR 0,66 |
| Réponse complète (tous les faits attendus) | 15/22 |
| Réponse partielle | 2/22 |
| Réponse sans le fait attendu | 4/22 |
| Refus à tort | 1/22 |
| Réponses avec au moins une citation | 21/21 |
| Questions hors corpus correctement refusées | 5/5 |
| Temps moyen par réponse (en local sur MacBook) | ~31 s |

Le détail de chaque réponse est dans `eval_resultats.json`.

**Ce qu'on en retient**
- Le système ne répond jamais aux questions hors corpus : la consigne de refus est bien suivie.
- Une partie des erreurs vient de la génération, pas de la recherche. Pour la longueur minimale des mots de passe, le bon passage est récupéré (rang 1 ou 2), mais le modèle de 3B paramètres répond « 80 bits d'entropie » au lieu de « 12 caractères ».
- Les questions reformulées sont plus difficiles pour la recherche (5/7 contre 12/15), d'où l'intérêt de la recherche hybride.

## Fonctionnement

1. **Indexation** (`ingest.py`) : les PDF sont découpés en paragraphes, regroupés en chunks d'environ 350 mots avec 50 mots de chevauchement (un paragraphe n'est jamais coupé), puis vectorisés avec bge-m3.
2. **Recherche** (`search.py`) : recherche vectorielle (similarité cosinus, index HNSW), recherche plein texte PostgreSQL (analyse en français), ou les deux fusionnées par Reciprocal Rank Fusion.
3. **Génération** (`rag.py`, `llm.py`) : les meilleurs chunks sont envoyés au LLM avec leur numéro. Il doit répondre uniquement à partir de ceux-ci et citer ses sources sous la forme `[n]`. Les numéros qui ne correspondent à aucun extrait sont ignorés.
4. **Évaluation** (`evaluate.py`) : mesure séparément la recherche (pour les trois modes), le contenu des réponses et les refus.

## Installation

Prérequis : Python 3.10+, Docker, [Ollama](https://ollama.com).

```bash
ollama pull bge-m3
ollama pull qwen2.5:3b

docker compose up -d
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Utilisation

Placer les PDF dans `data/` (non versionnés), puis :

```bash
python ingest.py                                        # indexation
python rag.py "Comment sécuriser les mots de passe ?"   # question en ligne de commande
streamlit run app.py                                    # interface web
python evaluate.py                                      # évaluation complète (15 à 30 min)
python evaluate.py --sans-generation                    # recherche seulement (1 à 2 min)
python check.py "ma question"                           # contenu de la base et 5 chunks les plus proches
```

Le modèle et les paramètres (taille des chunks, nombre d'extraits) se règlent dans `config.py`. Pour changer de modèle ou de fournisseur, seul `llm.py` est à modifier.

## Limites et pistes

- [ ] Comparer le modèle local avec un modèle via API sur le même jeu de test.
- [ ] Vérifier que chaque extrait cité soutient bien la phrase qui le cite : aujourd'hui, seule l'existence du numéro est vérifiée.
- [ ] Accepter plusieurs documents sources valides par question dans l'évaluation : certaines réponses (Wi-Fi par exemple) sont dans les deux guides.
- L'évaluation des réponses repose sur la présence de mots-clés : elle ne juge pas la qualité de la formulation.

## Corpus

- CNIL, *Guide de la sécurité des données personnelles*
- ANSSI, *Guide d'hygiène informatique*
- ANSSI, *Recommandations de sécurité pour un système d'IA générative*
