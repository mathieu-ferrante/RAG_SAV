"""Le garde-fou d'entrée du moteur de réponse.

`rechercher()` produisait déjà un diagnostic complet — `correspondance_modele`
par passage, `contexte_faible` global — que **personne ne lisait**. Ce module
est le premier consommateur : il décide si l'on a le droit d'appeler le LLM.

Pourquoi un module à part plutôt qu'un `if` dans la génération : la décision
doit être testable sans LLM, sans base et sans réseau, et surtout elle doit
être *lisible* — un auditeur doit pouvoir dire pourquoi l'assistant a refusé
de répondre. C'est la contrainte client n° 2 (« escalader plutôt qu'inventer »)
appliquée à la sortie de la recherche.

Le raisonnement est le même que pour `escalade.py`, mais un cran plus loin :
`escalade.py` refuse AVANT de chercher, sur la seule question. `verrou.py`
refuse APRÈS avoir cherché, sur ce que la recherche a effectivement ramené.
"""

from rag_sav.config import CORRESPONDANCES_ACCEPTEES, REFUSER_SI_APPAREIL_NON_PRECISE

# ---------------------------------------------------------------------------
# Tri des passages
# ---------------------------------------------------------------------------

def _recevable(resultat: dict) -> bool:
    """Ce passage est-il rattaché à l'appareil du client ?

    `non_contrainte` signifie que le filtre dur n'avait rien à filtrer : le
    passage est peut-être d'une autre gamme. Avec 60 % de doublons exacts
    entre gammes, le laisser entrer dans le contexte revient à jouer la
    réponse aux dés.
    """
    return resultat.get("correspondance_modele") in CORRESPONDANCES_ACCEPTEES


def _citable(resultat: dict) -> bool:
    """Décision du 15/09 : l'assistant LIT l'interne, il ne le CITE pas.

    Bulletins techniques et procédures SAV portent la mention « documentation
    interne » et des références de pièces. Ils servent à être exact — un
    bulletin prévaut sur un manuel — mais la citation rendue au client doit
    porter sur un document qui lui est destiné.
    """
    return resultat.get("audience", "client") == "client"


# ---------------------------------------------------------------------------
# La décision
# ---------------------------------------------------------------------------

REFUS = {
    "aucun_contexte": (
        "Je n'ai trouvé aucun passage de notre documentation traitant de votre "
        "demande. Je transmets votre question à un conseiller."
    ),
    "contexte_non_contraint": (
        "Les passages trouvés ne concernent pas de façon certaine votre "
        "appareil. Plutôt que de vous donner une procédure qui pourrait valoir "
        "pour un autre modèle, je transmets votre demande à un conseiller."
    ),
    "contexte_faible": (
        "Notre documentation ne traite pas votre demande d'assez près pour que "
        "je puisse y répondre sans risque d'approximation. Je transmets votre "
        "question à un conseiller."
    ),
    "appareil_non_precise": (
        "Cette question n'a pas la même réponse selon l'appareil, et vous ne "
        "m'avez pas indiqué lequel. Pouvez-vous me donner la référence "
        "figurant sur l'étiquette signalétique, par exemple WX-450 ?"
    ),
    "bulletin_prevaut": (
        "Pour ce code sur votre appareil, une consigne technique plus récente "
        "que votre manuel s'applique. Pour ne pas vous indiquer une procédure "
        "dépassée, je transmets votre demande à un conseiller, qui vous guidera. "
        "Préparez le numéro de série de votre appareil (étiquette signalétique)."
    ),
    "aucune_source_citable": (
        "Les seuls éléments dont je dispose sur ce point relèvent de notre "
        "documentation technique interne, que je ne peux pas vous citer "
        "directement. Un conseiller va reprendre votre demande."
    ),
}


# Motifs qui ne sont pas un refus faute de contexte, mais un passage de main
# volontaire à un conseiller : le statut rendu est « escalade ».
MOTIFS_ESCALADE = {"bulletin_prevaut"}


def _bulletin_prevaut(passages: list[dict]) -> bool:
    """Un document INTERNE prévaut-il sur la documentation client ?

    Décision du 12/10 (option 3). Un bulletin technique existe parce que le
    manuel et le référentiel sont faux ou incomplets sur ce point. Deux
    issues étaient mauvaises :

      - répondre avec le manuel : le client suit une procédure dépassée ;
      - laisser le modèle reprendre le bulletin : du contenu « diffusion
        conseillers et techniciens » sort vers le client, sous une citation
        de manuel qui ne dit pas la même chose (constaté sur WX-500 + E52 :
        firmware 4.2, numéros de série 2503).

    Un humain reprend donc la main, et c'est une règle — pas le modèle — qui
    le décide. `prevaut` est calculé par la recherche : bulletin prioritaire
    ET mentionnant le code demandé. Un bulletin destiné au client (audience
    « client ») n'est pas concerné : il se cite normalement.
    """
    return any(p.get("prevaut") and not _citable(p) for p in passages)


def _sans_appareil(resultats: list[dict]) -> tuple[list[dict], str | None]:
    """Que faire quand la question ne nomme ni modèle ni gamme ?

    Le filtre dur n'a alors rien à filtrer, donc tous les passages ressortent
    `non_contrainte` et la règle générale les écarterait tous — une question
    de garantie ou de procédure posée sans référence ne recevait JAMAIS de
    réponse, alors que le corpus la contient. Or le danger n'est pas
    l'absence d'appareil : c'est de transposer une procédure d'une gamme à
    une autre. On le mesure au lieu de le supposer.

    Trois branches, de la plus sûre à la plus prudente :

      1. des documents transverses sont remontés   -> ils valent pour tous
      2. tout ce qui remonte relève d'une seule gamme -> rien à transposer
      3. plusieurs gammes se disputent la réponse  -> le LLM répond gamme par
         gamme (le prompt l'y oblige) et invite à préciser la référence ; ou,
         avec REFUSER_SI_APPAREIL_NON_PRECISE=1, refus déterministe.

    Le cas vraiment dangereux — un code erreur sans appareil — n'arrive
    jamais jusqu'ici : `escalade.py` l'a déjà intercepté.
    """
    transverses = [
        r for r in resultats
        if r.get("portee") == "global" or r.get("correspondance_modele") == "transverse"
    ]
    if transverses:
        return transverses, None

    gammes = {r.get("gamme") for r in resultats if r.get("gamme")}
    if len(gammes) <= 1 or not REFUSER_SI_APPAREIL_NON_PRECISE:
        return list(resultats), None

    return [], "appareil_non_precise"


def decider_generation(reponse_recherche: dict) -> dict:
    """Peut-on appeler le LLM, et avec quels passages ?

    Renvoie toujours un dict :

        {"autorise": True,  "passages": [...], "citables": [...]}
        {"autorise": False, "motif": "...", "message": "...", "passages": []}

    L'ordre des vérifications va du constat le plus grossier au plus fin,
    comme le tuple `REGLES` d'escalade.py : le motif rendu doit être le plus
    précis possible, mais on ne teste la finesse qu'une fois le grossier écarté.
    """
    resultats = reponse_recherche.get("resultats") or []
    diagnostic = reponse_recherche.get("diagnostic") or {}
    analyse = reponse_recherche.get("analyse") or {}

    # 1. La recherche n'a rien ramené du tout.
    if not resultats:
        return _refus("aucun_contexte")

    # 2. Rattachement à l'appareil — sauf si la question n'en nomme aucun,
    #    auquel cas il n'y a rien à rattacher et c'est la cohérence entre les
    #    passages qui décide (voir _sans_appareil).
    if not analyse.get("modele") and not analyse.get("gamme"):
        passages, motif = _sans_appareil(resultats)
        if motif:
            return _refus(motif)
    else:
        passages = [r for r in resultats if _recevable(r)]
        if not passages:
            return _refus("contexte_non_contraint")

    # 3. Un bulletin interne prévaut pour ce code et cet appareil : la
    #    documentation client est dépassée, un conseiller reprend la main.
    #    Avant le seuil de similarité : le bulletin a été retrouvé par le
    #    code exact, sa pertinence ne se discute pas.
    if _bulletin_prevaut(passages):
        return _refus("bulletin_prevaut")

    # 4. Les passages sont du bon appareil, mais aucun ne traite le sujet.
    #    Seuil provisoire (0.45), à recalibrer sur le jeu d'évaluation.
    if diagnostic.get("contexte_faible"):
        return _refus("contexte_faible")

    # 5. Tout est du bon appareil et proche du sujet, mais rien n'est citable.
    citables = [r for r in passages if _citable(r)]
    if not citables:
        return _refus("aucune_source_citable")

    gammes = {r.get("gamme") for r in passages if r.get("gamme")}
    plusieurs_gammes = (
        not analyse.get("modele") and not analyse.get("gamme") and len(gammes) > 1
    )
    return {
        "autorise": True,
        "passages": passages,
        "citables": citables,
        "plusieurs_gammes": plusieurs_gammes,
    }


def _refus(motif: str) -> dict:
    return {
        "autorise": False,
        "statut": "escalade" if motif in MOTIFS_ESCALADE else "refus",
        "motif": motif,
        "message": REFUS[motif],
        "passages": [],
        "citables": [],
    }
