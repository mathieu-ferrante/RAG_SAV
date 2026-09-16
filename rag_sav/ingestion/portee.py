"""Portée documentaire : à quel(s) appareil(s) un document s'applique.

C'est la métadonnée qui tient la contrainte « exactitude au modèle près ».
Sans elle, aucun filtrage n'est possible. Voir README.md.
"""

from datetime import datetime
from pathlib import Path

from rag_sav.catalogue import (
    detecter_gamme_isolee,
    detecter_gamme_par_mots,
    extraire_modeles,
    gamme_du_modele,
    modeles_de_la_gamme,
)

# Catégories dont le contenu s'adresse aux conseillers et techniciens, pas au
# client final (mention « documentation interne », références de pièces).
# L'assistant les LIT — un bulletin prévaut sur le manuel — mais ne les cite pas
# tels quels : c'est le prompt de génération qui porte cette règle.
CATEGORIES_INTERNES = {"Bulletins_techniques", "Procedures_SAV"}

# Un bulletin technique prévaut explicitement sur les manuels et le référentiel
# pour les points qu'il traite (cf. BT-2026-011).
PRIORITE_PAR_CATEGORIE = {"Bulletins_techniques": 10}


def date_fichier(chemin: Path) -> str:
    """Date de dernière modification, au format YYYY-MM-DD."""
    return datetime.fromtimestamp(chemin.stat().st_mtime).strftime("%Y-%m-%d")


def determiner_portee(chemin: Path, texte: str = "") -> dict:
    """Renvoie toujours les mêmes clés, par ordre de fiabilité décroissante.

    portee = "modele"  un ou plusieurs modèles précis (Manuel_WX-450.pdf,
                       bulletin technique visant le FR-700)
    portee = "gamme"   toute une gamme (PROC-WX-01, faq-lave-linge.html)
    portee = "global"  s'applique à tout (CGV)

    « modeles_couverts » est TOUJOURS une liste : c'est elle qui sera
    interrogée en base.
    """
    nom = chemin.stem

    # 1. Un modèle du catalogue dans le nom du fichier — le cas le plus sûr.
    modeles = extraire_modeles(nom)

    if not modeles:
        # 2. Une gamme dans le nom du fichier (PROC-WX-01, Gamme_WX).
        code_gamme = detecter_gamme_isolee(nom)
        if code_gamme:
            return _portee_gamme(code_gamme)

        # 3. Le produit nommé en clair (faq-lave-linge.html).
        code_gamme = detecter_gamme_par_mots(nom)
        if code_gamme:
            return _portee_gamme(code_gamme)

        # 4. Des modèles cités dans le CONTENU. Cas des bulletins techniques :
        #    BT-2026-007 vise le WX-500, mais son nom de fichier ne le dit pas.
        modeles = extraire_modeles(texte)

    if modeles:
        gammes = {gamme_du_modele(m) for m in modeles}
        return {
            "portee": "modele",
            "modele": modeles[0] if len(modeles) == 1 else None,
            "gamme": gammes.pop() if len(gammes) == 1 else None,
            "modeles_couverts": modeles,
        }

    # 5. Rien trouvé : document transverse (CGV).
    return {"portee": "global", "modele": None, "gamme": None, "modeles_couverts": []}


def _portee_gamme(code_gamme: str) -> dict:
    """Un document de gamme couvre TOUS les modèles de cette gamme."""
    return {
        "portee": "gamme",
        "modele": None,
        "gamme": code_gamme,
        "modeles_couverts": modeles_de_la_gamme(code_gamme),
    }


def metadonnees_communes(chemin: Path, categorie: str, texte: str = "") -> dict:
    """Socle de métadonnées posé sur tout document, quel que soit son format."""
    base = {
        "source": str(chemin),
        "nom_fichier": chemin.name,
        "categorie": categorie,
        "date_modification": date_fichier(chemin),
        "audience": "interne" if categorie in CATEGORIES_INTERNES else "client",
        "priorite": PRIORITE_PAR_CATEGORIE.get(categorie, 0),
    }
    base.update(determiner_portee(chemin, texte))
    return base
