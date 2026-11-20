"""Recherche des chunks : vectorielle, plein texte ou hybride (RRF).

python search.py "Comment sécuriser les mots de passe ?"
python search.py --mode keyword --k 10 "Comment sécuriser le wifi ?"
"""
import argparse

import numpy as np
import ollama
import psycopg
from pgvector.psycopg import register_vector

import config

MODES = ("hybrid", "vector", "keyword")
COLONNES = "chunk_id, document_id, title, source, page, sections, text"

_conn = None


def connect():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg.connect(config.DB_URL, autocommit=True)
        register_vector(_conn)
    return _conn


def _to_dicts(rows):
    return [
        {"score": float(r[7]), "chunk_id": r[0], "document_id": r[1], "title": r[2], "source": r[3],
         "page": r[4], "sections": r[5], "text": r[6]}
        for r in rows
    ]


def embed_query(query):
    vec = ollama.embed(model=config.EMBED_MODEL, input=query)["embeddings"][0]
    return np.array(vec, dtype=np.float32)


def vector_search(query, k):
    q = embed_query(query)
    rows = connect().execute(
        f"SELECT {COLONNES}, 1 - (embedding <=> %s) AS score "
        "FROM chunks ORDER BY embedding <=> %s LIMIT %s",
        (q, q, k),
    ).fetchall()
    return _to_dicts(rows)


def keyword_search(query, k):
    # plainto_tsquery relie les mots par ET : on les relie par OU pour ne pas
    # exiger que tous les mots de la question soient dans le même chunk
    rows = connect().execute(
        "WITH q AS (SELECT to_tsquery('french', "
        "    replace(plainto_tsquery('french', %s)::text, ' & ', ' | ')) AS query) "
        f"SELECT {COLONNES}, ts_rank_cd(tsv, q.query) AS score "
        "FROM chunks, q WHERE tsv @@ q.query ORDER BY score DESC LIMIT %s",
        (query, k),
    ).fetchall()
    return _to_dicts(rows)


def hybrid_search(query, k, pool=20, rrf_k=60):
    # Reciprocal Rank Fusion : on fusionne les rangs, les scores des deux méthodes
    # n'étant pas comparables
    scores, chunks = {}, {}
    for results in (vector_search(query, pool), keyword_search(query, pool)):
        for rank, chunk in enumerate(results, start=1):
            scores[chunk["chunk_id"]] = scores.get(chunk["chunk_id"], 0) + 1 / (rrf_k + rank)
            chunks[chunk["chunk_id"]] = chunk
    best = sorted(scores, key=scores.get, reverse=True)[:k]
    return [{**chunks[i], "score": round(scores[i], 4)} for i in best]


def retrieve(query, k=config.TOP_K, mode="hybrid"):
    if mode == "vector":
        return vector_search(query, k)
    if mode == "keyword":
        return keyword_search(query, k)
    return hybrid_search(query, k)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="+")
    ap.add_argument("--mode", choices=MODES, default="hybrid")
    ap.add_argument("--k", type=int, default=config.TOP_K)
    args = ap.parse_args()

    for rank, c in enumerate(retrieve(" ".join(args.question), args.k, args.mode), start=1):
        sections = f" – {', '.join(c['sections'])}" if c["sections"] else ""
        print(f"{rank}. [{c['chunk_id']}] score {c['score']:.4f}  {c['title']}{sections}")
        print(f"   {c['text'][:300].replace(chr(10), ' ')}...\n")
