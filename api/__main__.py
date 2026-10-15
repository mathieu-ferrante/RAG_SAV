"""Lancement de l'API, et gestion des comptes conseillers.

    python -m api                                  # lance l'API
    python -m api --ajouter-conseiller jdupont     # crée le compte (ou change le mot de passe)
    python -m api --supprimer-conseiller jdupont
    python -m api --conseillers                    # liste les comptes

L'API écoute sur API_HOTE:API_PORT (127.0.0.1:8000 par défaut, voir .env).
Documentation interactive : http://127.0.0.1:8000/docs

Le modèle d'embedding (~2 Go) est chargé AVANT d'ouvrir le port : la première
question ne paie pas son chargement, et une installation incomplète échoue au
démarrage plutôt qu'à la première requête.
"""

import sys
from getpass import getpass


def gerer_comptes(argv: list[str]) -> bool:
    """Commandes de comptes. True si l'une a été traitée."""
    from api import comptes

    if "--conseillers" in argv:
        noms = comptes.lister()
        print("\n".join(noms) if noms else "Aucun compte conseiller.")
        return True

    for option in ("--ajouter-conseiller", "--supprimer-conseiller"):
        if option not in argv:
            continue
        index = argv.index(option)
        if index + 1 >= len(argv):
            print(f"{option} attend un identifiant.")
            return True
        identifiant = argv[index + 1]
        if option == "--supprimer-conseiller":
            print("Compte supprimé." if comptes.supprimer(identifiant) else "Compte inconnu.")
            return True
        mot_de_passe = getpass(f"Mot de passe pour {identifiant} : ")
        if mot_de_passe != getpass("Confirmer : "):
            print("Les deux saisies diffèrent : rien n'a été enregistré.")
            return True
        try:
            comptes.ajouter(identifiant, mot_de_passe)
        except ValueError as erreur:
            print(erreur)
            return True
        print(f"Compte conseiller « {identifiant.strip().lower()} » enregistré.")
        return True
    return False


def main(argv: list[str]) -> None:
    if gerer_comptes(argv):
        return

    import uvicorn

    from api.reglages import API_HOTE, API_PORT
    from rag_sav.embeddings import obtenir_modele

    obtenir_modele()
    uvicorn.run("api.routes:app", host=API_HOTE, port=API_PORT)


if __name__ == "__main__":
    main(sys.argv[1:])
