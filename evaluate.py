"""Évaluation du RAG sur le jeu de test eval_questions.json.

Trois choses mesurées séparément :
  1. Recherche : le passage qui contient la réponse est-il parmi les TOP_K récupérés ?
     (comparé pour les trois modes : hybride, vectoriel, mots-clés)
  2. Réponse   : la réponse contient-elle les faits attendus ? cite-t-elle ses sources ?
  3. Refus     : les questions hors corpus sont-elles refusées ?

python evaluate.py                    # tout (compte 15 à 30 min avec qwen2.5:3b)
python evaluate.py --sans-generation  # recherche seulement, en 1 à 2 min
"""
import argparse
import json
import time
import unicodedata

import config
from rag import NOT_FOUND, answer, cited_numbers, connect
from search import MODES, search


def norm(texte):
    """Minuscules, sans accents, apostrophes et espaces uniformisés."""
    texte = unicodedata.normalize("NFD", texte.lower().replace("’", "'"))
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return " ".join(texte.split())


def passage_trouve(q, chunks):
    """Rang (1, 2, ...) du premier passage du bon document qui contient toute la preuve, sinon None."""
    for rang, c in enumerate(chunks, start=1):
        if c["doc"] == q["doc"] and all(norm(p) in norm(c["content"]) for p in q["preuve"]):
            return rang
    return None


def faits_presents(q, reponse):
    """Nombre de faits attendus présents dans la réponse (un fait = une liste de formulations acceptées)."""
    r = norm(reponse)
    return sum(any(norm(v) in r for v in fait) for fait in q["faits"])


def est_un_refus(reponse):
    return norm("Je ne trouve pas cette information") in norm(reponse)


def pct(n, total):
    return f"{n}/{total} ({100 * n / total:.0f} %)" if total else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sans-generation", action="store_true")
    args = ap.parse_args()

    with open("eval_questions.json", encoding="utf-8") as f:
        questions = json.load(f)
    dans_corpus = [q for q in questions if q["type"] != "hors_corpus"]
    hors_corpus = [q for q in questions if q["type"] == "hors_corpus"]
    resultats = []

    with connect() as conn:
        # 1. Recherche, pour les trois modes
        print(f"1. RECHERCHE (le bon passage est-il dans les {config.TOP_K} récupérés ?)\n")
        for q in dans_corpus:
            q["rangs"] = {m: passage_trouve(q, search(conn, q["question"], m)) for m in MODES}
        for type_q in ("directe", "reformulee", None):
            groupe = [q for q in dans_corpus if type_q is None or q["type"] == type_q]
            libelle = type_q or "TOTAL"
            ligne = "  ".join(f"{m}: {pct(sum(q['rangs'][m] is not None for q in groupe), len(groupe))}"
                              for m in MODES)
            print(f"  {libelle:<11} {ligne}")
        rangs = [q["rangs"]["hybrid"] for q in dans_corpus if q["rangs"]["hybrid"]]
        if rangs:
            mrr = sum(1 / r for r in rangs) / len(dans_corpus)
            print(f"  MRR (hybride) : {mrr:.2f}   (1 = toujours en 1re position)")

        if args.sans_generation:
            return

        # 2 et 3. Réponses (mode hybride, comme dans l'application)
        print("\n2. RÉPONSES (mode hybride)\n")
        for q in questions:
            debut = time.time()
            reponse, chunks = answer(conn, q["question"])
            duree = time.time() - debut
            r = {"id": q["id"], "type": q["type"], "question": q["question"], "reponse": reponse,
                 "refus": est_un_refus(reponse), "cite": bool(cited_numbers(reponse, chunks)),
                 "duree_s": round(duree, 1),
                 "passages": [f"{c['doc']} p.{c['page']}" for c in chunks]}
            if q["type"] != "hors_corpus":
                r["rang_hybride"] = q["rangs"]["hybrid"]
                r["faits"] = f"{faits_presents(q, reponse)}/{len(q['faits'])}"
            resultats.append(r)
            etat = "REFUS" if r["refus"] else r.get("faits", "répond")
            print(f"  Q{q['id']:>2} [{q['type'][:4]}] {etat:<6} {duree:4.0f} s  {q['question']}")

    rep_corpus = [r for r in resultats if r["type"] != "hors_corpus"]
    rep_hors = [r for r in resultats if r["type"] == "hors_corpus"]
    complets = [r for r in rep_corpus if not r["refus"] and r["faits"].split("/")[0] == r["faits"].split("/")[1]]
    partiels = [r for r in rep_corpus if not r["refus"] and r not in complets and not r["faits"].startswith("0/")]
    faux_refus = [r for r in rep_corpus if r["refus"]]
    print("\n  Questions du corpus :")
    print(f"    réponse complète (tous les faits) : {pct(len(complets), len(rep_corpus))}")
    print(f"    réponse partielle                 : {pct(len(partiels), len(rep_corpus))}")
    print(f"    refus à tort                      : {pct(len(faux_refus), len(rep_corpus))}")
    print(f"    réponses avec au moins une citation : "
          f"{pct(sum(r['cite'] for r in rep_corpus if not r['refus']), len(rep_corpus) - len(faux_refus))}")
    print("    refus à tort alors que le bon passage était récupéré : "
          f"{sum(1 for r in faux_refus if r['rang_hybride'])} (=> problème de génération, pas de recherche)")
    print(f"\n3. HORS CORPUS : refus corrects {pct(sum(r['refus'] for r in rep_hors), len(rep_hors))}")
    print(f"\nTemps moyen par réponse : {sum(r['duree_s'] for r in resultats) / len(resultats):.0f} s")

    with open("eval_resultats.json", "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=1)
    print("Détail de chaque réponse dans eval_resultats.json (à relire à la main).")


if __name__ == "__main__":
    main()
