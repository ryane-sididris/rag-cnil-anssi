"""Indexation des PDF du dossier data/ dans PostgreSQL (pgvector).

python ingest.py
"""
import re
import time
from pathlib import Path

import numpy as np
import ollama
import psycopg
import pymupdf
from pgvector.psycopg import register_vector

import config


def extract_paragraphs(pdf_path):
    """Retourne une liste de (page, paragraphe)."""
    paras = []
    with pymupdf.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            for block in page.get_text("blocks"):
                if block[6] != 0:  # bloc image
                    continue
                text = block[4].replace("­", "")
                text = re.sub(r"-\n(\w)", r"\1", text)  # mots coupés en fin de ligne
                text = " ".join(text.split())
                if len(text.split()) >= 5:  # numéros de page, en-têtes...
                    paras.append((page_num, text))
    return paras


def make_chunks(paras, max_words=config.CHUNK_WORDS, overlap=config.OVERLAP_WORDS):
    """Regroupe les paragraphes en chunks de max_words mots au plus.

    Un paragraphe n'est jamais coupé, sauf s'il dépasse max_words à lui seul.
    Chaque chunk commence par les `overlap` derniers mots du précédent.
    """
    units = []
    for page, text in paras:
        words = text.split()
        for i in range(0, len(words), max_words):
            units.append((page, " ".join(words[i:i + max_words])))

    chunks = []
    current, current_page, current_len, new_len = [], None, 0, 0
    for page, text in units:
        n = len(text.split())
        if new_len and current_len + n > max_words:
            chunks.append((current_page, " ".join(current)))
            tail = " ".join(" ".join(current).split()[-overlap:]) if overlap else ""
            current = [tail] if tail else []
            current_len, new_len, current_page = len(tail.split()), 0, None
        if current_page is None:
            current_page = page
        current.append(text)
        current_len += n
        new_len += n
    if new_len:
        chunks.append((current_page, " ".join(current)))
    return chunks


def embed(texts, batch_size=16):
    vectors = []
    for i in range(0, len(texts), batch_size):
        response = ollama.embed(model=config.EMBED_MODEL, input=texts[i:i + batch_size])
        vectors.extend(response["embeddings"])
    return vectors


def main():
    pdfs = sorted(Path(config.DATA_DIR).glob("*.pdf"))
    if not pdfs:
        print(f"Aucun PDF dans {config.DATA_DIR}/")
        return

    with psycopg.connect(config.DB_URL) as conn:
        register_vector(conn)
        total = 0
        for pdf in pdfs:
            start = time.time()
            chunks = make_chunks(extract_paragraphs(pdf))
            vectors = embed([text for _, text in chunks])

            # on remplace le document s'il a déjà été indexé
            conn.execute("DELETE FROM chunks WHERE doc = %s", (pdf.name,))
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO chunks (doc, page, chunk_index, content, embedding) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [
                        (pdf.name, page, i, text, np.array(vec, dtype=np.float32))
                        for i, ((page, text), vec) in enumerate(zip(chunks, vectors))
                    ],
                )
            conn.commit()

            avg = sum(len(t.split()) for _, t in chunks) / max(len(chunks), 1)
            print(f"{pdf.name} : {len(chunks)} chunks, {avg:.0f} mots en moyenne, "
                  f"{time.time() - start:.0f} s")
            total += len(chunks)

    print(f"\n{len(pdfs)} documents, {total} chunks indexés")


if __name__ == "__main__":
    main()
