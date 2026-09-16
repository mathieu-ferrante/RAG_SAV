"""Point d'entrée : tester la recherche à la main.

    python console.py                          # jeu de questions types puis mode interactif
    python console.py "mon wx450 affiche e23"  # une question
"""

import sys

from rag_sav.recherche import rechercher

QUESTIONS_TYPES = [
    "Mon lave-vaisselle LV-200 affiche le code erreur E23",
    "Mon lave-linge WX-450 affiche E23",
    "Que signifie le code E23 ?",
    "mon wx500 affiche e52",
    "Comment détartrer mon lave-linge WX-400 ?",
    "Modele LV verre marqués",
    "bonjour mon lave-linge 450 affiche e 23",   # écriture libre
    "j'ai un WX-460, code E23",                  # référence hors catalogue
    "voir page 450 du manuel, code F12",         # code hors documentation
    "j'ai le code E77 qui s'affiche",            # code sans appareil
]


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
    if len(sys.argv) > 1:
        afficher(" ".join(sys.argv[1:]))
    else:
        for question in QUESTIONS_TYPES:
            afficher(question, top_k=3)
        boucle_interactive()
