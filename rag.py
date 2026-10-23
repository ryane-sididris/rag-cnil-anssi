"""Recherche + génération de la réponse avec citations.

python rag.py "Comment sécuriser les mots de passe ?"
"""
import re
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
    # consignes répétées en fin de message : les petits modèles suivent mieux
    # ce qui est juste avant la réponse
    return (
        f"Extraits :\n\n{context}\n\n"
        f"Question : {question}\n\n"
        "Consignes : réponds en 5 points maximum, sans répétition. "
        "Chaque point commence par un tiret et se termine par le numéro de l'extrait "
        "qui le justifie. Exemple de format (sur un autre sujet) :\n"
        "- Les sauvegardes doivent être testées régulièrement [2]\n"
        "Un même numéro peut servir plusieurs fois. "
        f"Si les extraits ne contiennent pas la réponse, écris seulement : « {NOT_FOUND} »"
    )


def answer(conn, question, mode="hybrid", k=config.TOP_K):
    chunks = search(conn, question, mode, k)
    if not chunks:
        return NOT_FOUND, []
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(question, chunks)},
    ]
    return llm.chat(messages), chunks


def cited_numbers(reply, chunks):
    """Numéros d'extraits cités dans la réponse, en ignorant ceux qui n'existent pas."""
    numbers = {int(n) for n in re.findall(r"\[(\d+)\]", reply)}
    return sorted(n for n in numbers if 1 <= n <= len(chunks))


def connect():
    conn = psycopg.connect(config.DB_URL, autocommit=True)
    register_vector(conn)
    return conn


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Comment sécuriser les mots de passe ?"
    with connect() as conn:
        reply, chunks = answer(conn, question)
    print(reply, "\n")
    for n in cited_numbers(reply, chunks):
        print(f"[{n}] {chunks[n - 1]['doc']}, p. {chunks[n - 1]['page']}")
