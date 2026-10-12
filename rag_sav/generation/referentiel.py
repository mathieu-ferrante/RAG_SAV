"""Répondre sans LLM quand le référentiel répond déjà.

Le référentiel des codes erreur est découpé ligne par ligne (`decoupage =
"atomique"`) et chaque ligne porte une rédaction client toute faite :

    ## Code E23 — Sonde de température défectueuse
    - **Gamme :** LV (Lave-vaisselle)
    - **Modèles concernés :** LV-100, LV-150, LV-200, …
    - **Signification :** Sonde de température défectueuse
    - **Conduite à tenir (client) :** Contacter le SAV. Le lavage a
      température élevée est indisponible en attendant l'intervention.
    - **Intervention SAV (technicien) :** Remplacer la sonde CTN (pièce 51-0790).

Quand la question donne un code ET un appareil, et que le référentiel couvre
le couple, faire rédiger cette phrase par un modèle probabiliste n'apporte
rien et coûte tout : 15 à 30 secondes, une hallucination possible, une
citation à vérifier. C'est la même logique que le filtre dur — **ce qui est
structuré ne se devine pas.**

Le LLM garde son vrai rôle : les questions de procédure, de garantie et les
formulations libres, là où il faut synthétiser plusieurs passages.

Deux garde-fous :

  - la colonne « Intervention SAV (technicien) » n'est JAMAIS reprise : elle
    porte les références de pièces et s'adresse au technicien ;
  - si un passage retenu **fait autorité** (bulletin technique récent), on
    laisse la main au LLM : le bulletin prévaut sur le référentiel, et c'est
    justement le cas que ce raccourci ne sait pas traiter.
"""

import re

MOTIF_CHAMP = "- **{champ} :**"

CHAMP_CONDUITE = "Conduite à tenir (client)"
CHAMP_SIGNIFICATION = "Signification"


def _champ(texte: str, champ: str) -> str | None:
    """Valeur d'un champ de la ligne de référentiel, sans le gras markdown.

    Le champ se termine à la puce suivante ou à la fin du passage : une
    conduite à tenir peut courir sur deux lignes.
    """
    debut = texte.find(MOTIF_CHAMP.format(champ=champ))
    if debut == -1:
        return None

    reste = texte[debut + len(MOTIF_CHAMP.format(champ=champ)):]
    fin = reste.find("\n- **")
    valeur = (reste if fin == -1 else reste[:fin]).strip()
    # Une ligne de version en italique peut suivre le dernier champ.
    valeur = re.split(r"\n\*[^*]", valeur)[0].strip()
    return " ".join(valeur.split()) or None


def _ligne_du_code(passages: list[dict], code: str, modele: str) -> dict | None:
    """La ligne de référentiel qui traite CE code pour CET appareil."""
    for passage in passages:
        metadata = passage.get("metadata") or {}
        if metadata.get("decoupage") != "atomique":
            continue
        if (passage.get("code_erreur") or metadata.get("code_erreur")) != code:
            continue
        if passage.get("audience", "client") != "client":
            continue
        if modele not in (passage.get("modeles_couverts") or []):
            continue
        if _champ(passage.get("page_content") or "", CHAMP_CONDUITE):
            return passage
    return None


def reponse_directe(analyse: dict, passages: list[dict]) -> dict | None:
    """La réponse tirée du référentiel, ou None s'il ne couvre pas le cas.

    Rend la même forme que la génération : un texte prêt à afficher et la
    liste des sources, pour que l'appelant n'ait pas à savoir d'où vient la
    réponse.
    """
    code, modele = analyse.get("code"), analyse.get("modele")
    if not code or not modele:
        return None

    # Un bulletin technique prévaut sur le référentiel : ce raccourci ne sait
    # pas arbitrer, il s'efface.
    if any(passage.get("prevaut") for passage in passages):
        return None

    ligne = _ligne_du_code(passages, code, modele)
    if ligne is None:
        return None

    contenu = ligne.get("page_content") or ""
    conduite = _champ(contenu, CHAMP_CONDUITE)
    signification = _champ(contenu, CHAMP_SIGNIFICATION) or (
        (ligne.get("metadata") or {}).get("signification")
    )

    entete = f"Le code {code} sur votre appareil {modele}"
    entete += f" signale : {signification}." if signification else "."

    texte = (
        f"{entete}\n\n{conduite}\n\n"
        f"Sources :\n- {ligne['nom_fichier']} — {ligne['section_path']}"
    )

    return {
        "texte": texte,
        "sources": [
            {"nom_fichier": ligne["nom_fichier"], "section_path": ligne["section_path"]}
        ],
    }
