"""Préparation du corpus : PDF bruts (data/) -> corpus/documents.json

python prepare.py

Chaque guide est découpé selon sa propre structure :
  - CNIL, sécurité des données personnelles : 1 document par fiche ;
  - ANSSI, hygiène informatique : avant-propos et mode d'emploi, puis 1 document par chapitre
    (les 42 mesures y sont des sections) ;
  - ANSSI, IA générative : 1 document par partie du sommaire (les recommandations R1-R35
    y sont des sections).

Le texte est lu ligne par ligne avec sa taille de police, ce qui permet de reconnaître les
titres et de retirer en-têtes, pieds de page, numéros de page et notes de bas de page.
Les sous-titres sont conservés dans "sections", pour que le découpage en chunks
(chunk.py) puisse suivre la structure des documents.
"""
import json
import re
from collections import Counter
from pathlib import Path

import pymupdf

import config

SOURCES = {
    "cnil_securite.pdf": {
        "prefixe": "CNIL",
        "nom": "CNIL, Guide pratique RGPD – Sécurité des données personnelles (édition 2024, mise à jour 2026)",
        "url": "https://www.cnil.fr/fr/guide-de-la-securite-des-donnees-personnelles-nouvelle-edition-2024",
    },
    "anssi_hygiene.pdf": {
        "prefixe": "HYG",
        "nom": "ANSSI, Guide d'hygiène informatique – 42 mesures (version 2.0, septembre 2017)",
        "url": "https://cyber.gouv.fr",
    },
    "anssi_ia_generative.pdf": {
        "prefixe": "IAG",
        "nom": "ANSSI, Recommandations de sécurité pour un système d'IA générative (ANSSI-PA-102, avril 2024)",
        "url": "https://cyber.gouv.fr/sites/default/files/document/"
               "Recommandations_de_s%C3%A9curit%C3%A9_pour_un_syst%C3%A8me_d_IA_g%C3%A9n%C3%A9rative.pdf",
    },
}

ACRONYMES = {"api": "API", "ia": "IA", "rgpd": "RGPD", "wi-fi": "Wi-Fi"}
CORRECTIONS = {"articificielle": "artificielle"}  # coquille présente dans le PDF de la CNIL
ETIQUETTE = re.compile(r"(Mesure \d+|R\d+)")


# ---------------------------------------------------------------- lecture du PDF

def _texte_ligne(spans):
    """Texte d'une ligne, reconstruit caractère par caractère, et sa taille de police principale.

    Certains PDF justifiés n'encodent pas les espaces (« Cedocumentrédigéparl'ANSSI ») :
    on remet un espace quand l'écart entre deux caractères est anormalement grand.
    """
    tailles = Counter()
    for s in spans:
        tailles[round(s["size"], 1)] += len(s["chars"])
    principale = tailles.most_common(1)[0][0]

    sortie, fin_prec = [], None
    for i, s in enumerate(spans):
        texte = "".join(c["c"] for c in s["chars"]).strip()
        petit = s["size"] < 0.85 * principale
        if petit and re.fullmatch(r"\d+", texte):  # appel de note en exposant
            continue
        if i == 0 and petit and texte == "I":  # puce du guide IA (glyphe « I »)
            sortie.append("- ")
            fin_prec = None
            continue
        for c in s["chars"]:
            if (fin_prec is not None and c["c"] != " " and sortie and sortie[-1] != " "
                    and c["bbox"][0] - fin_prec > 0.12 * s["size"]):
                sortie.append(" ")
            sortie.append(c["c"])
            fin_prec = c["bbox"][2]
    texte = "".join(sortie).replace("\x07", "").replace("\xad", "").replace("\t", " ")
    return " ".join(texte.split()), principale


def lignes(pdf_path):
    """Liste de lignes {page, taille, gras, y, texte}, triées de haut en bas sur chaque page."""
    resultat = []
    with pymupdf.open(pdf_path) as doc:
        for num, page in enumerate(doc, start=1):
            page_lignes = []
            for bloc in page.get_text("rawdict")["blocks"]:
                for ligne in bloc.get("lines", []):
                    spans = [s for s in ligne["spans"] if "".join(c["c"] for c in s["chars"]).strip()]
                    if not spans:
                        continue
                    texte, taille = _texte_ligne(spans)
                    if texte:
                        gras = bool(max(spans, key=lambda s: len(s["chars"]))["flags"] & 16)
                        page_lignes.append({"page": num, "taille": taille, "gras": gras,
                                            "y": round(ligne["bbox"][1]), "x": ligne["bbox"][0],
                                            "texte": texte})
            page_lignes.sort(key=lambda l: (l["y"], l["x"]))
            resultat.extend(page_lignes)
    return resultat


# ------------------------------------------------- reconnaissance des éléments par guide
# Chaque fonction associe une ligne à un type :
#   "ignorer", "document" (titre de document), "sous-document" (partie de niveau 2),
#   "section" (sous-titre), "niveau" (mention standard / renforcé) ou "texte".

def classer_cnil(l):
    t, taille = l["texte"], l["taille"]
    if not 5 <= l["page"] <= 60:  # avant : couverture, sommaire, avant-propos ; après : check-list
        return "ignorer"
    if taille >= 13 and l["gras"]:
        return "document"
    if taille == 13.0 or (taille == 6.6 and t.isupper()):
        return "section"
    if taille in (6.0, 7.0, 30.0) or (taille == 10.0 and l["y"] > 550):
        return "ignorer"  # notes, tableaux, intercalaires de partie, numéros de page
    return "texte"


def classer_hygiene(l):
    t, taille = l["texte"], l["taille"]
    if not 3 <= l["page"] <= 60 or l["page"] == 4:  # sommaire, outil de suivi, bibliographie
        return "ignorer"
    if t in ("AVANT-PROPOS", "MODE D’EMPLOI DU GUIDE"):  # réunis dans un document d'introduction
        return "document" if l["page"] == 3 else "section"
    if taille == 22.5:
        return "document"
    if taille == 50.0 or 14.5 <= taille <= 15.5:
        return "section"  # numéro et titre de la mesure
    if taille == 6.7 and l["gras"]:
        return "niveau"
    if taille in (6.7, 8.0, 113.5) or (taille == 10.0 and l["gras"]) or l["y"] > 545:
        return "ignorer"  # en-têtes, références, numéros de chapitre et de page
    return "texte"


def classer_ia(l):
    t, taille = l["texte"], l["taille"]
    if not 5 <= l["page"] <= 31:  # avant : couverture, sommaire ; après : liste des R, bibliographie
        return "ignorer"
    if taille in (33.9, 27.9):
        if re.fullmatch(r"\d+(\.\d+)*", t):
            return "ignorer"  # numéro de partie
        return "document" if taille == 33.9 else "sous-document"
    if taille == 17.9 or (taille == 12.0 and re.fullmatch(r"R\d+", t)):
        return "section"  # titre de recommandation, terme défini, ou étiquette R1-R35
    if taille in (8.0, 9.0, 43.8) or l["y"] > 770:
        return "ignorer"  # notes, pied de page, numéro de chapitre
    return "texte"


CLASSEURS = {"cnil_securite.pdf": classer_cnil, "anssi_hygiene.pdf": classer_hygiene,
             "anssi_ia_generative.pdf": classer_ia}


# ------------------------------------------------------------- assemblage des documents

def joindre(a, b):
    """Recolle deux morceaux de texte, en réparant les mots coupés en fin de ligne."""
    if a.endswith("-") and b[:1].islower():
        return a + b if b.startswith(("ci ", "ci,", "là")) else a[:-1] + b
    return f"{a} {b}"


def nb_mots(doc):
    return sum(len(p.split()) for s in doc["sections"] for p in s["paragraphes"])


def assembler(pdf_name):
    """Construit la liste des documents d'un guide : titre, pages et sections."""
    classer = CLASSEURS[pdf_name]
    docs, doc, section, prec, chapitre = [], None, None, None, None

    for l in lignes(Path(config.DATA_DIR) / pdf_name):
        genre, t = classer(l), l["texte"]
        if genre == "ignorer":
            continue
        # ligne suivante d'un titre sur plusieurs lignes ?
        suite = (prec and prec[0] == genre and prec[1]["page"] == l["page"]
                 and l["y"] - prec[1]["y"] < 1.6 * max(l["taille"], 18))

        if genre in ("document", "sous-document"):
            if suite:
                doc["titre"] = joindre(doc["titre"], t)
                if genre == "document":
                    chapitre = doc["titre"]
            else:
                if genre == "document":
                    chapitre = t
                intro = []
                if genre == "sous-document" and doc and doc["niveau"] == 1 and nb_mots(doc) < 100:
                    # courte introduction de partie : rattachée à la première sous-partie
                    docs.remove(doc)
                    intro = [s for s in doc["sections"] if s["paragraphes"]]
                doc = {"titre": t, "niveau": 1 if genre == "document" else 2, "partie": chapitre,
                       "pages": [intro[0]["page"] if intro else l["page"], l["page"]], "sections": intro}
                docs.append(doc)
                section = None
        elif doc is None:
            continue
        elif genre == "section":
            if l["taille"] == 50.0 and t.isdigit():  # numéro de mesure du guide d'hygiène
                t = f"Mesure {t}"
            if suite and section and not section["paragraphes"]:
                # titre sur plusieurs lignes, ou étiquette (« Mesure 5 », « R3 ») + titre
                if ETIQUETTE.fullmatch(t):
                    section["titre"] = f"{t} – {section['titre']}"
                elif ETIQUETTE.fullmatch(section["titre"]):
                    section["titre"] = f"{section['titre']} – {t}"
                else:
                    section["titre"] = joindre(section["titre"], t)
            else:
                section = {"titre": t, "page": l["page"], "paragraphes": []}
                doc["sections"].append(section)
        else:
            if genre == "niveau":
                t = "Niveau renforcé :" if "renforc" in t.lower() else "Niveau standard :"
            if section is None:
                section = {"titre": None, "page": l["page"], "paragraphes": []}
                doc["sections"].append(section)
            paras = section["paragraphes"]
            if not paras or genre == "niveau" or t.startswith(("•", "- ", ">>")) or re.match(r"\d+\. ", t):
                paras.append(t)
            elif paras[-1].endswith("-") and t[:1].islower():
                paras[-1] = joindre(paras[-1], t)
            elif l["page"] != prec[1]["page"]:
                # changement de page : on continue la phrase si elle n'était pas finie
                if paras[-1].endswith((".", "!", "?", ":", "»")):
                    paras.append(t)
                else:
                    paras[-1] = joindre(paras[-1], t)
            elif prec[0] != "texte" or l["y"] - prec[1]["y"] > 1.9 * l["taille"]:
                paras.append(t)
            else:
                paras[-1] = joindre(paras[-1], t)
        doc["pages"][1] = l["page"]
        prec = (genre, l)

    for d in docs:
        for s in d["sections"]:
            if s["titre"]:
                s["titre"] = titre_propre(s["titre"])
            s["paragraphes"] = [re.sub(r"\s+([.,)])", r"\1", re.sub(r"^(>>|•)\s*", "- ", p))
                                for p in s["paragraphes"] if len(p.split()) >= 2]
        d["sections"] = [s for s in d["sections"] if s["paragraphes"]]
    return [d for d in docs if d["sections"]]


def titre_propre(texte):
    """« FICHE 4 - AUTHENTIFIER LES UTILISATEURS » -> « Authentifier les utilisateurs »."""
    texte = re.sub(r"^FICHE\s*\d+\s*[-–]\s*", "", " ".join(texte.split()), flags=re.I)
    if sum(c.isupper() for c in texte) > sum(c.islower() for c in texte):  # titre en capitales
        texte = " ".join(ACRONYMES.get(m, CORRECTIONS.get(m, m)) for m in texte.lower().split())
        texte = texte[0].upper() + texte[1:]
    return texte


def texte_document(sections):
    return "\n\n".join("\n".join(([s["titre"]] if s["titre"] else []) + s["paragraphes"]) for s in sections)


def mots(texte):
    return set(re.findall(r"\w+", texte.lower()))


def main():
    documents = []
    for pdf_name, info in SOURCES.items():
        # le guide d'hygiène commence par un document d'introduction (HYG_00), puis les chapitres I à X
        debut = 0 if info["prefixe"] == "HYG" else 1
        for i, d in enumerate(assembler(pdf_name), start=debut):
            titre = titre_propre(d["titre"])
            if info["prefixe"] == "CNIL":
                titre = f"Fiche {i} – {titre}"
            elif info["prefixe"] == "HYG":
                titre = f"Chapitre {i} – {titre}" if i else "Avant-propos et mode d'emploi du guide"
            p1, p2 = d["pages"]
            documents.append({
                "document_id": f"{info['prefixe']}_{i:02d}",
                "title": titre,
                "source": f"{info['nom']}, p. {p1}" + (f"-{p2}" if p2 != p1 else "") + " du PDF",
                "url": info["url"],
                "fichier": pdf_name,
                "partie": d["partie"] if info["prefixe"] == "IAG" and d["niveau"] == 2 else None,
                "pages": [p1, p2],
                "text": texte_document(d["sections"]),
                "sections": [{"titre": s["titre"], "page": s["page"], "texte": "\n".join(s["paragraphes"])}
                             for s in d["sections"]],
            })

    # contrôle des quasi-doublons (similarité de Jaccard sur le vocabulaire)
    for i, a in enumerate(documents):
        for b in documents[i + 1:]:
            ma, mb = mots(a["text"]), mots(b["text"])
            if len(ma & mb) / len(ma | mb) > 0.6:
                print(f"Attention, documents très proches : {a['document_id']} et {b['document_id']}")

    Path(config.CORPUS_DIR).mkdir(exist_ok=True)
    with open(config.DOCUMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=1)

    tailles = [len(d["text"].split()) for d in documents]
    for d, n in zip(documents, tailles):
        print(f"{d['document_id']:<8} {n:>5} mots {len(d['sections']):>3} sections  {d['title'][:70]}")
    print(f"\n{len(documents)} documents, de {min(tailles)} à {max(tailles)} mots "
          f"(moyenne {sum(tailles) / len(tailles):.0f}) -> {config.DOCUMENTS_FILE}")


if __name__ == "__main__":
    main()
