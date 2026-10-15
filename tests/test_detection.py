"""Non-régression de la détection des références et des codes erreur.

    python tests/test_detection.py        (aucune dépendance)
    pytest tests/test_detection.py        (si pytest est installé)

Chaque cas vient d'une formulation réellement plausible côté client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag_sav.catalogue import (  # noqa: E402
    extraire_references,
    normaliser_code_erreur,
    normaliser_modele,
)
from rag_sav.recherche.analyse import analyser_question  # noqa: E402

# --- Modèles : toutes les écritures d'une même référence --------------------

MODELES_OK = [
    "WX-300", "wx-300", "Wx-300", "wX-300",
    "WX 300", "wx 300", "WX  300", "wx\t300",
    "wx300", "WX300", "wx_300", "wx.300", "wx/300",
    "wx - 300", "WX -300", "WX- 300",
    "WX–300", "WX—300", "WX‑300",      # tirets Word / PDF
    "WX 300",                                     # espace insécable
    "mon lave-linge WX300 fait du bruit",
    "référence : wx-300.",
    "(WX 300)",
    "Manuel_WX-300.pdf",
]

MODELES_KO = [
    "wx-30", "wx-30000", "awx-300", "wx-300a",
    "BT-2026-007", "PROC-WX-01", "page 300",
]

# --- Codes erreur -----------------------------------------------------------

CODES_OK = {
    "E23": "E23", "e23": "E23", "E-23": "E23", "e-23": "E23",
    "E 23": "E23", "e 23": "E23", "e  23": "E23", "E_23": "E23",
    "E.23": "E23", "e/23": "E23", "E023": "E23", "e-023": "E23",
    "e7": "E07", "E-7": "E07",
    "le code erreur E 23 clignote": "E23",
    "erreur e23,": "E23", "(E23)": "E23", "f12": "F12", "F 12": "F12",
}

CODES_KO = [
    "ligne 12", "page 42", "il y a 23 jours", "23", "e 7",
    "annexe E 23", "figure F 12", "voir tableau E 42",
]


def test_modeles_toutes_ecritures():
    for texte in MODELES_OK:
        assert normaliser_modele(texte) == "WX-300", f"non reconnu : {texte!r}"


def test_modeles_faux_positifs():
    for texte in MODELES_KO:
        assert normaliser_modele(texte) is None, f"faux positif : {texte!r}"


def test_codes_toutes_ecritures():
    for texte, attendu in CODES_OK.items():
        assert normaliser_code_erreur(texte) == attendu, f"non reconnu : {texte!r}"


def test_codes_faux_positifs():
    for texte in CODES_KO:
        assert normaliser_code_erreur(texte) is None, f"faux positif : {texte!r}"


def test_reference_inconnue_conservee():
    """Une référence bien formée hors catalogue n'est plus jetée en silence."""
    resultat = extraire_references("j'ai un WX-460")
    assert resultat == {"modeles": [], "inconnus": ["WX-460"]}

    analyse = analyser_question("j'ai un WX-460, code E23")
    assert analyse["modele"] is None
    assert analyse["modeles_inconnus"] == ["WX-460"]
    assert analyse["gamme"] == "WX"            # le préfixe reste exploitable


def test_reference_de_document_ignoree():
    """BT-2026 n'est pas une référence produit : ni modèle, ni « inconnue »."""
    assert extraire_references("bulletin BT-2026-007") == {"modeles": [], "inconnus": []}


def test_plusieurs_appareils():
    assert extraire_references("un wx450 et un LV 200")["modeles"] == ["WX-450", "LV-200"]


def test_numero_seul_avec_gamme_en_clair():
    analyse = analyser_question("mon lave-linge 450 affiche e 23")
    assert analyse["modele"] == "WX-450"
    assert analyse["origine_modele"] == "numero_seul"
    assert analyse["code"] == "E23"


def test_numero_seul_garde_fous():
    """Un nombre isolé n'est pas une référence sous prétexte qu'il existe."""
    for question in [
        "mon lave-linge est en panne, voir page 450 du manuel",
        "mon lave-linge m'a coûté 450 euros",
        "mon lave-linge tourne à 450 tr/min",
        "commande n° 450, mon lave-linge est en panne",
        "mon lave-linge, facture 450 du 12 mars",
    ]:
        assert analyser_question(question)["modele"] is None, question


def test_numero_seul_sans_gamme():
    """Sans gamme dite en clair, un numéro seul ne suffit pas."""
    assert analyser_question("mon appareil 450 affiche E23")["modele"] is None


def test_non_regression_analyse():
    analyse = analyser_question("Mon lave-vaisselle LV-200 affiche le code erreur E23")
    assert (analyse["modele"], analyse["gamme"], analyse["code"]) == ("LV-200", "LV", "E23")

    analyse = analyser_question("mon wx500 affiche e52")
    assert (analyse["modele"], analyse["code"]) == ("WX-500", "E52")

    analyse = analyser_question("Que signifie le code E23 ?")
    assert analyse["modele"] is None and analyse["gamme"] is None


if __name__ == "__main__":
    echecs = 0
    for nom, fonction in sorted(globals().items()):
        if not nom.startswith("test_"):
            continue
        try:
            fonction()
            print(f"  ok   {nom}")
        except AssertionError as erreur:
            echecs += 1
            print(f"  ECHEC {nom} : {erreur}")
    print(f"\n{'TOUT PASSE' if not echecs else f'{echecs} echec(s)'}")
    sys.exit(1 if echecs else 0)
