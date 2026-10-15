"""Règles d'escalade : quand refuser de répondre.

Aucune de ces règles ne repose sur un score. Elles sont déterministes,
reproductibles et explicables à un auditeur — c'est ce qu'exige la contrainte
client « escalader explicitement plutôt qu'inventer ».

Les règles sont évaluées dans l'ordre, du message le plus précis au plus
général. La première qui se déclenche gagne : un client qui a donné une
référence hors catalogue doit s'entendre dire ça, et pas « donnez-moi votre
référence ».

Ce que le filtre dur ne peut pas garantir, c'est le cas où il n'a RIEN à
filtrer — un code posé sans appareil, ou un code que personne ne documente.
C'est ce trou que ferment les deux dernières règles.
"""

from rag_sav.catalogue import (
    gamme_de_la_reference,
    libelle_gamme,
    modeles_de_la_gamme,
)

# `curseur` est importé DANS les deux fonctions qui interrogent la base (R8) :
# les règles elles-mêmes sont de la logique pure et doivent pouvoir être
# testées, et appelées par le jeu d'évaluation, sans PostgreSQL.

# ---------------------------------------------------------------------------
# Ce que la documentation connaît réellement
# ---------------------------------------------------------------------------

REQUETE_CODES_REFERENTIEL = """
SELECT metadata->>'code_erreur'               AS code,
       array_agg(DISTINCT metadata->>'gamme') AS gammes
FROM chunks
WHERE metadata->>'code_erreur' IS NOT NULL
  AND metadata->>'gamme' IS NOT NULL
GROUP BY 1;
"""

# Bornes non alphanumériques : « E52 » ne doit pas correspondre dans « E520 »
# ni dans « BASE52 ».
REQUETE_CODE_DANS_LE_TEXTE = """
SELECT EXISTS (
    SELECT 1 FROM chunks
    WHERE page_content ~* ('(^|[^a-z0-9])' || %(code)s || '([^a-z0-9]|$)')
) AS present;
"""

_cache_referentiel: dict[str, list[str]] | None = None
_cache_codes_connus: dict[str, bool] = {}
_cache_codes_appareil: dict[tuple, bool] = {}


def codes_referentiel(relire: bool = False) -> dict[str, list[str]]:
    """Tous les codes du référentiel indexé, et les gammes qui les portent.

    Cette liste n'est pas écrite en dur : elle est déduite du référentiel tel
    qu'il est réellement indexé. Si Electrodomus livre demain un référentiel
    modifié, l'escalade suit automatiquement.

    Exemple : {'E01': ['LV','WX'], 'E15': ['LV'], 'E23': ['LV','WX'], …}
    """
    from rag_sav.stockage.connexion import curseur

    global _cache_referentiel
    if _cache_referentiel is None or relire:
        with curseur() as cur:
            cur.execute(REQUETE_CODES_REFERENTIEL)
            _cache_referentiel = {
                ligne["code"]: sorted(ligne["gammes"]) for ligne in cur.fetchall()
            }
    return _cache_referentiel


def codes_ambigus(relire: bool = False) -> dict[str, list[str]]:
    """Codes dont la signification dépend de la gamme (portés par plusieurs).

    E23 = pompe de vidange sur un lave-linge, sonde de température sur un
    lave-vaisselle. Sans le modèle ni la gamme, toute réponse est un pari.
    """
    return {
        code: gammes
        for code, gammes in codes_referentiel(relire).items()
        if len(gammes) > 1
    }


def code_connu(code: str) -> bool:
    """Ce code existe-t-il quelque part dans la documentation ?

    Pas seulement dans le référentiel : E52 n'est traité que par le bulletin
    BT-2026-007, et ne doit pas déclencher d'escalade pour autant. Un code est
    déclaré inconnu seulement s'il n'apparaît NI dans le référentiel, NI dans
    le texte d'aucun chunk.
    """
    if code in codes_referentiel():
        return True
    if code not in _cache_codes_connus:
        from rag_sav.stockage.connexion import curseur

        with curseur() as cur:
            cur.execute(REQUETE_CODE_DANS_LE_TEXTE, {"code": code})
            _cache_codes_connus[code] = bool(cur.fetchone()["present"])
    return _cache_codes_connus[code]


def code_documente_pour_appareil(code: str, analyse: dict) -> bool:
    """Ce code apparaît-il dans la documentation VISIBLE pour cet appareil ?

    Visible = ce que le filtre dur de la recherche laisse passer pour ce
    modèle (ou cette gamme), documentation interne comprise. C'est la même
    clause que `requete.clause_filtre()` : la règle et la recherche voient
    exactement le même périmètre.

    Mesuré le 12/10 sur les 252 couples modèle × code : les 132 codes d'une
    autre gamme sont absents de toute la documentation visible, les 120 codes
    de la gamme y sont tous. La séparation est parfaite, la règle est sûre.
    """
    from rag_sav.recherche.requete import clause_filtre
    from rag_sav.stockage.connexion import curseur

    filtre, parametres = clause_filtre(analyse)
    cle = (code, analyse.get("modele"), analyse.get("gamme"))
    if cle not in _cache_codes_appareil:
        with curseur() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM chunks WHERE " + filtre +
                " AND page_content ~* ('(^|[^a-z0-9])' || %(code)s || '([^a-z0-9]|$)'))"
                " AS present;",
                {"code": code, **parametres},
            )
            _cache_codes_appareil[cle] = bool(cur.fetchone()["present"])
    return _cache_codes_appareil[cle]


def vider_cache() -> None:
    """À appeler après une réindexation."""
    global _cache_referentiel
    _cache_referentiel = None
    _cache_codes_connus.clear()
    _cache_codes_appareil.clear()


# ---------------------------------------------------------------------------
# Les règles
# ---------------------------------------------------------------------------

def _plusieurs_modeles(analyse: dict) -> dict | None:
    """Répondre pour l'un des deux au hasard serait la faute grave à éviter."""
    if len(analyse["modeles"]) <= 1:
        return None
    return {
        "motif": "plusieurs_modeles",
        "message": (
            f"Votre message mentionne plusieurs appareils "
            f"({', '.join(analyse['modeles'])}). "
            "Pour quel appareil souhaitez-vous de l'aide ?"
        ),
    }


def _reference_inconnue(analyse: dict) -> dict | None:
    """Le client a donné une référence bien formée, absente du catalogue.

    Sans cette règle, « j'ai un WX-460 » était jeté en silence : le client
    s'entendait redemander une référence qu'il venait de donner, ou pire,
    recevait une réponse valable pour toute la gamme sans que personne ne
    signale que sa référence est inconnue.
    """
    if analyse["modele"] or not analyse.get("modeles_inconnus"):
        return None

    reference = analyse["modeles_inconnus"][0]
    gamme = gamme_de_la_reference(reference)
    exemples = ", ".join(modeles_de_la_gamme(gamme)[:2])

    return {
        "motif": "reference_inconnue",
        "message": (
            f"La référence {reference} ne figure pas dans notre catalogue "
            f"{libelle_gamme(gamme).lower()}. Pouvez-vous la vérifier sur "
            f"l'étiquette signalétique de l'appareil ? "
            f"Elle ressemble à {exemples}."
        ),
        "reference_signalee": reference,
    }


def _code_inconnu(analyse: dict) -> dict | None:
    """R1a — le code n'existe nulle part dans la documentation.

    Cas de « voir page 450 du manuel, code F12 ». Auparavant la recherche
    partait quand même et remontait le passage le moins éloigné : une réponse
    arbitraire présentée comme une réponse. Un code que personne ne documente
    n'est pas une question à laquelle l'assistant peut répondre.

    Cette règle s'applique MÊME si le modèle est connu : un WX-450 qui affiche
    E99 pose une question sans réponse documentée.
    """
    code = analyse["code"]
    if not code or code_connu(code):
        return None

    return {
        "motif": "code_inconnu",
        "message": (
            f"Le code {code} ne figure pas dans notre documentation technique. "
            "Je préfère transmettre votre demande à un conseiller plutôt que "
            "de vous donner une réponse approximative. Pouvez-vous vérifier "
            "le code affiché à l'écran de votre appareil ?"
        ),
        "code_signale": code,
    }


def _code_hors_appareil(analyse: dict) -> dict | None:
    """Le code existe, mais pas pour l'appareil du client (décision du 14/10).

    « Mon WX-450 affiche E15 » : E15 est un code lave-vaisselle. Avant cette
    règle, la recherche partait quand même, ramenait cinq passages WX-450 dont
    aucun ne parle de E15, et le LLM était appelé sur un contexte hors sujet.
    Le contrôle des citations ne pouvait rien y faire : une réponse hors sujet
    mais bien citée sortait en « repondu ».

    Placée après `_code_inconnu` : un code inconnu partout reçoit le message
    plus précis. Ne s'applique que si un appareil est identifié (modèle ou
    gamme) : sans appareil, les deux règles suivantes prennent le relais.
    """
    code = analyse["code"]
    if not code or not (analyse["modele"] or analyse["gamme"]):
        return None
    if code_documente_pour_appareil(code, analyse):
        return None

    appareil = libelle_gamme(analyse["gamme"]).lower()
    if analyse["modele"]:
        appareil = f"{appareil} {analyse['modele']}"
    return {
        "motif": "code_hors_appareil",
        "message": (
            f"Le code {code} ne figure pas dans la documentation de votre "
            f"{appareil}. Pouvez-vous vérifier le code affiché à l'écran et la "
            "référence de l'appareil (étiquette signalétique) ? Si les deux "
            "sont exacts, je transmets votre demande à un conseiller."
        ),
        "code_signale": code,
    }


def _code_ambigu_sans_appareil(analyse: dict) -> dict | None:
    """Le code existe, mais ne veut pas dire la même chose selon la gamme."""
    if not analyse["code"] or analyse["modele"] or analyse["gamme"]:
        return None

    gammes = codes_ambigus().get(analyse["code"])
    if not gammes:
        return None

    libelles = ", ".join(libelle_gamme(g).lower() for g in gammes)
    return {
        "motif": "code_ambigu_sans_modele",
        "message": (
            f"Le code {analyse['code']} n'a pas la même signification selon "
            f"l'appareil ({libelles}). Pouvez-vous m'indiquer la référence de "
            "votre appareil ? Elle figure sur l'étiquette signalétique, "
            "par exemple WX-450."
        ),
        "gammes_concernees": gammes,
    }


def _code_sans_appareil(analyse: dict) -> dict | None:
    """R1b — un code, aucun appareil identifié, même quand il n'est pas ambigu.

    E77 n'est porté que par les fours : la tentation est de répondre quand
    même. Mais rien ne dit que le client possède un four — il a pu mal lire son
    écran, ou son appareil peut porter un code absent de notre référentiel. La
    bonne réponse à « j'ai le code E77 » est de demander la référence, pas de
    parier sur la gamme.

    Sans cette règle, le filtre dur ne filtre rien : la recherche part sur les
    875 chunks du corpus, toutes gammes confondues.
    """
    if not analyse["code"] or analyse["modele"] or analyse["gamme"]:
        return None

    return {
        "motif": "code_sans_appareil",
        "message": (
            f"Pour vous indiquer ce que signifie le code {analyse['code']} sur "
            "votre appareil, j'ai besoin de sa référence. Elle figure sur "
            "l'étiquette signalétique, par exemple WX-450."
        ),
        "code_signale": analyse["code"],
    }


# Du message le plus précis au plus général. L'ordre EST la spécification.
REGLES = (
    _plusieurs_modeles,
    _reference_inconnue,
    _code_inconnu,
    _code_hors_appareil,
    _code_ambigu_sans_appareil,
    _code_sans_appareil,
)


def decider_escalade(analyse: dict) -> dict | None:
    """None si la recherche peut avoir lieu, sinon le motif et le message."""
    for regle in REGLES:
        decision = regle(analyse)
        if decision:
            return {"escalade": True, **decision}
    return None
