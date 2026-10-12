"""Point d'entrée : l'assistant SAV en console, ou la recherche seule.

    python console.py                          # l'assistant : une réponse, puis ses annexes
    python console.py "mon wx450 affiche e23"  # une question
    python console.py --questions-types        # le jeu de recette

    python console.py --passages ...           # la RECHERCHE seule, sans LLM :
                                               # les passages classés, pour déboguer

Sans `--passages`, ce point d'entrée est identique à `python repondre.py`.
"""

import sys

# Sortie redirigée vers un fichier sous Windows (`> sortie.txt`) : Python écrit
# alors en cp1252, qui ne connaît pas le tiret insécable « ‑ » que les modèles
# mettent dans « WX‑450 ». Un caractère non représentable devient « ? » au lieu
# de faire planter l'assistant en plein milieu d'une réponse.
for _flux in (sys.stdout, sys.stderr):
    if hasattr(_flux, "reconfigure"):
        _flux.reconfigure(errors="replace")

from questions_types import QUESTIONS_TYPES
from rag_sav.recherche import rechercher

def afficher(question: str, top_k: int = 5) -> None:
    print(f"\n{'=' * 78}\nQUESTION : « {question} »\n{'=' * 78}")

    reponse = rechercher(question, top_k=top_k)
    analyse = reponse["analyse"]

    origine_modele = f" ({analyse['origine_modele']})" if analyse["origine_modele"] else ""
    print(
        f"  Analyse  : code={analyse['code'] or '-'} | "
        f"modèle={analyse['modele'] or '-'}{origine_modele} | "
        f"gamme={analyse['gamme'] or '-'} ({analyse['origine_gamme'] or 'non détectée'})"
    )
    if analyse["modeles_inconnus"]:
        print(f"  /!\\ Référence(s) hors catalogue : {', '.join(analyse['modeles_inconnus'])}")

    if reponse["escalade"]:
        print(f"\n  >>> ESCALADE [{reponse['escalade']['motif']}]")
        print(f"  >>> {reponse['escalade']['message']}")
        return

    diag = reponse["diagnostic"]
    print(
        f"  Filtre   : {diag['filtre_applique']} | "
        f"plein texte : {diag['requete_plein_texte'] or 'inactif'} | "
        f"meilleure similarité : {diag['meilleure_similarite']}"
    )
    if diag["contexte_faible"]:
        print("  /!\\ Contexte faible : aucun passage vraiment proche de la question.")

    if not reponse["resultats"]:
        print("\n  Aucun résultat.")
        return

    print()
    for rang, res in enumerate(reponse["resultats"], start=1):
        drapeau = " [PRÉVAUT]" if res["prevaut"] else ""
        print(
            f"[{rang}] {res['nom_fichier']} — {res['section_path']}{drapeau}\n"
            f"    correspondance : {res['correspondance_modele']} | "
            f"similarité : {res['similarite']} | "
            f"rangs vec/texte : {res['rang_vec']}/{res['rang_fts']} | "
            f"audience : {res['audience']}"
        )
        extrait = res["page_content"].split("\n\n", 1)[-1].replace("\n", " ")
        print(f"    {extrait[:160]}...\n{'-' * 78}")


def boucle_interactive() -> None:
    print("\n=== MODE INTERACTIF (« q » pour quitter) ===")
    while True:
        try:
            saisie = input("\nVotre question SAV : ").strip()
            if not saisie or saisie.lower() in ("exit", "quit", "q"):
                break
            afficher(saisie)
        except (KeyboardInterrupt, EOFError):
            break


if __name__ == "__main__":
    arguments = sys.argv[1:]

    if "--passages" not in arguments:
        from repondre import main

        main(arguments)
        sys.exit(0)

    arguments = [a for a in arguments if a != "--passages"]
    if "--questions-types" in arguments:
        for question in QUESTIONS_TYPES:
            afficher(question, top_k=3)
    elif arguments:
        afficher(" ".join(arguments))
    else:
        boucle_interactive()
