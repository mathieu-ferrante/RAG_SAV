"""Réglages lus dans le .env — ici, le seuil de similarité.

    python tests/test_config.py
    pytest tests/test_config.py

Chaque cas tourne dans un interpréteur neuf : config.py lit l'environnement
une seule fois, à l'import.
"""

import os
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _seuil(valeur):
    env = {k: v for k, v in os.environ.items() if k != "SEUIL_SIMILARITE"}
    if valeur is not None:
        env["SEUIL_SIMILARITE"] = valeur
    # load_dotenv() ne remplace pas une variable déjà définie ; pour le cas
    # « absente », on lance depuis un dossier vide afin qu'aucun .env ne soit lu.
    code = (
        "import sys, dotenv; dotenv.load_dotenv = lambda *a, **k: None;"
        f"sys.path.insert(0, {str(RACINE)!r});"
        "from rag_sav.config import SEUIL_SIMILARITE_PROVISOIRE as s; print(repr(s))"
    )
    sortie = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    lignes = sortie.stdout.strip().splitlines()
    return float(lignes[-1]), "\n".join(lignes[:-1])


def test_absent_donne_045():
    assert _seuil(None) == (0.45, "")


def test_valeur_lue_dans_l_environnement():
    assert _seuil("0.55")[0] == 0.55


def test_virgule_decimale_acceptee():
    assert _seuil("0,5")[0] == 0.5


def test_valeur_illisible_retombe_sur_045_avec_avertissement():
    valeur, message = _seuil("haut")
    assert valeur == 0.45 and "invalide" in message


def test_valeur_hors_bornes_refusee():
    assert _seuil("45")[0] == 0.45      # 45 au lieu de 0.45 : erreur fréquente
    assert _seuil("-0.1")[0] == 0.45


def test_le_diagnostic_utilise_bien_la_valeur_reglee():
    code = (
        "import sys, dotenv; dotenv.load_dotenv = lambda *a, **k: None;"
        f"sys.path.insert(0, {str(RACINE)!r});"
        "from rag_sav.recherche.resultats import diagnostic;"
        "a = {'modele': 'WX-450', 'gamme': 'WX'};"
        "print(diagnostic(a, [{'similarite': 0.5}], None)['contexte_faible'])"
    )
    env = dict(os.environ, SEUIL_SIMILARITE="0.6")
    sortie = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert sortie.stdout.strip() == "True"   # 0.5 < 0.6 : contexte faible


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
