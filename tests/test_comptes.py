"""Comptes conseillers — sans serveur.

    python tests/test_comptes.py
    pytest tests/test_comptes.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import comptes  # noqa: E402

FICHIER = Path(tempfile.mkdtemp()) / "comptes.json"


def test_ajout_puis_verification():
    comptes.ajouter("JDupont", "motdepasse-solide", FICHIER)
    assert comptes.verifier("jdupont", "motdepasse-solide", FICHIER) == "jdupont"
    assert comptes.verifier("JDUPONT ", "motdepasse-solide", FICHIER) == "jdupont"
    assert comptes.verifier("jdupont", "mauvais", FICHIER) is None
    assert comptes.verifier("inconnu", "motdepasse-solide", FICHIER) is None


def test_aucun_mot_de_passe_en_clair():
    comptes.ajouter("mmartin", "secret-de-test-123", FICHIER)
    assert "secret-de-test-123" not in FICHIER.read_text(encoding="utf-8")


def test_mot_de_passe_trop_court_refuse():
    try:
        comptes.ajouter("court", "1234", FICHIER)
    except ValueError:
        return
    raise AssertionError("un mot de passe de 4 caractères a été accepté")


def test_supprimer_un_compte_coupe_son_acces():
    comptes.ajouter("temporaire", "motdepasse-solide", FICHIER)
    assert comptes.supprimer("temporaire", FICHIER)
    assert comptes.verifier("temporaire", "motdepasse-solide", FICHIER) is None
    assert "temporaire" not in comptes.lister(FICHIER)


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
