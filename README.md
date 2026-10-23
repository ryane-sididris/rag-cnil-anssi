# RAG sur les guides CNIL / ANSSI

Assistant de questions-réponses sur des guides publics de la CNIL et de l'ANSSI. Tout tourne en local : LLM et embeddings via Ollama, stockage dans PostgreSQL avec pgvector.

## Avancement

- [x] Extraction des PDF, découpage en chunks, embeddings (bge-m3), stockage pgvector
- [x] Recherche hybride (vectorielle + plein texte, fusion RRF)
- [x] Génération avec citation des sources, interface Streamlit
- [ ] Évaluation sur un jeu de questions de test
- [ ] Comparaison du modèle local (Ollama) avec un modèle via API, sur le même jeu de test

## Fonctionnement

1. **Indexation** (`ingest.py`) : les PDF sont découpés en paragraphes, regroupés en chunks d'environ 350 mots avec 50 mots de chevauchement, puis vectorisés avec bge-m3.
2. **Recherche** (`search.py`) : recherche vectorielle (similarité cosinus), recherche plein texte PostgreSQL (analyse en français), ou les deux fusionnées par Reciprocal Rank Fusion.
3. **Génération** (`rag.py`, `llm.py`) : les meilleurs chunks sont envoyés au LLM, qui doit répondre uniquement à partir de ceux-ci, citer ses sources et dire quand l'information est absente.

## Installation

Prérequis : Python 3.10+, Docker, [Ollama](https://ollama.com).

```bash
ollama pull bge-m3
ollama pull mistral

docker compose up -d
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Utilisation

Placer les PDF dans `data/` (non versionnés), puis :

```bash
python ingest.py                                   # indexation
python rag.py "Comment sécuriser les mots de passe ?"   # question en ligne de commande
streamlit run app.py                               # interface web
```

Le modèle et les paramètres (taille des chunks, nombre d'extraits) se règlent dans `config.py`.

Corpus utilisé :
- CNIL, *Guide de la sécurité des données personnelles*
- ANSSI, *Guide d'hygiène informatique*
- ANSSI, *Recommandations de sécurité pour un système d'IA générative*
