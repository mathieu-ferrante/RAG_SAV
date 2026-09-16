"""Comprendre la question : quel code erreur, quel modèle, quelle gamme."""

import re

from rag_sav.catalogue import (
    detecter_gamme_par_mots,
    extraire_codes_erreur,
    extraire_references,
    gamme_de_la_reference,
    gamme_du_modele,
    modele_par_numero,
    normaliser_texte,
)

STOPWORDS_FR = {
    "le", "la", "les", "un", "une", "des", "et", "ou", "de", "du", "à", "en",
    "que", "qui", "quoi", "dont", "où", "ce", "cette", "ces", "je", "tu", "il",
    "elle", "nous", "vous", "ils", "elles", "mon", "ton", "son", "sa", "ses",
    "ma", "ta", "mes", "tes", "nos", "vos", "leurs", "aux", "par", "pour",
    "sur", "sous", "dans", "avec", "sans", "est", "sont", "ont", "suis", "es",
    "fait", "faire", "veux", "dire", "ça", "affiche", "s'affiche", "comment",
    "fais", "sortir", "men", "stp", "perdu", "merde", "chui", "bonjour",
    "merci", "svp", "problème", "probleme", "appareil", "machine",
}

MOTIF_MOT = re.compile(r"\b[a-zA-Z0-9à-ÿÀ-Ÿ]+\b")
MOTIF_REPETITION = re.compile(r"(.)\1{3,}")  # « aaaah », « hellooooo »

# --- Numéro seul : « mon lave-linge 450 » -----------------------------------
#
# Beaucoup de clients ne donnent que le numéro, la gamme étant dite en clair.
# On ne s'y risque QUE si la gamme est connue par ailleurs et que le numéro
# désigne un modèle existant de cette gamme — plus les deux garde-fous
# ci-dessous, sans lesquels « page 450 » ou « 450 euros » deviendraient des
# références d'appareil.

MOTIF_NUMERO_SEUL = re.compile(r"(?<![a-z0-9\-_/.])(\d{3,4})(?![a-z0-9])")

_AVANT = (
    r"page|pages|ligne|lignes|article|articles|chapitre|section|paragraphe"
    r"|figure|tableau|annexe|numero|num|no|ref|reference|facture|commande"
    r"|devis|dossier|tel|telephone|depuis|environ|code|erreur|euros?|watts?"
    r"|n"
)
_APRES = (
    r"euros?|eur|e|ans?|mois|jours?|semaines?|heures?|h|min|minutes?|secondes?"
    r"|watts?|w|kw|tr|tours?|degres?|km|kg|g|ml|cl|l|cm|mm|m|fois|personnes?|%"
)

MOTIF_AVANT_NUMERO = re.compile(rf"\b(?:{_AVANT})\W{{0,3}}$")
MOTIF_APRES_NUMERO = re.compile(rf"^\W{{0,3}}(?:{_APRES})\b")


def _resoudre_numero_seul(question_normalisee: str, gamme: str | None) -> str | None:
    """« mon lave-linge 450 » + gamme WX -> « WX-450 ». None si rien de sûr."""
    if not gamme:
        return None

    for correspondance in MOTIF_NUMERO_SEUL.finditer(question_normalisee):
        modele = modele_par_numero(gamme, correspondance.group(1))
        if not modele:
            continue
        if MOTIF_AVANT_NUMERO.search(question_normalisee[: correspondance.start()]):
            continue
        if MOTIF_APRES_NUMERO.match(question_normalisee[correspondance.end():]):
            continue
        return modele

    return None


def analyser_question(question: str) -> dict:
    """Extrait tout ce qui permettra de contraindre la recherche.

    >>> analyser_question("mon lave-vaisselle lv200 affiche E23")["modele"]
    'LV-200'
    >>> analyser_question("mon lave-linge 450 affiche e 23")["modele"]
    'WX-450'
    """
    normalisee = normaliser_texte(question)

    codes = extraire_codes_erreur(question)
    references = extraire_references(question)
    modeles, inconnus = references["modeles"], references["inconnus"]

    # Un seul modèle cité : on peut contraindre au modèle près.
    modele = modeles[0] if len(modeles) == 1 else None
    origine_modele = "reference" if modele else None

    if modele:
        gamme, origine = gamme_du_modele(modele), "modele"
    else:
        gammes = {gamme_du_modele(m) for m in modeles}
        if len(gammes) == 1:
            gamme, origine = gammes.pop(), "modeles"
        elif inconnus:
            # « WX-460 » : le modèle est inconnu, la gamme ne l'est pas.
            # On retient la gamme ; l'escalade décidera s'il faut le dire.
            gammes = {gamme_de_la_reference(r) for r in inconnus}
            gamme = gammes.pop() if len(gammes) == 1 else None
            origine = "reference_inconnue" if gamme else None
        else:
            # Pas de référence : on se rabat sur le vocabulaire (« mon four »).
            gamme = detecter_gamme_par_mots(question)
            origine = "vocabulaire" if gamme else None

            # Gamme dite en clair, numéro donné seul : « mon lave-linge 450 ».
            candidat = _resoudre_numero_seul(normalisee, gamme)
            if candidat:
                modele, origine_modele = candidat, "numero_seul"
                modeles = [candidat]

    return {
        "question": question,
        "codes": codes,
        "code": codes[0] if codes else None,
        "modeles": modeles,
        "modele": modele,
        # Référence bien formée mais absente du catalogue (« WX-460 ») : on ne
        # la jette plus en silence, l'escalade peut la nommer au client.
        "modeles_inconnus": inconnus,
        "origine_modele": origine_modele,
        "gamme": gamme,
        "origine_gamme": origine,
    }


def preparer_requete_plein_texte(analyse: dict) -> str | None:
    """Construit la requête plein texte. Le modèle n'y figure plus.

    C'est LE changement central : PostgreSQL indexe « LV-200 » en 'lv' + '-200'
    (tiret compris), donc la requête « e23 & lv & 200 » ne pouvait jamais
    correspondre. Le modèle est désormais une métadonnée filtrée en SQL ; le
    plein texte ne s'occupe que du vocabulaire.

    None si rien d'exploitable : la recherche se fera alors sur la seule
    branche vectorielle, ce qui est signalé dans le diagnostic.
    """
    if analyse["codes"]:
        return " | ".join(code.lower() for code in analyse["codes"])

    mots = [
        mot
        for mot in MOTIF_MOT.findall(analyse["question"].lower())
        if mot not in STOPWORDS_FR and len(mot) > 2 and not MOTIF_REPETITION.search(mot)
    ]
    uniques = list(dict.fromkeys(mots))
    return " | ".join(uniques) if uniques else None
