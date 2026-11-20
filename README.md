# Assistant documentaire CNIL / ANSSI (RAG)

Assistant de questions-réponses sur trois guides publics de sécurité informatique. Il recherche les passages pertinents dans un corpus préparé à partir des guides, puis un modèle de langage local répond uniquement à partir de ces passages, en citant les extraits utilisés. Si les passages ne permettent pas de répondre, l'assistant refuse.

LLM (`qwen2.5:3b`) et embeddings (`bge-m3`) via Ollama, index dans PostgreSQL avec pgvector.

## Installation

Prérequis : Python 3.10+, Docker, [Ollama](https://ollama.com).

```bash
ollama pull bge-m3
ollama pull qwen2.5:3b
docker compose up -d
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Utilisation

Le corpus préparé (`corpus/`) est versionné. Pour le reconstruire, placer les trois guides dans `data/` sous les noms `cnil_securite.pdf`, `anssi_hygiene.pdf` et `anssi_ia_generative.pdf`.

```bash
python prepare.py        # PDF -> corpus/documents.json
python chunk.py          # documents -> corpus/chunks.json
python ingest.py         # indexation dans PostgreSQL

python search.py "Combien de temps garder les logs ?"   # top-k chunks et scores
python rag.py "Combien de temps garder les logs ?"      # réponse, sources, extraits récupérés
streamlit run app.py                                    # interface web

python evaluate.py --recherche   # recherche seule, 3 modes
python evaluate.py               # recherche + réponses
python evaluate.py --bilan       # synthèse des jugements faits à la main
```

Les paramètres sont dans `config.py`.

## Données

| Guide | Pages | Documents |
|---|---|---|
| [CNIL, Guide pratique RGPD – Sécurité des données personnelles](https://www.cnil.fr/fr/guide-de-la-securite-des-donnees-personnelles-nouvelle-edition-2024) (éd. 2024, mise à jour 2026) | 64 | 25 (une fiche = un document) |
| ANSSI, Guide d'hygiène informatique – 42 mesures (v2.0, 2017), [cyber.gouv.fr](https://cyber.gouv.fr) | 72 | 11 (introduction + 10 chapitres) |
| [ANSSI, Recommandations de sécurité pour un système d'IA générative](https://cyber.gouv.fr/sites/default/files/document/Recommandations_de_s%C3%A9curit%C3%A9_pour_un_syst%C3%A8me_d_IA_g%C3%A9n%C3%A9rative.pdf) (2024) | 38 | 14 (une partie du sommaire = un document) |

**Nettoyage** (`prepare.py`). Le texte est lu ligne par ligne avec sa taille de police, pour :
- repérer les titres (fiches, chapitres, mesures, recommandations R1-R35) ;
- retirer en-têtes, pieds de page, numéros de page, notes de bas de page, sommaires, bibliographies et récapitulatifs en double (check-list CNIL, outil de suivi et liste des recommandations ANSSI) ;
- recoller les mots coupés en fin de ligne et remettre les espaces manquants du PDF IA de l'ANSSI (l'extraction brute donnait « Cedocumentrédigéparl'ANSSI… ») ;
- garder la mention « Niveau standard / Niveau renforcé » des mesures ANSSI.

Les tableaux et figures ne sont pas repris.

`corpus/documents.json` : 50 documents de 183 à 2 792 mots, avec `document_id` (`CNIL_04`, `HYG_03`, `IAG_08`...), `title`, `source` (guide et pages), `url`, `pages`, `text` et `sections`.

**Chunks** (`chunk.py`). Le découpage suit les sections des documents (parties d'une fiche CNIL, mesures, recommandations) :
1. une section de moins de 350 mots n'est pas coupée ;
2. les petites sections voisines sont regroupées jusqu'à 350 mots ;
3. une section plus longue est coupée entre deux paragraphes, avec 50 mots de chevauchement ;
4. un chunk de moins de 100 mots est fusionné avec son voisin.

`corpus/chunks.json` : 138 chunks de 102 à 440 mots (médiane 241), avec `chunk_id` (`HYG_03_C02`), `document_id`, `title`, `source`, `page` et `sections`.

## Recherche

`retrieve(query, k, mode)` dans `search.py` renvoie les k chunks les plus pertinents avec leur score et leurs métadonnées :
- **vectorielle** : similarité cosinus des embeddings bge-m3, index HNSW ;
- **mots-clés** : recherche plein texte PostgreSQL en français, mots de la question reliés par OU ;
- **hybride** (par défaut) : fusion des deux par Reciprocal Rank Fusion.

Le titre du document est indexé avec le texte. k = 4.

## Génération

Les 4 chunks sont placés dans le prompt avec leur identifiant, titre, section et source. Le modèle doit répondre uniquement à partir des extraits, en 5 points maximum terminés par l'identifiant de l'extrait utilisé, ou répondre « Je ne trouve pas cette information dans les documents. ». Les identifiants cités qui ne font pas partie des extraits fournis sont signalés. Pas de seuil de score.

## Évaluation

33 questions dans `evaluation/questions.json` :

| Catégorie | Nombre |
|---|---|
| directe | 15 |
| reformulée | 7 |
| hors corpus | 5 |
| difficile (ambiguë, sources divergentes, fausse prémisse, synthèse de deux guides) | 6 |

**Recherche** (bon chunk parmi les 4 premiers) :

| | hybride | vectorielle | mots-clés |
|---|---|---|---|
| directe | 13/15 | 14/15 | 12/15 |
| reformulée | 6/7 | 7/7 | 5/7 |
| difficile | 5/6 | 4/6 | 5/6 |
| total | 24/28 | 25/28 | 22/28 |
| MRR | 0,75 | 0,76 | 0,59 |

**Réponses** (mode hybride) :
- bon chunk récupéré : 22/25 questions avec réponse attendue ;
- questions hors corpus refusées : 5/5 ;
- refus alors qu'une réponse était attendue : 3/25 ;
- réponses citant au moins une source valide : 23/23 ;
- temps moyen : 35 s par réponse.

Le détail est dans `evaluation/resultats.csv` et `evaluation/resultats.json`. La première version du projet (PDF découpés sans préparation) est dans `evaluation/v1_pdf_brut/`.

## Fichiers

```
prepare.py      PDF -> documents nettoyés
chunk.py        documents -> chunks
ingest.py       indexation (pgvector + plein texte)
search.py       retrieve()
rag.py          prompt, génération, vérification des citations
llm.py          appel au LLM
app.py          interface Streamlit
evaluate.py     évaluation
config.py       paramètres
```
