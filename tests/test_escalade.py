"""Non-régression des règles d'escalade, sans base de données.

    python tests/test_escalade.py        (aucune dépendance hors psycopg)
    pytest tests/test_escalade.py

Le référentiel est simulé : ces tests vérifient les RÈGLES, pas le SQL.
Les valeurs reprennent le référentiel réellement indexé (5 codes ambigus).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag_sav.recherche import escalade  # noqa: E402
from rag_sav.recherche.analyse import analyser_question  # noqa: E402

REFERENTIEL_SIMULE = {
    "E01": ["LV", "WX"], "E10": ["FR", "LV", "WX"], "E23": ["LV", "WX"],
    "E31": ["FR", "WX"], "E42": ["FR", "LV"],
    "E15": ["LV"], "E20": ["WX"], "E77": ["FR"],
}

# E52 n'est traité que par le bulletin BT-2026-007 : hors référentiel, mais
# bien présent dans le corpus.
CODES_DANS_LE_TEXTE = set(REFERENTIEL_SIMULE) | {"E52"}

escalade.codes_referentiel = lambda relire=False: REFERENTIEL_SIMULE
escalade.code_connu = lambda code: code in CODES_DANS_LE_TEXTE


def motif(question: str) -> str | None:
    decision = escalade.decider_escalade(analyser_question(question))
    return decision["motif"] if decision else None


CAS = [
    # question                                          motif attendu
    ("Mon lave-linge WX-450 affiche E23",               None),
    ("mon wx500 affiche e52",                           None),   # code hors référentiel mais documenté
    ("Comment détartrer mon lave-linge WX-400 ?",       None),   # aucun code
    ("mon lave-linge affiche E15",                      None),   # gamme par le vocabulaire
    ("bonjour mon lave-linge 450 affiche e 23",         None),   # écriture libre
    ("j'ai un wx450 et un lv200",                       "plusieurs_modeles"),
    ("j'ai un WX-460, code E23",                        "reference_inconnue"),
    ("voir page 450 du manuel, code F12",               "code_inconnu"),   # R1a
    ("mon lave-linge WX-450 affiche E99",               "code_inconnu"),   # R1a, même avec un modèle
    ("Que signifie le code E23 ?",                      "code_ambigu_sans_modele"),
    ("j'ai le code E77 qui s'affiche",                  "code_sans_appareil"),  # R1b
    ("code E20",                                        "code_sans_appareil"),  # R1b
]


def test_regles_escalade():
    for question, attendu in CAS:
        obtenu = motif(question)
        assert obtenu == attendu, f"{question!r} -> {obtenu!r}, attendu {attendu!r}"


def test_message_toujours_renseigne():
    for question, attendu in CAS:
        if attendu is None:
            continue
        decision = escalade.decider_escalade(analyser_question(question))
        assert decision["message"].strip(), question
        assert decision["escalade"] is True, question


def test_code_ambigu_nomme_les_gammes():
    decision = escalade.decider_escalade(analyser_question("Que signifie le code E23 ?"))
    assert decision["gammes_concernees"] == ["LV", "WX"]
    assert "lave-linge" in decision["message"] and "lave-vaisselle" in decision["message"]


def test_codes_ambigus_deduits_du_referentiel():
    """La liste n'est pas écrite en dur : elle se déduit des gammes portées."""
    assert sorted(escalade.codes_ambigus()) == ["E01", "E10", "E23", "E31", "E42"]


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
