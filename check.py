"""Affiche le contenu de la base et les 5 chunks les plus proches d'une question.

python check.py "Comment sécuriser les mots de passe ?"
"""
import sys

from rag import connect
from search import vector_search

question = " ".join(sys.argv[1:]) or "Comment sécuriser les mots de passe ?"

with connect() as conn:
    for doc, n in conn.execute("SELECT doc, COUNT(*) FROM chunks GROUP BY doc ORDER BY doc"):
        print(f"{doc} : {n} chunks")

    print(f"\nQuestion : {question}\n")
    for rank, c in enumerate(vector_search(conn, question, 5), start=1):
        print(f"{rank}. {c['doc']}, p. {c['page']} (similarité {c['score']:.2f})")
        print(f"   {c['content'][:250]}...\n")
