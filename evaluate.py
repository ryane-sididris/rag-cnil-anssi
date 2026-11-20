"""Évaluation sur evaluation/questions.json.

python evaluate.py --recherche   # recherche seule, 3 modes
python evaluate.py               # recherche + réponses (mode hybride)
python evaluate.py --bilan       # synthèse des colonnes remplies à la main dans resultats.csv

Colonnes à remplir dans resultats.csv :
  correct : oui / partiel / non
  ancree  : oui / non
  echec   : aucun / recherche / generation / ancrage / refus
"""
import argparse
import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import config
from rag import answer, normaliser
from search import MODES, retrieve

DOSSIER = Path(config.EVAL_DIR)
QUESTIONS = DOSSIER / "questions.json"
RECHERCHE_CSV = DOSSIER / "recherche.csv"
RESULTATS_JSON = DOSSIER / "resultats.json"
RESULTATS_CSV = DOSSIER / "resultats.csv"
JUGEMENTS = ("correct", "ancree", "echec", "commentaire")
CATEGORIES = ("directe", "reformulee", "difficile", "hors_corpus")


def rang_bon_chunk(q, chunks):
    # bon chunk : chunk d'un document attendu qui contient toute la preuve
    for rang, c in enumerate(chunks, start=1):
        if c["document_id"] in q["documents_attendus"] and \
                all(normaliser(p) in normaliser(c["text"]) for p in q.get("preuve", [])):
            return rang
    return None


def faits_trouves(q, reponse):
    if not q.get("faits"):
        return ""
    r = normaliser(reponse)
    return f"{sum(any(normaliser(v) in r for v in fait) for fait in q['faits'])}/{len(q['faits'])}"


def pct(n, total):
    return f"{n}/{total} ({100 * n / total:.0f} %)" if total else "-"


def ecrire_csv(chemin, lignes):
    with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0]), delimiter=";")
        w.writeheader()
        w.writerows(lignes)


def lire_csv(chemin):
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def evaluer_recherche(questions):
    avec_reponse = [q for q in questions if q["documents_attendus"]]
    lignes = []
    for q in avec_reponse:
        rangs = {m: rang_bon_chunk(q, retrieve(q["question"], config.TOP_K, m)) for m in MODES}
        lignes.append({"id": q["id"], "categorie": q["categorie"], "question": q["question"],
                       **{m: rangs[m] or "" for m in MODES}})

    print(f"Bon chunk dans les {config.TOP_K} premiers :\n")
    print(f"  {'':<12}" + "".join(f"{m:<22}" for m in MODES))
    for cat in ("directe", "reformulee", "difficile", None):
        groupe = [l for l in lignes if cat is None or l["categorie"] == cat]
        print(f"  {cat or 'total':<12}" + "".join(
            f"{pct(sum(bool(l[m]) for l in groupe), len(groupe)):<22}" for m in MODES))
    print(f"  {'MRR':<12}" + "".join(
        f"{sum(1 / l[m] for l in lignes if l[m]) / len(lignes):<22.2f}" for m in MODES))

    differences = [l for l in lignes if len({bool(l[m]) for m in MODES}) > 1]
    if differences:
        print("\n  Rang du bon chunk quand les modes diffèrent (- = absent) :")
        for l in differences:
            print(f"    {l['id']} " + "  ".join(f"{m}: {l[m] or '-'}" for m in MODES) + f"  {l['question']}")

    ecrire_csv(RECHERCHE_CSV, lignes)


def evaluer_reponses(questions):
    if RESULTATS_CSV.exists() and any(l.get("correct") for l in lire_csv(RESULTATS_CSV)):
        raise SystemExit(f"{RESULTATS_CSV} contient déjà des jugements, renomme-le avant de relancer.")

    complet, lignes = [], []
    print(f"Mode hybride, k = {config.TOP_K}, {config.LLM_MODEL}\n")
    for q in questions:
        debut = time.time()
        r = answer(q["question"])
        duree = round(time.time() - debut, 1)
        rang = rang_bon_chunk(q, r["chunks"]) if q["documents_attendus"] else None
        complet.append({**q, **r, "rang_bon_chunk": rang, "duree_s": duree})
        lignes.append({
            "id": q["id"], "categorie": q["categorie"], "question": q["question"],
            "attendu": q["attendu"], "documents_attendus": ", ".join(q["documents_attendus"]) or "aucun",
            "extraits_recuperes": ", ".join(c["chunk_id"] for c in r["chunks"]),
            "rang_bon_chunk": rang or ("" if q["documents_attendus"] else "sans objet"),
            "reponse": r["reponse"], "sources_citees": ", ".join(r["sources"]),
            "citations_invalides": ", ".join(r["citations_invalides"]),
            "refus": "oui" if r["refus"] else "non", "faits_trouves": faits_trouves(q, r["reponse"]),
            "duree_s": duree, **{j: "" for j in JUGEMENTS},
        })
        etat = "REFUS" if r["refus"] else (lignes[-1]["faits_trouves"] or "répond")
        print(f"  {q['id']} [{q['categorie'][:5]}] bon chunk: {rang or '-':<2} {etat:<6} {duree:4.0f} s  {q['question']}")

    with open(RESULTATS_JSON, "w", encoding="utf-8") as f:
        json.dump(complet, f, ensure_ascii=False, indent=1)
    ecrire_csv(RESULTATS_CSV, lignes)

    attendus = [l for l in lignes if l["attendu"] == "reponse"]
    hors = [l for l in lignes if l["categorie"] == "hors_corpus"]
    repondues = [l for l in lignes if l["refus"] == "non" and l["categorie"] != "hors_corpus"]
    print(f"\n  bon chunk récupéré           {pct(sum(bool(l['rang_bon_chunk']) for l in attendus), len(attendus))}")
    print(f"  refus hors corpus            {pct(sum(l['refus'] == 'oui' for l in hors), len(hors))}")
    print(f"  refus à tort                 {pct(sum(l['refus'] == 'oui' for l in attendus), len(attendus))}")
    print(f"  réponses avec une source     {pct(sum(bool(l['sources_citees']) for l in repondues), len(repondues))}")
    print(f"  citations invalides          {sum(bool(l['citations_invalides']) for l in lignes)}")
    print(f"  temps moyen                  {sum(l['duree_s'] for l in lignes) / len(lignes):.0f} s")


def bilan():
    lignes = lire_csv(RESULTATS_CSV)
    manquants = [l["id"] for l in lignes if not l["correct"] or not l["echec"]]
    if manquants:
        print(f"Non jugées : {', '.join(manquants)}\n")

    print(f"{'':<12}{'n':>3}  {'correct':<22}{'partiel':<22}{'ancrée':<22}")
    for cat in CATEGORIES:
        g = [l for l in lignes if l["categorie"] == cat]
        print(f"{cat:<12}{len(g):>3}  {pct(sum(l['correct'] == 'oui' for l in g), len(g)):<22}"
              f"{pct(sum(l['correct'] == 'partiel' for l in g), len(g)):<22}"
              f"{pct(sum(l['ancree'] == 'oui' for l in g), len(g)):<22}")

    echecs = defaultdict(list)
    for l in lignes:
        echecs[l["echec"] or "?"].append(l["id"])
    print("\nÉchecs :")
    for typ, n in Counter({k: len(v) for k, v in echecs.items()}).most_common():
        print(f"  {typ:<11} {n:>2}  {', '.join(echecs[typ])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recherche", action="store_true")
    ap.add_argument("--bilan", action="store_true")
    args = ap.parse_args()

    if args.bilan:
        return bilan()
    with open(QUESTIONS, encoding="utf-8") as f:
        questions = json.load(f)
    print(f"{len(questions)} questions : " + ", ".join(
        f"{n} {c}" for c, n in Counter(q["categorie"] for q in questions).items()) + "\n")
    if args.recherche:
        evaluer_recherche(questions)
    else:
        evaluer_reponses(questions)


if __name__ == "__main__":
    main()
