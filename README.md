# RAG sur les guides CNIL / ANSSI

Assistant de questions-réponses sur des guides publics de la CNIL et de l'ANSSI. Tout tourne en local : LLM et embeddings via Ollama, stockage dans PostgreSQL avec pgvector.

## Avancement

- [x] Extraction des PDF, découpage en chunks, embeddings (bge-m3), stockage pgvector
- [ ] Recherche hybride (vectorielle + plein texte)
- [ ] Génération avec citation des sources
- [ ] Évaluation sur un jeu de questions de test

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
python ingest.py
python check.py "Comment sécuriser les mots de passe ?"
```

Corpus utilisé :
- CNIL, *Guide de la sécurité des données personnelles*
- ANSSI, *Guide d'hygiène informatique*
- ANSSI, *Recommandations de sécurité pour un système d'IA générative*
