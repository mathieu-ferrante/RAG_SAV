"""Catalogue produit Electrodomus : gammes, modèles, et leur détection.

Source de vérité unique. Un nouveau modèle s'ajoute ICI et nulle part ailleurs.
Voir README.md, section « Pourquoi une métadonnée et pas du texte ».

La détection se fait en trois temps plutôt qu'avec une expression régulière
unique et de plus en plus dense :

    1. NORMALISER  le texte est ramené à une forme canonique (minuscules, sans
                   accents, tirets et espaces unifiés). Les motifs n'ont donc
                   plus à énumérer les variantes d'écriture.
    2. EXTRAIRE    un motif volontairement permissif remonte des *candidats*
                   (« wx 300 », « e 23 », « e-023 »), assortis de garde-fous.
    3. VALIDER     chaque candidat est confronté au catalogue. Ce qui n'y
                   figure pas n'est plus jeté en silence : c'est renvoyé à part
                   (référence inconnue), pour que l'appelant puisse le dire.

Élargir la tolérance revient à toucher la normalisation ou la liste de
séparateurs, pas à récrire un motif.
"""

import re
import unicodedata

GAMMES: dict[str, dict] = {
    "WX": {
        "libelle": "Lave-linge",
        "modeles": ["WX-300", "WX-350", "WX-400", "WX-450", "WX-500", "WX-550"],
        "synonymes": [
            "lave-linge", "lave linge", "lavelinge", "machine a laver",
            "machine-a-laver", "laveuse", "lessiveuse",
        ],
    },
    "LV": {
        "libelle": "Lave-vaisselle",
        "modeles": ["LV-100", "LV-150", "LV-200", "LV-250", "LV-300", "LV-350"],
        "synonymes": [
            "lave-vaisselle", "lave vaisselle", "lavevaisselle",
            "lave-vaiselle", "lave vaiselle",  # fautes fréquentes
        ],
    },
    "FR": {
        "libelle": "Four encastrable",
        "modeles": ["FR-600", "FR-650", "FR-700", "FR-750", "FR-800", "FR-850"],
        "synonymes": ["four", "fours", "four encastrable", "cuisiniere", "pyrolyse"],
    },
}

_GAMME_PAR_MODELE: dict[str, str] = {
    modele: code for code, gamme in GAMMES.items() for modele in gamme["modeles"]
}

# Numéro -> modèle, gamme par gamme. Sert à résoudre « mon lave-linge 450 ».
_MODELE_PAR_NUMERO: dict[str, dict[str, str]] = {
    code: {modele.split("-")[1]: modele for modele in gamme["modeles"]}
    for code, gamme in GAMMES.items()
}


# ---------------------------------------------------------------------------
# 1. Normalisation
# ---------------------------------------------------------------------------

# Word, les PDF et les copier-coller clients produisent une demi-douzaine de
# tirets visuellement identiques au tiret ASCII, et autant d'espaces.
# Sans cette table, « WX–450 » (tiret demi-cadratin, inséré automatiquement par
# la correction de Word) n'est pas reconnu alors qu'il est indiscernable à
# l'œil de « WX-450 ».
_TIRETS_UNICODE = "‐‑‒–—―−﹘﹣－"
_ESPACES_UNICODE = "     　"

_TRADUCTION = str.maketrans(
    {**{c: "-" for c in _TIRETS_UNICODE}, **{c: " " for c in _ESPACES_UNICODE}}
)


def _sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def normaliser_texte(texte: str) -> str:
    """Forme canonique sur laquelle travaille TOUTE la détection.

    minuscules · sans accents · tirets et espaces unifiés

    >>> normaliser_texte("Mon WX–450 é")
    'mon wx-450 e'
    """
    return _sans_accents((texte or "").translate(_TRADUCTION)).lower()


# ---------------------------------------------------------------------------
# 2. Motifs d'extraction (appliqués au texte NORMALISÉ, donc en minuscules)
# ---------------------------------------------------------------------------

# Séparateur toléré entre le préfixe et le numéro. Couvre d'un seul tenant
# « wx300 », « wx-300 », « wx 300 », « wx  300 », « wx_300 », « wx.300 »,
# « wx/300 », « wx - 300 ». Il est capturé : savoir si le client a mis un
# espace permet d'être plus prudent sur les codes erreur (cf. plus bas).
_SEPARATEUR = r"([ \t]{0,2}[-_./]?[ \t]{0,2})"

# Deux lettres + 3 ou 4 chiffres. On n'utilise pas \b : dans « Manuel_WX-450 »,
# le souligné est un caractère de mot, donc \b ne voit aucune frontière et le
# modèle passerait inaperçu.
MOTIF_MODELE = re.compile(rf"(?<![a-z0-9])([a-z]{{2}}){_SEPARATEUR}(\d{{3,4}})(?![a-z0-9])")

# Code erreur : E ou F + 1 à 3 chiffres.
MOTIF_CODE_ERREUR = re.compile(rf"(?<![a-z0-9])([ef]){_SEPARATEUR}(\d{{1,3}})(?![a-z0-9])")

# Repère une gamme écrite seule (proc-wx-01, fiche_garantie_gamme_lv).
# Les deux lettres ne doivent pas être collées à d'autres, sinon « fr »
# correspondrait dans « france ».
MOTIF_GAMME_ISOLEE = re.compile(
    r"(?<![a-z])(" + "|".join(g.lower() for g in GAMMES) + r")(?![a-z])"
)

# Garde-fou de la forme relâchée « e 23 » : un E/F isolé suivi d'un nombre est
# un code erreur, SAUF juste après un mot de numérotation. Le lookbehind du
# motif écarte déjà « ligne 12 » ou « page 42 » (le « e » y est précédé d'une
# lettre) ; ceci couvre le reste (« annexe E 23 », « figure F 12 »).
MOTIF_NUMEROTATION = re.compile(
    r"\b(?:page|pages|ligne|lignes|article|articles|chapitre|chapitres|section"
    r"|sections|paragraphe|alinea|figure|figures|tableau|tableaux|annexe"
    r"|annexes|colonne|rubrique|note|notes|etape|etapes|version|revision|rev"
    r"|numero|num|no)\W{0,3}$"
)


# ---------------------------------------------------------------------------
# 3. Extraction + validation
# ---------------------------------------------------------------------------

def _forme_relachee(separateur: str) -> bool:
    """Le client a-t-il séparé le préfixe du numéro par un espace ?"""
    return " " in separateur or "\t" in separateur


def _code_canonique(lettre: str, chiffres: str) -> str:
    """« e-023 », « e23 », « E 23 » -> « E23 » ; « e7 » -> « E07 ».

    Le référentiel écrit les codes sur deux chiffres (E01 … E77). On ramène
    donc tout à cette forme : sans quoi « E023 » et « E23 » désigneraient deux
    codes différents en base.
    """
    return f"{lettre.upper()}{int(chiffres):02d}"


def extraire_codes_erreur(texte: str) -> list[str]:
    """Tous les codes erreur cités, sans doublon et dans l'ordre.

    >>> extraire_codes_erreur("erreur E 23 puis e-023 et f12")
    ['E23', 'F12']
    """
    normalise = normaliser_texte(texte)
    trouves: list[str] = []

    for correspondance in MOTIF_CODE_ERREUR.finditer(normalise):
        lettre, separateur, chiffres = correspondance.groups()

        if _forme_relachee(separateur):
            # Un seul chiffre séparé par un espace (« e 7 ») est trop
            # ambigu pour être retenu : on exige la forme collée ou tiretée.
            if len(chiffres) < 2:
                continue
            if MOTIF_NUMEROTATION.search(normalise[: correspondance.start()]):
                continue

        code = _code_canonique(lettre, chiffres)
        if code not in trouves:
            trouves.append(code)

    return trouves


def extraire_references(texte: str) -> dict[str, list[str]]:
    """Sépare ce qui EST une référence du catalogue de ce qui y ressemble.

    {
      "modeles":  ["WX-450"],   # validés
      "inconnus": ["WX-460"],   # préfixe de gamme connu, numéro inconnu
    }

    « inconnus » est la correction du silence signalé en revue de code : une
    référence mal saisie ou d'une nouvelle série n'est plus jetée sans un mot,
    l'appelant peut le dire au client au lieu de lui redemander ce qu'il vient
    de donner.

    Un candidat dont le préfixe n'est pas une gamme connue (« BT-2026 » d'un
    bulletin technique, « PR-001 » d'une pièce) est ignoré : rien ne permet de
    le distinguer d'une référence de document.

    >>> extraire_references("j'ai un wx 460 et un LV-200")
    {'modeles': ['LV-200'], 'inconnus': ['WX-460']}
    """
    normalise = normaliser_texte(texte)
    modeles: list[str] = []
    inconnus: list[str] = []

    for correspondance in MOTIF_MODELE.finditer(normalise):
        prefixe, _, numero = correspondance.groups()
        candidat = f"{prefixe.upper()}-{numero}"

        if candidat in _GAMME_PAR_MODELE:
            if candidat not in modeles:
                modeles.append(candidat)
        elif prefixe.upper() in GAMMES and candidat not in inconnus:
            inconnus.append(candidat)

    return {"modeles": modeles, "inconnus": inconnus}


def extraire_modeles(texte: str) -> list[str]:
    """Tous les modèles du catalogue cités, sans doublon et dans l'ordre.

    On renvoie la liste complète : une question mentionnant deux appareils ne
    doit pas en perdre un silencieusement.
    """
    return extraire_references(texte)["modeles"]


def normaliser_modele(fragment: str) -> str | None:
    """« wx450 », « WX 450 », « WX–450 » -> « WX-450 ». None si hors catalogue."""
    modeles = extraire_references(fragment)["modeles"]
    return modeles[0] if modeles else None


def normaliser_code_erreur(fragment: str) -> str | None:
    """« e23 », « E-23 », « E 23 », « e023 » -> « E23 »."""
    codes = extraire_codes_erreur(fragment)
    return codes[0] if codes else None


def detecter_gamme_par_mots(texte: str) -> str | None:
    """« mon lave-vaisselle » -> « LV ».

    None si le texte évoque plusieurs gammes ou aucune : dans le doute on ne
    devine pas, on escalade.
    """
    normalise = normaliser_texte(texte)
    vues = {
        code
        for code, gamme in GAMMES.items()
        if any(syn in normalise for syn in gamme["synonymes"])
    }
    return vues.pop() if len(vues) == 1 else None


def detecter_gamme_isolee(texte: str) -> str | None:
    """« PROC-WX-01 », « Gamme_LV » -> le code de gamme."""
    correspondance = MOTIF_GAMME_ISOLEE.search(normaliser_texte(texte))
    return correspondance.group(1).upper() if correspondance else None


def modele_par_numero(code_gamme: str | None, numero: str) -> str | None:
    """« WX » + « 450 » -> « WX-450 ». None si ce numéro n'existe pas."""
    if not code_gamme:
        return None
    return _MODELE_PAR_NUMERO.get(code_gamme.upper(), {}).get(numero)


def gamme_du_modele(modele: str | None) -> str | None:
    return _GAMME_PAR_MODELE.get(modele) if modele else None


def gamme_de_la_reference(reference: str | None) -> str | None:
    """Gamme lue sur le PRÉFIXE, y compris pour une référence hors catalogue.

    « WX-460 » -> « WX » : on ignore de quel appareil il s'agit, mais on sait
    déjà que c'est un lave-linge.
    """
    if not reference:
        return None
    prefixe = reference.split("-")[0].upper()
    return prefixe if prefixe in GAMMES else None


def modeles_de_la_gamme(code_gamme: str | None) -> list[str]:
    if not code_gamme:
        return []
    return list(GAMMES.get(code_gamme.upper(), {}).get("modeles", []))


def libelle_gamme(code_gamme: str | None) -> str:
    """« WX » -> « Lave-linge ». Sert à formuler les messages clients."""
    if not code_gamme:
        return "appareil"
    return GAMMES.get(code_gamme.upper(), {}).get("libelle", code_gamme)
