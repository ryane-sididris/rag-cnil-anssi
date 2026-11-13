# Assistant documentaire CNIL / ANSSI (RAG)

Assistant de questions-réponses sur trois guides publics de sécurité informatique. Il recherche les passages pertinents dans un corpus préparé à partir des guides, puis un modèle de langage local répond **uniquement à partir de ces passages**, en citant les extraits utilisés. Si les passages ne permettent pas de répondre, l'assistant refuse explicitement.

Tout tourne en local : LLM (`qwen2.5:3b`) et embeddings (`bge-m3`) via Ollama, index dans PostgreSQL avec pgvector.

<!-- Capture d'écran de l'interface : docs/interface.png -->

## Démarrage rapide

Prérequis : Python 3.10+, Docker, [Ollama](https://ollama.com).

```bash
ollama pull bge-m3
ollama pull qwen2.5:3b
docker compose up -d
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Le corpus préparé (`corpus/`) est versionné : on peut indexer directement. Pour le reconstruire depuis les PDF, placer les trois guides (liens plus bas) dans `data/` sous les noms `cnil_securite.pdf`, `anssi_hygiene.pdf` et `anssi_ia_generative.pdf`.

```bash
python prepare.py        # PDF -> corpus/documents.json   (50 documents nettoyés)
python chunk.py          # documents -> corpus/chunks.json (138 chunks)
python ingest.py         # vectorisation et indexation dans PostgreSQL

python search.py "Combien de temps garder les logs ?"   # recherche seule : top-k chunks et scores
python rag.py "Combien de temps garder les logs ?"      # réponse, sources, extraits récupérés
streamlit run app.py                                    # interface web

python evaluate.py --recherche   # évaluation de la recherche, 3 méthodes comparées
python evaluate.py               # évaluation complète (recherche + réponses)
python evaluate.py --bilan       # synthèse des jugements faits à la main
```

Tous les paramètres (modèles, taille des chunks, k) sont dans `config.py`.

## 1. Données

**Sources.** Trois guides publics, factuels et orientés « bonnes pratiques » : un utilisateur peut leur poser des questions précises (durées, seuils, procédures), et la plupart des réponses ne sont pas des connaissances générales d'un LLM.

| Guide | Pages | Documents |
|---|---|---|
| [CNIL, Guide pratique RGPD – Sécurité des données personnelles](https://www.cnil.fr/fr/guide-de-la-securite-des-donnees-personnelles-nouvelle-edition-2024) (éd. 2024, mise à jour 2026) | 64 | 25 (une fiche = un document) |
| ANSSI, Guide d'hygiène informatique – 42 mesures (v2.0, 2017), [cyber.gouv.fr](https://cyber.gouv.fr) | 72 | 11 (introduction + 10 chapitres) |
| [ANSSI, Recommandations de sécurité pour un système d'IA générative](https://cyber.gouv.fr/sites/default/files/document/Recommandations_de_s%C3%A9curit%C3%A9_pour_un_syst%C3%A8me_d_IA_g%C3%A9n%C3%A9rative.pdf) (2024) | 38 | 14 (une partie du sommaire = un document) |

**Nettoyage** (`prepare.py`). Le texte est lu ligne par ligne avec sa taille de police, ce qui permet de :
- reconnaître les titres (fiches, chapitres, mesures, recommandations R1-R35) ;
- retirer les en-têtes et pieds de page répétés, les numéros de page, les notes de bas de page, les appels de note en exposant, les pages de sommaire, la bibliographie et les récapitulatifs qui dupliquent le contenu (check-list CNIL, outil de suivi et liste des recommandations ANSSI) ;
- réparer les mots coupés en fin de ligne et les **espaces manquants** du PDF de l'ANSSI sur l'IA : l'extraction brute donnait des lignes comme « Cedocumentrédigéparl'ANSSI… », qui ne pouvaient être retrouvées ni par mots-clés ni par embeddings ;
- conserver la mention « Niveau standard / Niveau renforcé » des mesures ANSSI.

Les tableaux et figures (ex. : tableau d'analyse de risques de la fiche CNIL 20) ne sont pas repris. Un contrôle de quasi-doublons (similarité de Jaccard) est fait à la fin.

**Format.** `corpus/documents.json` : 50 documents de 183 à 2 792 mots, chacun avec `document_id` (ex. `CNIL_04`, `HYG_03`, `IAG_08`), `title`, `source` (guide et pages du PDF), `url`, `pages`, `text` et `sections` (titre, page et texte de chaque sous-partie).

**Chunks** (`chunk.py`). Le découpage suit la structure des documents plutôt qu'une longueur fixe :
1. une section (partie d'une fiche CNIL, mesure ANSSI, recommandation) qui tient dans 350 mots n'est jamais coupée ;
2. les petites sections voisines d'un même document sont regroupées jusqu'à 350 mots ;
3. une section plus longue est coupée entre deux paragraphes, avec 50 mots de chevauchement, et chaque morceau garde le titre de sa section ;
4. un chunk de moins de 100 mots (introduction d'une fiche) est fusionné avec son voisin.

Résultat : 138 chunks de 102 à 440 mots (médiane 241). `corpus/chunks.json` garde pour chaque chunk `chunk_id` (ex. `HYG_03_C02`), `document_id`, `title`, `source`, `page` et `sections`.

## 2. Recherche

`search.py` fournit `retrieve(query, k, mode)`, qui renvoie les k chunks les plus pertinents avec leur score et leurs métadonnées. Trois méthodes :
- **vectorielle** : similarité cosinus entre embeddings bge-m3 (multilingue), index HNSW ;
- **mots-clés** : recherche plein texte PostgreSQL (racinisation française, mots vides retirés), mots de la question reliés par OU ;
- **hybride** (par défaut) : fusion des deux listes par Reciprocal Rank Fusion (on fusionne les rangs, car les scores des deux méthodes ne sont pas comparables).

Le titre du document est indexé avec le texte : ajouté au texte vectorisé, et avec un poids plus fort dans l'index plein texte. k = 4. Les scores servent seulement à classer les chunks d'une même recherche.

## 3. Génération

`rag.py` place les 4 chunks dans le prompt, chacun avec son identifiant, son titre, sa section et sa source. Le prompt système interdit d'utiliser les connaissances générales du modèle. Les consignes de format sont répétées après la question, car les petits modèles suivent mieux ce qui précède immédiatement la réponse : 5 points maximum, chacun terminé par l'identifiant de l'extrait qui le justifie, ou la phrase de refus « Je ne trouve pas cette information dans les documents. ».

Après la génération, les identifiants cités sont vérifiés : ceux qui ne font pas partie des extraits fournis sont signalés comme citations invalides. Aucun seuil de score n'est utilisé pour refuser : le refus est décidé par le modèle à partir du contenu des extraits.

## 4. Évaluation

`evaluation/questions.json` contient 33 questions, écrites avant de lancer l'évaluation :

| Catégorie | Nombre | Rôle |
|---|---|---|
| directe | 15 | cas normal, vocabulaire proche du guide |
| reformulée | 7 | mots différents de ceux du guide (« logs », « wifi », « MFA ») |
| hors corpus | 5 | la réponse n'est pas dans les guides : refus attendu |
| difficile | 6 | question ambiguë, sources divergentes, fausse prémisse, raisonnement nécessaire, synthèse de deux guides |

Pour chaque question : documents attendus, expression qui doit figurer dans le bon chunk (`preuve`), et comportement attendu (réponse, refus ou réponse nuancée).

- `evaluation/recherche.csv` : rang du bon chunk pour chaque méthode de recherche.
- `evaluation/resultats.json` : extraits récupérés (texte complet), réponse et citations pour chaque question.
- `evaluation/resultats.csv` : tableau à compléter à la main : réponse correcte (oui / partiel / non), ancrée dans les extraits (oui / non), type d'échec (recherche / génération / ancrage / refus).

### Résultats

*À compléter après `python evaluate.py --recherche`, `python evaluate.py` et `python evaluate.py --bilan`.*

**Version précédente, pour comparaison** (`evaluation/v1_pdf_brut/`) : PDF découpés directement en blocs de 350 mots, sans préparation, 27 questions sans la catégorie « difficile ». Bon passage récupéré pour 17 questions sur 22, réponse complète pour 15 sur 22, 5 refus corrects sur 5 hors corpus, environ 31 s par réponse.

### Analyse des échecs

*À compléter avec un cas concret de chaque type : échec de recherche, de génération, d'ancrage et de refus (question, extraits récupérés, réponse, cause probable, correction possible).*

## Limites et pistes

*À compléter à partir des échecs observés.*

## Structure du dépôt

```
prepare.py      PDF -> documents nettoyés          corpus/documents.json
chunk.py        documents -> chunks                corpus/chunks.json
ingest.py       vectorisation et indexation        PostgreSQL (pgvector + plein texte)
search.py       retrieve() : recherche vectorielle, plein texte, hybride
rag.py          construction du prompt, génération, vérification des citations
llm.py          seul appel au LLM (changer de modèle ou de fournisseur ici)
app.py          interface Streamlit
evaluate.py     évaluation (recherche, réponses, bilan)
config.py       paramètres
```

<!-- À compléter : comment des outils d'IA ont été utilisés dans ce projet (demandé par le cours). -->
