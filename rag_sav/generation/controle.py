"""Contrôle des citations : vérifier ce que le prompt a seulement demandé.

Le prompt de `prompt.py` demande trois choses au modèle — citer, ne pas citer
l'interne, ne rien inventer. Un prompt n'oblige à rien : c'est une consigne
adressée à un modèle probabiliste. Ce module fait le travail déterministe
correspondant, APRÈS la génération.

C'est le bloc « post-traitement des citations » du schéma d'architecture, et
c'est le seul endroit du projet capable de détecter une hallucination de
source. Il ne réécrit jamais le fond de la réponse : il la qualifie, et
l'appelant décide.

Deux principes, appris sur le premier vrai rejeu (18/09) :

1. **Comparer les noms sur leur forme normalisée.** Le corpus contient
   `Referentiel_codes_erreur.xlsx`, sans accent — c'est le nom du classeur.
   Le modèle écrit `Référentiel_codes_erreur.xlsx`, parce que c'est
   l'orthographe française. Une comparaison stricte déclarait la citation
   inventée ET absente : le document le plus autoritaire du corpus traité en
   hallucination, sur un seul caractère.

2. **Réparer plutôt que rejeter quand la faute est de forme.** Une réponse
   fondée mais sans bloc « Sources : » n'est pas une invention : c'est un
   défaut de format, et nous savons quels passages ont été envoyés. On
   reconstitue le bloc au lieu de jeter la réponse. Citer faux ou citer
   l'interne restent des rejets — là il y a bien faute.

Aucune dépendance, aucun réseau : testable au même titre que `escalade.py`.
"""

import re
import unicodedata

from rag_sav.generation.prompt import MOTIF_CHAMP_TECHNICIEN

# Un nom de document tel qu'il apparaît dans le corpus : Manuel_WX-450.pdf,
# PROC-WX-02_Diagnostic_vidange.docx, faq-lave-linge.html,
# Referentiel_codes_erreur.xlsx. On repère la FORME, pour pouvoir comparer
# ensuite à la liste réelle et distinguer « cité » de « inventé ».
# Pas d'espace dans la classe : avec lui, « d'après le Manuel_WX-450.pdf »
# était capturé en entier (« après le Manuel_WX-450.pdf ») et une citation
# correcte au fil du texte passait pour une source inventée. Aucun nom de
# fichier du corpus ne contient d'espace.
MOTIF_FICHIER = re.compile(
    r"(?<![\w.\-])[\w][\w\-.]*\.(?:pdf|docx|doc|xlsx|xls|html|htm|md|txt)"
)

# Référence de pièce détachée : 44-2050, 51-0790. Quand elle n'existe que dans
# un passage INTERNE, la retrouver dans la réponse est une fuite de
# documentation technicien — que le nom du fichier soit cité ou non.
MOTIF_PIECE = re.compile(r"\b\d{2}-\d{3,4}\b")

# Tout ce qui est chiffré et précis : version de firmware (4.2), préfixe de
# numéro de série (2503), référence de pièce (44-3311), de bulletin
# (2026-007), dureté, température… Décision du 12/10 (option 3) : un tel
# marqueur que l'on ne trouve QUE dans un passage interne, et que le client
# n'a pas lui-même écrit, n'a rien à faire dans la réponse — quel que soit le
# document cité. C'est ce qui a laissé passer « firmware 4.2 / série 2503 »
# sous une citation du manuel WX-500.
MOTIF_MARQUEUR = re.compile(r"(?<![\w.])\d+(?:[.\-/]\d+)*(?![\w])")

# En deçà, un entier est trop banal pour signer une source (numéros d'étapes,
# « 10 minutes ») : il ferait accuser à tort une réponse fondée.
CHIFFRES_MIN_ENTIER = 3

# Part des mots significatifs d'un passage qu'il faut retrouver dans la
# réponse pour considérer que ce passage a servi. Valeur d'attente, à
# recalibrer sur le jeu d'évaluation comme SEUIL_SIMILARITE_PROVISOIRE.
SEUIL_RECOUVREMENT = 0.25

# Nombre maximum de sources reconstituées : au-delà, on ne cite plus, on liste.
MAX_SOURCES_REPAREES = 3

LONGUEUR_MOT_SIGNIFICATIF = 5


def _normaliser(texte: str) -> str:
    """Minuscules, sans accents : la forme sur laquelle on compare les noms.

    `Référentiel_codes_erreur.xlsx` et `Referentiel_codes_erreur.xlsx` doivent
    désigner le même document ; `MANUEL_WX-450.PDF` aussi.
    """
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn").casefold()


def _mots(texte: str) -> set[str]:
    """Les mots assez longs pour être discriminants, normalisés."""
    return {
        mot
        for mot in re.findall(r"[\w\-]+", _normaliser(texte))
        if len(mot) >= LONGUEUR_MOT_SIGNIFICATIF
    }


def _cites(texte: str, fichiers: set[str]) -> set[str]:
    """Quels fichiers connus apparaissent dans la réponse ?

    Comparaison par sous-chaîne normalisée plutôt que par parsing du bloc
    « Sources : » : un modèle qui cite correctement mais formate mal son bloc
    ne doit pas être accusé de ne pas avoir cité.
    """
    reponse = _normaliser(texte)
    return {fichier for fichier in fichiers if fichier and _normaliser(fichier) in reponse}


def _parts(passage: dict) -> tuple[str, str]:
    """(texte destiné au client, texte réservé) d'un passage.

    Un passage interne est réservé en entier. Un passage client l'est pour sa
    seule colonne « Intervention SAV (technicien) » : le référentiel est
    `audience=client` mais chacune de ses lignes porte une référence de pièce
    pour le technicien. `prompt.py` retire ce champ avant d'envoyer le passage
    au modèle ; le modèle ne peut donc pas le tenir de sa source client. S'il
    le restitue, c'est qu'il l'a lu dans un bulletin — une fuite (constaté au
    test du 12/10 : « 44-3311 » passait comme information client).
    """
    texte = passage.get("page_content") or ""
    if "audience_origine" in passage:
        # Profil conseiller (generation._ouvrir_au_conseiller) : toute la
        # documentation lui est destinée, colonne technicien comprise.
        return texte, ""
    if passage.get("audience", "client") != "client":
        return "", texte
    reserve = "\n".join(m.group(0) for m in MOTIF_CHAMP_TECHNICIEN.finditer(texte))
    return MOTIF_CHAMP_TECHNICIEN.sub("", texte), reserve


def _pieces_exclusivement_internes(passages: list[dict]) -> set[str]:
    """Références de pièces présentes dans du texte réservé et nulle part ailleurs.

    Réservé = passage interne, ou colonne technicien d'un passage client
    (voir `_parts`) : une référence que le client lit ailleurs dans un passage
    client n'est pas une fuite.
    """
    reservees, clients = set(), set()
    for passage in passages:
        client, reserve = _parts(passage)
        clients |= set(MOTIF_PIECE.findall(client))
        reservees |= set(MOTIF_PIECE.findall(reserve))
    return reservees - clients


# Une référence d'appareil (WX-500, FR 700, LV250) n'est pas un marqueur : elle
# figure partout, et c'est le client qui la donne.
MOTIF_APPAREIL = re.compile(r"\b[A-Za-z]{2}\s?-?\s?\d{3}\b")


def _forme_chiffres(texte: str) -> str:
    """Tirets typographiques -> « - », virgule décimale -> point."""
    for car in "‐‑‒–—―−":
        texte = texte.replace(car, "-")
    return re.sub(r"(\d),(\d)", r"\1.\2", texte)


def marqueurs(texte: str) -> set[str]:
    """Les marqueurs chiffrés assez précis pour trahir leur source."""
    trouves = set()
    texte = MOTIF_APPAREIL.sub(" ", _forme_chiffres(texte or ""))
    for jeton in MOTIF_MARQUEUR.findall(texte):
        if jeton.isdigit() and len(jeton) < CHIFFRES_MIN_ENTIER:
            continue
        trouves.add(jeton)
    return trouves


def marqueurs_exclusivement_internes(passages: list[dict], question: str = "") -> set[str]:
    """Marqueurs présents dans un passage interne et nulle part ailleurs.

    Ni dans un passage client (le référentiel, client, porte lui aussi des
    références : les répéter n'est pas une fuite), ni dans la question (le
    client peut redonner son propre numéro de série).
    """
    internes, autorises = set(), marqueurs(question)
    for passage in passages:
        client, reserve = _parts(passage)
        autorises |= marqueurs(client)
        internes |= marqueurs(reserve)
    return internes - autorises


def verifier(texte: str, passages: list[dict], question: str = "") -> dict:
    """Qualifie les citations d'une réponse produite.

        {
          "cites":     ["Manuel_WX-450.pdf"],      # connus et cités
          "internes":  [],                          # cités alors qu'INTERNE
          "inventes":  [],                          # forme de fichier hors contexte
          "pieces_internes": [],                    # fuite de référence technicien
          "marqueurs_internes": [],                 # fuite d'un chiffre interne (4.2, 2503)
          "aucune_citation": False,
          "conforme":  True,
        }

    `conforme` est le seul champ que l'appelant a besoin de lire ; les listes
    servent au diagnostic et au benchmark — ce sont elles qui donneront le taux
    d'affirmations non sourcées du jeu d'évaluation.
    """
    tous = {p.get("nom_fichier") for p in passages}
    internes = {
        p.get("nom_fichier") for p in passages if p.get("audience", "client") != "client"
    }
    # Un même nom de fichier peut arriver par deux passages, l'un client et
    # l'autre interne. On ne le compte interne que s'il n'est JAMAIS client.
    clients = {
        p.get("nom_fichier") for p in passages if p.get("audience", "client") == "client"
    }
    internes -= clients

    cites = _cites(texte, tous)
    cites_internes = cites & internes

    # Tout ce qui a la forme d'un nom de document sans être dans le contexte.
    connus = {_normaliser(nom) for nom in tous if nom}
    formes = {m.group(0).strip() for m in MOTIF_FICHIER.finditer(texte)}
    inventes = {f for f in formes if _normaliser(f) not in connus}

    fuites = {
        piece
        for piece in _pieces_exclusivement_internes(passages)
        if piece in texte
    }

    # Généralisation du contrôle des pièces à tout marqueur chiffré interne.
    marqueurs_fuites = marqueurs_exclusivement_internes(passages, question) & marqueurs(texte)

    return {
        "cites": sorted(c for c in cites if c),
        "internes": sorted(c for c in cites_internes if c),
        "inventes": sorted(inventes),
        "pieces_internes": sorted(fuites),
        "marqueurs_internes": sorted(marqueurs_fuites),
        "aucune_citation": not cites,
        "conforme": bool(cites)
        and not cites_internes
        and not inventes
        and not fuites
        and not marqueurs_fuites,
    }


# ---------------------------------------------------------------------------
# Réparation — le seul défaut qui ne mérite pas un rejet
# ---------------------------------------------------------------------------

def sources_probables(texte: str, passages: list[dict]) -> list[dict]:
    """Les passages citables que la réponse a visiblement utilisés.

    Mesure : la part des mots significatifs du passage que l'on retrouve dans
    la réponse. C'est grossier, mais déterministe et vérifiable — et il ne
    s'agit pas de deviner un raisonnement, seulement de ne pas attribuer une
    réponse à un passage dont elle ne reprend rien.
    """
    scores = []
    for passage in passages:
        if passage.get("audience", "client") != "client":
            continue  # l'interne ne se cite pas, même reconstitué
        mots_passage = _mots(passage.get("page_content") or "")
        if not mots_passage:
            continue
        recouvrement = len(mots_passage & _mots(texte)) / len(mots_passage)
        if recouvrement >= SEUIL_RECOUVREMENT:
            scores.append((recouvrement, passage))

    scores.sort(key=lambda couple: couple[0], reverse=True)
    return [passage for _, passage in scores[:MAX_SOURCES_REPAREES]]


def reparer(texte: str, passages: list[dict]) -> tuple[str, list[dict]] | None:
    """Ajoute le bloc « Sources : » manquant, ou rend None si rien à citer.

    Appelé uniquement quand le SEUL défaut est `aucune_citation` : la réponse
    est fondée sur les passages fournis, le modèle a seulement oublié — ou mal
    formaté — le bloc final. Rien du fond n'est modifié.
    """
    sources = sources_probables(texte, passages)
    if not sources:
        return None

    lignes = "\n".join(
        f"- {source['nom_fichier']} — {source['section_path']}" for source in sources
    )
    return f"{texte.rstrip()}\n\nSources :\n{lignes}", sources


MESSAGE_NON_CONFORME = (
    "Je préfère ne pas vous répondre de mémoire sur ce point. Je transmets "
    "votre demande à un conseiller, qui vous confirmera la procédure exacte "
    "pour votre appareil."
)


def motif_non_conformite(controle: dict) -> str | None:
    """Le motif le plus précis, du plus grave au moins grave."""
    if controle["inventes"]:
        return "citation_inventee"
    if controle["internes"]:
        return "citation_interne"
    if controle.get("pieces_internes") or controle.get("marqueurs_internes"):
        return "fuite_interne"
    if controle["aucune_citation"]:
        return "aucune_citation"
    return None
