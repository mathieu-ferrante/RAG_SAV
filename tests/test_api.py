"""L'API REST — sans base, sans LLM, sans modèle d'embedding.

    python tests/test_api.py
    pytest tests/test_api.py

`repondre()` est remplacé par un double : ces tests vérifient le CONTRAT HTTP
(ce qui entre, ce qui sort, ce qui ne doit jamais sortir), pas le moteur, déjà
couvert par les autres suites.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from api import comptes, routes as api  # noqa: E402

CONTENU_INTERNE = "firmware 4.2, numéros de série 2503"


APPELS = []


def faux_repondre(question, profil="client", **_):
    APPELS.append(profil)
    if "panne" in question:
        raise RuntimeError("base injoignable")
    analyse = {"question": question, "code": "E23", "modele": "WX-450", "gamme": "WX"}
    return {
        "question": question,
        "analyse": analyse,
        "diagnostic": {"meilleure_similarite": 0.71, "contexte_faible": False},
        "statut": "repondu",
        "motif": None,
        "reponse": "Nettoyez le filtre de vidange.\n\nSources :\nManuel_WX-450.pdf — 9. Codes erreur",
        "reponse_brute": CONTENU_INTERNE,
        "reparation": None,
        "sources": [{"nom_fichier": "Manuel_WX-450.pdf", "section_path": "9. Codes erreur"}],
        "passages": [{
            "nom_fichier": "BT-2026-007.docx", "section_path": "Procédure", "audience": "interne",
            "page_content": CONTENU_INTERNE, "similarite": 0.7, "prevaut": False,
            "correspondance_modele": "exacte",
        }],
        "candidats": [],
        "controle": {"conforme": True},
        "llm": {"modele": "llama3.2", "fournisseur": "ollama", "duree_s": 1.2,
                "jetons_prompt": 900, "jetons_reponse": 80, "jetons_par_seconde": 66},
    }


api.repondre = faux_repondre
client = TestClient(api.app)

import tempfile  # noqa: E402

_FICHIER = Path(tempfile.mkdtemp()) / "comptes.json"
for _f in (comptes.ajouter, comptes.supprimer, comptes.lister, comptes.verifier):
    _f.__defaults__ = tuple(_FICHIER if isinstance(d, Path) else d for d in (_f.__defaults__ or ()))
comptes.ajouter("jdupont", "motdepasse-solide")
CONSEILLER = ("jdupont", "motdepasse-solide")


def test_question_nominale():
    r = client.post("/questions", json={"question": "Mon lave-linge WX-450 affiche E23"})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["statut"] == "repondu"
    assert corps["sources"] == [{"nom_fichier": "Manuel_WX-450.pdf", "section_path": "9. Codes erreur"}]
    assert corps["analyse"] == {"code": "E23", "modele": "WX-450", "gamme": "WX"}
    assert corps["details"] is None


def test_rien_d_interne_ne_sort_par_defaut():
    """Passages internes et réponse brute restent côté serveur."""
    r = client.post("/questions", json={"question": "Mon WX-500 affiche E52"})
    assert CONTENU_INTERNE not in r.text


def test_details_refuses_si_non_actives():
    api.API_DETAILS = False
    r = client.post("/questions", json={"question": "x", "details": True})
    assert r.status_code == 403


def test_details_sans_texte_des_passages():
    api.API_DETAILS = True
    try:
        r = client.post("/questions", json={"question": "Mon WX-450 affiche E23", "details": True})
    finally:
        api.API_DETAILS = False
    assert r.status_code == 200
    passages = r.json()["details"]["passages"]
    assert passages and "page_content" not in passages[0]


def test_question_vide_ou_trop_longue():
    assert client.post("/questions", json={"question": ""}).status_code == 422
    assert client.post("/questions", json={"question": "   "}).status_code == 422
    assert client.post("/questions", json={"question": "a" * 2001}).status_code == 422
    assert client.post("/questions", json={}).status_code == 422


def test_panne_du_moteur_rend_503_sans_trace():
    r = client.post("/questions", json={"question": "panne"})
    assert r.status_code == 503
    assert "injoignable" not in r.text and "Traceback" not in r.text


def test_vider_cache():
    from rag_sav.recherche import escalade

    escalade._cache_codes_connus["E99"] = False
    assert client.post("/cache/vider").status_code == 401
    assert client.post("/cache/vider", auth=CONSEILLER).json() == {"statut": "ok"}
    assert escalade._cache_codes_connus == {}


def test_sans_identifiant_profil_client():
    APPELS.clear()
    r = client.post("/questions", json={"question": "Mon WX-450 affiche E23"})
    assert r.json()["profil"] == "client" and r.json()["conseiller"] is None
    assert APPELS == ["client"]


def test_identifiant_et_mot_de_passe_profil_conseiller():
    """Une seule étape : pas de connexion préalable, pas de jeton."""
    APPELS.clear()
    r = client.post("/questions", json={"question": "Mon WX-500 affiche E52"}, auth=CONSEILLER)
    assert r.status_code == 200, r.text
    assert r.json()["profil"] == "conseiller" and r.json()["conseiller"] == "jdupont"
    assert APPELS == ["conseiller"]


def test_mauvais_mot_de_passe_401_sans_repli_client():
    APPELS.clear()
    r = client.post("/questions", json={"question": "x"}, auth=("jdupont", "faux"))
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Basic"
    r = client.post("/questions", json={"question": "x"}, auth=("personne", "faux"))
    assert r.status_code == 401
    assert APPELS == [], "repondre() ne doit pas être appelé"


def test_conseiller_a_droit_aux_details():
    api.API_DETAILS = False
    r = client.post("/questions", json={"question": "x", "details": True}, auth=CONSEILLER)
    assert r.status_code == 200 and r.json()["details"] is not None


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
