"""Point d'entrée : l'assistant SAV, en console.

    python repondre.py                              # vos questions, au clavier
    python repondre.py "mon wx450 affiche e23"      # une question
    python repondre.py --questions-types            # le jeu de recette
    python repondre.py --qualite [--categorie piege] [--pause 4]   # test de qualité
    python repondre.py --modele qwen2.5:7b "..."    # surcharge ponctuelle

Ce que le client lit, c'est LA RÉPONSE rédigée par l'assistant. Les passages de
la documentation qui l'ont fondée ne viennent qu'après, en annexe : ce sont ses
sources, pas la réponse. Pour voir la recherche seule, sans LLM :

    python console.py --passages "mon wx450 affiche e23"
"""

import sys
import time

# Sortie redirigée vers un fichier sous Windows (`> sortie.txt`) : Python écrit
# alors en cp1252, qui ne connaît pas le tiret insécable « ‑ » que les modèles
# mettent dans « WX‑450 ». Un caractère non représentable devient « ? » au lieu
# de faire planter l'assistant en plein milieu d'une réponse.
for _flux in (sys.stdout, sys.stderr):
    if hasattr(_flux, "reconfigure"):
        _flux.reconfigure(errors="replace")

from questions_types import QUESTIONS_TYPES
from rag_sav.generation import repondre
from rag_sav.generation.llm import disponible
from rag_sav.generation.prompt import corps_du_passage

LARGEUR = 78
TAILLE_EXTRAIT = 280

TITRES = {
    "repondu": "RÉPONSE",
    "escalade": "À PRÉCISER / TRANSMIS À UN CONSEILLER",
    "refus": "PAS DE RÉPONSE FIABLE",
    "non_conforme": "RÉPONSE ÉCARTÉE (citations non conformes)",
    "erreur_llm": "ASSISTANT INDISPONIBLE",
}


def _extrait(passage: dict) -> str:
    texte = " ".join(corps_du_passage(passage["page_content"]).split())
    return texte if len(texte) <= TAILLE_EXTRAIT else texte[:TAILLE_EXTRAIT].rstrip() + "…"


def _annexes(resultat: dict) -> None:
    """Les passages consultés — présentés comme les pièces jointes de la réponse."""
    passages = resultat["passages"]
    titre = "passages de la documentation consultés"
    if not passages and resultat.get("candidats"):
        passages = resultat["candidats"]
        titre = "passages les plus proches (NON utilisés pour répondre)"
    if not passages:
        return

    citees = {(s["nom_fichier"], s["section_path"]) for s in resultat["sources"]}
    print(f"\n  {'-' * (LARGEUR - 2)}\n  ANNEXES — {titre}\n")
    for rang, passage in enumerate(passages, start=1):
        cle = (passage["nom_fichier"], passage["section_path"])
        if passage.get("audience", "client") != "client":
            nature = "interne, jamais citée au client"
        elif cle in citees:
            nature = "citée"
        else:
            nature = "consultée"
        print(f"  [{rang}] {passage['nom_fichier']} — {passage['section_path']}")
        similarite = passage.get("similarite")
        print(f"      ({nature} · similarité {similarite if similarite is not None else '-'})")
        if passage.get("audience", "client") == "client":
            print(f"      {_extrait(passage)}")
        else:
            print("      (extrait non affiché : documentation technique interne)")
        print()


def afficher(question: str, **surcharges) -> dict:
    print(f"\n{'=' * LARGEUR}\nQUESTION : « {question} »\n{'=' * LARGEUR}")

    resultat = repondre(question, **surcharges)
    analyse = resultat["analyse"]

    motif = f" [{resultat['motif']}]" if resultat["motif"] else ""
    print(f"\n  >>> {TITRES.get(resultat['statut'], resultat['statut'])}{motif}\n")
    for ligne in resultat["reponse"].splitlines():
        print(f"  {ligne}")

    if resultat["motif"] == "repli_referentiel":
        indisponible = (resultat["reponse_brute"] or "").startswith("(LLM indisponible")
        print(
            "\n  (le modèle est indisponible : réponse tirée du référentiel)"
            if indisponible
            else "\n  (le modèle n'a pas fourni de réponse exploitable : réponse tirée du référentiel)"
        )
        print("  --- réponse du modèle, conservée pour diagnostic ---")
        for ligne in (resultat["reponse_brute"] or "").splitlines():
            print(f"  | {ligne}")

    controle = resultat.get("controle") or {}
    fuites = sorted(set(controle.get("pieces_internes", [])) | set(controle.get("marqueurs_internes", [])))
    if fuites:
        print(f"\n  /!\\ réponse du modèle écartée : elle reprenait du contenu interne ({', '.join(fuites)})")

    if resultat["statut"] == "non_conforme":
        print("\n  --- réponse écartée, conservée pour diagnostic ---")
        for ligne in resultat["reponse_brute"].splitlines():
            print(f"  | {ligne}")
        print(f"  | contrôle : {resultat['controle']}")

    _annexes(resultat)

    # Le détail technique en dernier : utile pour déboguer, pas pour lire.
    print(
        f"  Analyse : code={analyse['code'] or '-'} | "
        f"modèle={analyse['modele'] or '-'} | gamme={analyse['gamme'] or '-'}"
    )
    if resultat["diagnostic"]:
        diag = resultat["diagnostic"]
        print(
            f"  Filtre  : {diag['filtre_applique']} | "
            f"similarité max : {diag['meilleure_similarite']} | "
            f"passages retenus : {len(resultat['passages'])}"
        )
    if resultat["llm"]:
        llm = resultat["llm"]
        print(
            f"  LLM     : {llm['fournisseur']}/{llm['modele']} — {llm['duree_s']} s"
            f" | jetons {llm['jetons_prompt']} -> {llm['jetons_reponse']}"
            f" ({llm['jetons_par_seconde']} j/s)"
        )

    return resultat


def boucle_interactive(**surcharges) -> None:
    print("\n=== ASSISTANT SAV (« q » pour quitter) ===")
    while True:
        try:
            saisie = input("\nVotre question SAV : ").strip()
            if not saisie or saisie.lower() in ("exit", "quit", "q"):
                break
            afficher(saisie, **surcharges)
        except (KeyboardInterrupt, EOFError):
            break


def _lire_arguments(argv: list[str]) -> tuple[dict, str | None, dict]:
    surcharges, mots = {}, []
    options = {"recette": False, "qualite": False, "categorie": None, "pause": 3.0}
    index = 0
    while index < len(argv):
        jeton = argv[index]
        if jeton in ("--modele", "--fournisseur", "--url") and index + 1 < len(argv):
            surcharges[jeton.lstrip("-")] = argv[index + 1]
            index += 2
        elif jeton == "--categorie" and index + 1 < len(argv):
            options["categorie"] = argv[index + 1]
            index += 2
        elif jeton == "--pause" and index + 1 < len(argv):
            try:
                options["pause"] = max(0.0, float(argv[index + 1].replace(",", ".")))
            except ValueError:
                print(f"--pause attend un nombre de secondes (reçu « {argv[index + 1]} ») : 3 s retenues.")
            index += 2
        elif jeton == "--questions-types":
            options["recette"] = True
            index += 1
        elif jeton == "--qualite":
            options["qualite"] = True
            index += 1
        else:
            mots.append(jeton)
            index += 1
    return surcharges, " ".join(mots) or None, options


def _verdict(resultat: dict, acceptes: tuple) -> str:
    statut = resultat["statut"]
    repli = resultat.get("motif") == "repli_referentiel"
    ok = "OK   " if statut in acceptes else "ÉCART"
    return ok + (" (repli référentiel)" if repli else "")


def passer_qualite(categorie: str | None, pause: float, surcharges: dict) -> None:
    from questions_qualite import CATEGORIES, QUESTIONS_QUALITE

    if categorie and categorie not in CATEGORIES:
        print(f"Catégorie inconnue : {categorie}. Choix : {', '.join(CATEGORIES)}")
        return
    jeu = [q for q in QUESTIONS_QUALITE if not categorie or q[0] == categorie]
    bilan = []
    for numero, (cat, question, acceptes, attendu) in enumerate(jeu):
        if numero and pause:
            time.sleep(pause)
        print(f"\n[{cat}] ATTENDU : {attendu}")
        print(f"          statut accepté : {' ou '.join(acceptes)}")
        resultat = afficher(question, **surcharges)
        bilan.append((cat, question, resultat["statut"], _verdict(resultat, acceptes)))

    print(f"\n{'=' * LARGEUR}\nBILAN QUALITÉ ({len(bilan)} questions)\n{'=' * LARGEUR}")
    for cat, question, statut, verdict in bilan:
        print(f"  {verdict:<24} {cat:<17} {statut:<12} {question[:60]}")
    bons = sum(1 for b in bilan if b[3].startswith("OK"))
    print(f"\n  {bons}/{len(bilan)} statuts conformes. Le CONTENU des réponses "
          "se juge à l'œil avec les lignes ATTENDU.")


def main(argv: list[str]) -> None:
    surcharges, question, options = _lire_arguments(argv)

    if not disponible(surcharges.get("fournisseur"), surcharges.get("url")):
        print(
            "/!\\ Le service LLM ne répond pas. Vérifier qu'Ollama tourne "
            "(`ollama list`) ou les variables FOURNISSEUR_LLM / URL_LLM / "
            "CLE_API_LLM du .env.\n"
        )

    if options["qualite"]:
        passer_qualite(options["categorie"], options["pause"], surcharges)
    elif options["recette"]:
        for questionnaire in QUESTIONS_TYPES:
            afficher(questionnaire, **surcharges)
    elif question:
        afficher(question, **surcharges)
    else:
        boucle_interactive(**surcharges)


if __name__ == "__main__":
    main(sys.argv[1:])
