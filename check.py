"""Affiche le contenu de la base et les 5 chunks les plus proches d'une question.

python check.py "Comment sécuriser les mots de passe ?"
"""
import sys

import numpy as np
import ollama
import psycopg
from pgvector.psycopg import register_vector

import config

question = " ".join(sys.argv[1:]) or "Comment sécuriser les mots de passe ?"

with psycopg.connect(config.DB_URL) as conn:
    register_vector(conn)

    for doc, n in conn.execute("SELECT doc, COUNT(*) FROM chunks GROUP BY doc ORDER BY doc"):
        print(f"{doc} : {n} chunks")

    q_vec = np.array(ollama.embed(model=config.EMBED_MODEL, input=question)["embeddings"][0],
                     dtype=np.float32)
    rows = conn.execute(
        "SELECT doc, page, content, embedding <=> %s AS distance "
        "FROM chunks ORDER BY distance LIMIT 5",
        (q_vec,),
    ).fetchall()

    print(f"\nQuestion : {question}\n")
    for rank, (doc, page, content, dist) in enumerate(rows, start=1):
        print(f"{rank}. {doc}, p. {page} (similarité {1 - dist:.2f})")
        print(f"   {content[:250]}...\n")
