"""Indexation de corpus/chunks.json dans PostgreSQL (pgvector + plein texte).

La table est recréée à chaque exécution.
"""
import json
import time

import numpy as np
import ollama
import psycopg
from pgvector.psycopg import register_vector

import config

SCHEMA = f"""
DROP TABLE IF EXISTS chunks;
CREATE TABLE chunks (
    chunk_id    TEXT PRIMARY KEY,
    document_id TEXT   NOT NULL,
    title       TEXT   NOT NULL,
    source      TEXT   NOT NULL,
    page        INT    NOT NULL,
    sections    TEXT[] NOT NULL,
    text        TEXT   NOT NULL,
    embedding   vector({config.EMBED_DIM}) NOT NULL,
    -- titre du document (poids A) + texte (poids B)
    tsv tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('french', title), 'A') || setweight(to_tsvector('french', text), 'B')
    ) STORED
);
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON chunks USING gin (tsv);
"""


def texte_a_vectoriser(chunk):
    return f"{chunk['title']}\n{chunk['text']}"


def embed(texts, batch_size=16):
    vectors = []
    for i in range(0, len(texts), batch_size):
        response = ollama.embed(model=config.EMBED_MODEL, input=texts[i:i + batch_size])
        vectors.extend(response["embeddings"])
    return vectors


def main():
    with open(config.CHUNKS_FILE, encoding="utf-8") as f:
        chunks = json.load(f)

    start = time.time()
    vectors = embed([texte_a_vectoriser(c) for c in chunks])

    with psycopg.connect(config.DB_URL) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)
        conn.execute(SCHEMA)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (chunk_id, document_id, title, source, page, sections, text, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                [(c["chunk_id"], c["document_id"], c["title"], c["source"], c["page"], c["sections"],
                  c["text"], np.array(v, dtype=np.float32)) for c, v in zip(chunks, vectors)],
            )
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    print(f"{n} chunks indexés en {time.time() - start:.0f} s")


if __name__ == "__main__":
    main()
