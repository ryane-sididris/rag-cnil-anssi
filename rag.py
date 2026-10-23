"""Recherche + génération de la réponse avec citations.

python rag.py "Comment sécuriser les mots de passe ?"
"""
import sys

import psycopg
from pgvector.psycopg import register_vector

import config
import llm
from search import search

NOT_FOUND = "Je ne trouve pas cette information dans les documents."

SYSTEM_PROMPT = f"""Tu réponds à des questions sur la sécurité informatique et la protection \
des données, uniquement à partir des extraits de guides de la CNIL et de l'ANSSI fournis.

Règles :
- Réponds en français, de façon concise.
- Utilise uniquement les informations des extraits, jamais tes connaissances générales.
- Cite tes sources avec le numéro de l'extrait entre crochets, par exemple [1] ou [2][3].
- Si les extraits ne permettent pas de répondre, réponds seulement : « {NOT_FOUND} »"""


def build_prompt(question, chunks):
    context = "\n\n".join(
        f"[{i}] ({c['doc']}, p. {c['page']})\n{c['content']}"
        for i, c in enumerate(chunks, start=1)
    )
    return f"Extraits :\n\n{context}\n\nQuestion : {question}"


def answer(conn, question, mode="hybrid", k=config.TOP_K):
    chunks = search(conn, question, mode, k)
    if not chunks:
        return NOT_FOUND, []
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(question, chunks)},
    ]
    return llm.chat(messages), chunks


def connect():
    conn = psycopg.connect(config.DB_URL, autocommit=True)
    register_vector(conn)
    return conn


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Comment sécuriser les mots de passe ?"
    with connect() as conn:
        reply, chunks = answer(conn, question)
    print(reply, "\n")
    for i, c in enumerate(chunks, start=1):
        print(f"[{i}] {c['doc']}, p. {c['page']}")
