"""Recherche + génération de la réponse avec citations.

python rag.py "Comment sécuriser les mots de passe ?"
"""
import re
import sys
import unicodedata

import config
import llm
from search import retrieve

NOT_FOUND = "Je ne trouve pas cette information dans les documents."
CHUNK_ID = re.compile(r"\b([A-Z]{3,4}_\d{2}_C\d{2})\b")

SYSTEM_PROMPT = f"""Tu es un assistant qui répond à des questions sur la sécurité informatique \
et la protection des données, à partir d'extraits de guides de la CNIL et de l'ANSSI.

Règles :
- Réponds en français, de façon concise.
- Utilise uniquement les informations des extraits fournis. N'utilise jamais tes connaissances \
générales et ne devine pas.
- Après chaque information, cite l'identifiant de l'extrait qui la justifie, entre crochets.
- Si les extraits ne permettent pas de répondre, réponds seulement : « {NOT_FOUND} »"""


def build_context(chunks):
    """Les extraits, chacun précédé de son identifiant, de son titre et de sa source."""
    parts = []
    for c in chunks:
        section = f"\nSection : {', '.join(c['sections'])}" if c["sections"] else ""
        parts.append(f"[{c['chunk_id']}]\nTitre : {c['title']}{section}\n"
                     f"Source : {c['source']}\nTexte : {c['text']}")
    return "\n\n".join(parts)


def build_prompt(question, chunks):
    # consignes répétées en fin de message : les petits modèles suivent mieux
    # ce qui est juste avant la réponse
    return (
        f"Extraits :\n\n{build_context(chunks)}\n\n"
        f"Question : {question}\n\n"
        "Consignes : réponds uniquement à partir des extraits ci-dessus, en 5 points maximum, "
        "sans répétition. Chaque point commence par un tiret et se termine par l'identifiant "
        "de l'extrait qui le justifie. Exemple de format (sur un autre sujet) :\n"
        "- Les sauvegardes doivent être testées régulièrement [XXX_00_C01]\n"
        "Un même extrait peut servir plusieurs fois. "
        f"Si les extraits ne contiennent pas la réponse, écris seulement : « {NOT_FOUND} »"
    )


def normaliser(texte):
    texte = unicodedata.normalize("NFD", texte.lower().replace("’", "'"))
    return " ".join("".join(c for c in texte if unicodedata.category(c) != "Mn").split())


def est_un_refus(reponse):
    return normaliser(NOT_FOUND.rstrip(".")) in normaliser(reponse)


def answer(question, k=config.TOP_K, mode="hybrid"):
    """Recherche les extraits, génère la réponse et vérifie ses citations.

    Renvoie un dictionnaire : question, reponse, sources (identifiants cités qui font partie
    des extraits), citations_invalides (identifiants cités qui n'en font pas partie),
    refus, chunks (extraits récupérés).
    """
    chunks = retrieve(question, k, mode)
    if chunks:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(question, chunks)},
        ]
        reponse = llm.chat(messages)
    else:
        reponse = NOT_FOUND

    recuperes = [c["chunk_id"] for c in chunks]
    cites = list(dict.fromkeys(CHUNK_ID.findall(reponse)))  # sans doublons, dans l'ordre
    return {
        "question": question,
        "reponse": reponse,
        "sources": [i for i in cites if i in recuperes],
        "citations_invalides": [i for i in cites if i not in recuperes],
        "refus": est_un_refus(reponse),
        "chunks": chunks,
    }


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Comment sécuriser les mots de passe ?"
    r = answer(question)
    print(r["reponse"])
    print(f"\nSources : {', '.join(r['sources']) or 'aucune'}")
    if r["citations_invalides"]:
        print(f"Citations invalides (extraits non fournis) : {', '.join(r['citations_invalides'])}")
    print("\nExtraits récupérés :")
    for c in r["chunks"]:
        mark = "*" if c["chunk_id"] in r["sources"] else " "
        print(f" {mark} [{c['chunk_id']}] {c['score']:.4f}  {c['title']} ({c['source'].split(', p. ')[-1]})")
