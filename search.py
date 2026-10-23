"""Recherche des chunks : vectorielle, plein texte, ou hybride (fusion RRF)."""
import numpy as np
import ollama

import config

MODES = ("hybrid", "vector", "keyword")


def embed_query(question):
    vec = ollama.embed(model=config.EMBED_MODEL, input=question)["embeddings"][0]
    return np.array(vec, dtype=np.float32)


def _to_dicts(rows):
    return [
        {"id": r[0], "doc": r[1], "page": r[2], "content": r[3], "score": float(r[4])}
        for r in rows
    ]


def vector_search(conn, question, k):
    q = embed_query(question)
    rows = conn.execute(
        "SELECT id, doc, page, content, 1 - (embedding <=> %s) AS score "
        "FROM chunks ORDER BY embedding <=> %s LIMIT %s",
        (q, q, k),
    ).fetchall()
    return _to_dicts(rows)


def keyword_search(conn, question, k):
    # plainto_tsquery relie les mots par ET : on les relie par OU pour ne pas
    # exiger que tous les mots de la question soient dans le même chunk
    rows = conn.execute(
        "WITH q AS (SELECT to_tsquery('french', "
        "    replace(plainto_tsquery('french', %s)::text, ' & ', ' | ')) AS query) "
        "SELECT id, doc, page, content, ts_rank_cd(tsv, q.query) AS score "
        "FROM chunks, q WHERE tsv @@ q.query ORDER BY score DESC LIMIT %s",
        (question, k),
    ).fetchall()
    return _to_dicts(rows)


def hybrid_search(conn, question, k, pool=20, rrf_k=60):
    """Reciprocal Rank Fusion : chaque chunk gagne 1 / (rrf_k + rang) dans chaque liste.

    On fusionne les rangs plutôt que les scores, qui ne sont pas comparables
    entre les deux méthodes.
    """
    scores, chunks = {}, {}
    for results in (vector_search(conn, question, pool), keyword_search(conn, question, pool)):
        for rank, chunk in enumerate(results, start=1):
            scores[chunk["id"]] = scores.get(chunk["id"], 0) + 1 / (rrf_k + rank)
            chunks[chunk["id"]] = chunk
    best = sorted(scores, key=scores.get, reverse=True)[:k]
    return [{**chunks[i], "score": scores[i]} for i in best]


def search(conn, question, mode="hybrid", k=config.TOP_K):
    if mode == "vector":
        return vector_search(conn, question, k)
    if mode == "keyword":
        return keyword_search(conn, question, k)
    return hybrid_search(conn, question, k)
