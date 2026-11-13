"""Découpage des documents en chunks : corpus/documents.json -> corpus/chunks.json

python chunk.py

Stratégie : les chunks suivent la structure des documents (sections d'une fiche CNIL,
mesures ANSSI, recommandations R1-R35).
  1. Une section qui tient dans CHUNK_WORDS mots n'est jamais coupée.
  2. Les petites sections voisines d'un même document sont regroupées jusqu'à CHUNK_WORDS mots
     (sinon on obtiendrait des chunks de 30 mots, trop pauvres pour répondre).
  3. Une section plus longue est coupée entre deux paragraphes, avec OVERLAP_WORDS mots de
     chevauchement ; chaque morceau garde le titre de sa section.
  4. Un chunk de moins de MIN_CHUNK_WORDS mots (introduction d'une fiche, par exemple)
     est fusionné avec son voisin.
Chaque chunk garde les métadonnées de son document (identifiant, titre, source).
"""
import json

import config


def nb_mots(texte):
    return len(texte.split())


def couper_section(titre, texte, max_mots=config.CHUNK_WORDS, chevauchement=config.OVERLAP_WORDS):
    """Coupe une section trop longue entre deux paragraphes.

    Un paragraphe n'est jamais coupé, sauf s'il dépasse max_mots à lui seul.
    Chaque morceau commence par le titre de la section et les `chevauchement`
    derniers mots du morceau précédent.
    """
    unites = []
    for para in texte.split("\n"):
        m = para.split()
        unites.extend(" ".join(m[i:i + max_mots]) for i in range(0, len(m), max_mots))

    morceaux, courant, nouveaux = [], [], 0
    for unite in unites:
        n = nb_mots(unite)
        if nouveaux and nb_mots("\n".join(courant)) + n > max_mots:
            morceaux.append(courant)
            fin = " ".join(" ".join(courant).split()[-chevauchement:]) if chevauchement else ""
            courant, nouveaux = ([f"[...] {fin}"] if fin else []), 0
        courant.append(unite)
        nouveaux += n
    if nouveaux:
        morceaux.append(courant)

    resultat = []
    for i, morceau in enumerate(morceaux):
        entete = [titre if i == 0 else f"{titre} (suite)"] if titre else []
        resultat.append("\n".join(entete + morceau))
    return resultat


def decouper(document, max_mots=config.CHUNK_WORDS, min_mots=config.MIN_CHUNK_WORDS):
    """Liste de (titres des sections, page, texte) pour un document."""
    # 1. unités = sections entières, ou morceaux de sections trop longues
    unites = []
    for s in document["sections"]:
        bloc = "\n".join(([s["titre"]] if s["titre"] else []) + [s["texte"]])
        if nb_mots(bloc) <= max_mots:
            unites.append(([s["titre"]], s["page"], bloc))
        else:
            unites.extend(([s["titre"]], s["page"], m) for m in couper_section(s["titre"], s["texte"]))

    # 2. regroupement des unités voisines tant que le chunk reste sous max_mots
    chunks = []
    for titres, page, texte in unites:
        if chunks and nb_mots(chunks[-1][2]) + nb_mots(texte) <= max_mots:
            chunks[-1][0].extend(t for t in titres if t not in chunks[-1][0])
            chunks[-1][2] += "\n\n" + texte
        else:
            chunks.append([list(titres), page, texte])

    # 3. un chunk trop court (ex. : introduction d'une fiche) est fusionné avec son voisin,
    #    quitte à dépasser un peu max_mots
    i = 0
    while i < len(chunks) and len(chunks) > 1:
        if nb_mots(chunks[i][2]) < min_mots:
            j = i + 1 if i + 1 < len(chunks) else i - 1
            a, b = sorted((i, j))
            chunks[a] = [chunks[a][0] + [t for t in chunks[b][0] if t not in chunks[a][0]],
                         chunks[a][1], chunks[a][2] + "\n\n" + chunks[b][2]]
            del chunks[b]
            i = a
        else:
            i += 1
    return chunks


def main():
    with open(config.DOCUMENTS_FILE, encoding="utf-8") as f:
        documents = json.load(f)

    chunks = []
    for doc in documents:
        for i, (titres, page, texte) in enumerate(decouper(doc), start=1):
            chunks.append({
                "chunk_id": f"{doc['document_id']}_C{i:02d}",
                "document_id": doc["document_id"],
                "title": doc["title"],
                "source": doc["source"],
                "page": page,
                "sections": [t for t in titres if t],
                "text": texte,
            })

    with open(config.CHUNKS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=1)

    tailles = sorted(nb_mots(c["text"]) for c in chunks)
    print(f"{len(documents)} documents -> {len(chunks)} chunks ({config.CHUNKS_FILE})")
    print(f"taille : min {tailles[0]}, médiane {tailles[len(tailles) // 2]}, max {tailles[-1]} mots")
    print(f"chunks de moins de 100 mots : {sum(t < 100 for t in tailles)}")


if __name__ == "__main__":
    main()
