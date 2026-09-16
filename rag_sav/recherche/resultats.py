"""Mise en forme des résultats et diagnostic de la recherche."""

from rag_sav.config import SEUIL_SIMILARITE_PROVISOIRE


def _correspondance_modele(metadata: dict, analyse: dict) -> str:
    """Comment ce passage se rattache-t-il à l'appareil du client ?"""
    couverts = metadata.get("modeles_couverts") or []

    if analyse["modele"] and analyse["modele"] in couverts:
        return "exacte" if metadata.get("portee") == "modele" else "gamme"
    if metadata.get("portee") == "global":
        return "transverse"
    if analyse["gamme"] and metadata.get("gamme") == analyse["gamme"]:
        return "gamme"
    return "non_contrainte"


def formater(ligne: dict, analyse: dict) -> dict:
    metadata = ligne["metadata"] or {}
    similarite = ligne.get("similarite")

    return {
        "id": ligne["id"],
        "page_content": ligne["page_content"],
        "document_source": ligne["document_source"],
        "nom_fichier": metadata.get("nom_fichier", ligne["document_source"]),
        "section_path": metadata.get("section_path", "Général"),
        "modele": metadata.get("modele"),
        "gamme": metadata.get("gamme"),
        "portee": metadata.get("portee"),
        "modeles_couverts": metadata.get("modeles_couverts") or [],
        "code_erreur": metadata.get("code_erreur"),
        # « interne » = bulletin ou procédure SAV : à lire pour être à jour,
        # à ne pas citer tel quel à un client (références de pièces, jargon).
        "audience": metadata.get("audience", "client"),
        "prevaut": bool(ligne.get("prevaut")),
        "correspondance_modele": _correspondance_modele(metadata, analyse),
        # Similarité cosinus réelle, dans [0, 1] : comparable d'une question à
        # l'autre, contrairement à l'ancien pourcentage de confiance qui ne
        # mesurait qu'une position relative dans le top-30 et plafonnait
        # mécaniquement à 52,9 % dès que la branche plein texte était vide.
        "similarite": round(float(similarite), 4) if similarite is not None else None,
        "score_rrf": float(ligne["score_rrf"]),
        "rang_vec": ligne["rang_vec"],
        "rang_fts": ligne["rang_fts"],
        "metadata": metadata,
    }


def diagnostic(analyse: dict, resultats: list[dict], plein_texte: str | None) -> dict:
    """État de santé de la recherche, pour le moteur de réponse et les logs."""
    similarites = [r["similarite"] for r in resultats if r["similarite"] is not None]
    meilleure = max(similarites) if similarites else None

    if analyse["modele"]:
        filtre = f"modele={analyse['modele']}"
    elif analyse["gamme"]:
        filtre = f"gamme={analyse['gamme']}"
    else:
        filtre = "aucun"

    return {
        "filtre_applique": filtre,
        "requete_plein_texte": plein_texte,
        "branche_texte_active": bool(plein_texte),
        "nb_resultats": len(resultats),
        "meilleure_similarite": meilleure,
        "contexte_faible": meilleure is None or meilleure < SEUIL_SIMILARITE_PROVISOIRE,
    }
