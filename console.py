"""Point d'entrée : l'assistant SAV en console.

    python console.py                              # vos questions, au clavier
    python console.py "mon wx450 affiche e23"      # une question
    python console.py --questions-types            # le jeu de recette
    python console.py --modele qwen2.5:7b "..."    # surcharge ponctuelle du LLM
    python console.py --passages "..."             # la RECHERCHE seule, sans LLM
    python console.py --conseiller "..."           # profil conseiller : doc interne citable

Ce que le client lit, c'est LA RÉPONSE rédigée par l'assistant. Les passages de
la documentation qui l'ont fondée ne viennent qu'après, en annexe : ce sont ses
sources, pas la réponse. `--passages` montre la recherche seule (classement,
correspondance au modèle, rangs), pour déboguer.

Pour servir l'assistant à d'autres applications : `python -m api` (API REST).
"""

import sys

# Sortie redirigée vers un fichier sous Windows (`> sortie.txt`) : Python écrit
# alors en cp1252, qui ne connaît pas le tiret insécable « ‑ » que les modèles
# mettent dans « WX‑450 ». Un caractère non représentable devient « ? » au lieu
# de faire planter l'assistant en plein milieu d'une réponse.
for _flux in (sys.stdout, sys.stderr):
    if hasattr(_flux, "reconfigure"):
        _flux.reconfigure(errors="replace")

LARGEUR = 78
TAILLE_EXTRAIT = 280

# Jeu de recette : vérifie d'un coup que les règles d'escalade, le filtre dur
# et le verrou réagissent comme prévu. Ce ne sont pas des questions client.
QUESTIONS_TYPES = [
    # Le cas nominal : code + appareil, deux gammes différentes pour le même code.
    "Mon lave-vaisselle LV-200 affiche le code erreur E23",
    "Mon lave-linge WX-450 affiche E23",
    # Un bulletin technique interne prévaut : un conseiller reprend la main.
    "mon wx500 affiche e52",
    # Question de procédure, sans code erreur.
    "Comment détartrer mon lave-linge WX-400 ?",
    # Question transverse, sans appareil : doit répondre depuis les CGV.
    "Quelle est la durée de la garantie ?",
    # Écritures libres : éprouvent la détection souple.
    "Modele LV verre marqués",
    "bonjour mon lave-linge 450 affiche e 23",
    # Les escalades attendues.
    "Que signifie le code E23 ?",            # code ambigu sans appareil
    "j'ai un WX-460, code E23",              # référence hors catalogue
    "voir page 450 du manuel, code F12",     # code inconnu de la documentation
    "Mon WX-450 affiche E15",                # code d'une autre gamme
    "j'ai le code E77 qui s'affiche",        # code sans appareil
]

TITRES = {
    "repondu": "RÉPONSE",
    "escalade": "À PRÉCISER / TRANSMIS À UN CONSEILLER",
    "refus": "PAS DE RÉPONSE FIABLE",
    "non_conforme": "RÉPONSE ÉCARTÉE (citations non conformes)",
    "erreur_llm": "ASSISTANT INDISPONIBLE",
}


# ---------------------------------------------------------------------------
# L'assistant : réponse, puis annexes
# ---------------------------------------------------------------------------

def _extrait(passage: dict) -> str:
    from rag_sav.generation.prompt import corps_du_passage

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
        if passage.get("audience_origine", "client") != "client":
            nature += " · documentation interne"
        print(f"  [{rang}] {passage['nom_fichier']} — {passage['section_path']}")
        similarite = passage.get("similarite")
        print(f"      ({nature} · similarité {similarite if similarite is not None else '-'})")
        if passage.get("audience", "client") == "client":
            print(f"      {_extrait(passage)}")
        else:
            print("      (extrait non affiché : documentation technique interne)")
        print()


def afficher(question: str, **surcharges) -> dict:
    from rag_sav.generation import repondre

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


# ---------------------------------------------------------------------------
# --passages : la recherche seule, sans LLM
# ---------------------------------------------------------------------------

def afficher_passages(question: str, top_k: int = 5) -> None:
    from rag_sav.recherche import rechercher

    print(f"\n{'=' * LARGEUR}\nQUESTION : « {question} »\n{'=' * LARGEUR}")

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
        print(f"    {extrait[:160]}...\n{'-' * LARGEUR}")


# ---------------------------------------------------------------------------
# Lancement
# ---------------------------------------------------------------------------

def boucle_interactive(traiter) -> None:
    print("\n=== ASSISTANT SAV (« q » pour quitter) ===")
    while True:
        try:
            saisie = input("\nVotre question SAV : ").strip()
            if not saisie or saisie.lower() in ("exit", "quit", "q"):
                break
            traiter(saisie)
        except (KeyboardInterrupt, EOFError):
            break


def _lire_arguments(argv: list[str]) -> tuple[dict, str | None, dict]:
    surcharges, mots = {}, []
    options = {"recette": False, "passages": False}
    index = 0
    while index < len(argv):
        jeton = argv[index]
        if jeton in ("--modele", "--fournisseur", "--url") and index + 1 < len(argv):
            surcharges[jeton.lstrip("-")] = argv[index + 1]
            index += 2
        elif jeton == "--questions-types":
            options["recette"] = True
            index += 1
        elif jeton == "--conseiller":
            surcharges["profil"] = "conseiller"
            index += 1
        elif jeton == "--passages":
            options["passages"] = True
            index += 1
        else:
            mots.append(jeton)
            index += 1
    return surcharges, " ".join(mots) or None, options


def main(argv: list[str]) -> None:
    surcharges, question, options = _lire_arguments(argv)

    if options["passages"]:
        traiter = afficher_passages
    else:
        from rag_sav.generation.llm import disponible

        if not disponible(surcharges.get("fournisseur"), surcharges.get("url")):
            print(
                "/!\\ Le service LLM ne répond pas. Vérifier qu'Ollama tourne "
                "(`ollama list`) ou les variables FOURNISSEUR_LLM / URL_LLM / "
                "CLE_API_LLM du .env.\n"
            )

        def traiter(texte: str) -> None:
            afficher(texte, **surcharges)

    if options["recette"]:
        for questionnaire in QUESTIONS_TYPES:
            traiter(questionnaire)
    elif question:
        traiter(question)
    else:
        boucle_interactive(traiter)


if __name__ == "__main__":
    main(sys.argv[1:])
