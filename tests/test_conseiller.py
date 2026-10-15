"""Le profil conseiller dans le moteur — sans base ni LLM.

    python tests/test_conseiller.py
    pytest tests/test_conseiller.py

Même scénario que le 12/10 : WX-500 + E52, le bulletin interne BT-2026-007
prévaut. Client : la conduite du référentiel, rien du bulletin. Conseiller :
le LLM est appelé avec le bulletin, et peut le citer.
"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rag_sav.generation.llm as llm  # noqa: E402
import rag_sav.generation.referentiel as referentiel  # noqa: E402
import rag_sav.recherche as recherche_pkg  # noqa: E402
from rag_sav.generation import repondre  # noqa: E402

E52 = """Document: Referentiel_codes_erreur.xlsx
Appareil: Lave-linge — gamme WX
Section: Code E52

## Code E52 — Sonde de température de lavage défectueuse
- **Gamme :** WX (Lave-linge)
- **Modèles concernés :** WX-300, WX-350, WX-400, WX-450, WX-500, WX-550
- **Signification :** Sonde de température de lavage défectueuse
- **Conduite à tenir (client) :** Contacter le SAV. L'appareil peut continuer a laver a froid en attendant l'intervention.
- **Intervention SAV (technicien) :** Remplacer la sonde CTN (pièce 44-3311).
*Version 2025-T4*"""

REFERENTIEL = {
    "nom_fichier": "Referentiel_codes_erreur.xlsx", "section_path": "Code E52", "page_content": E52,
    "audience": "client", "correspondance_modele": "gamme", "gamme": "WX", "code_erreur": "E52",
    "modeles_couverts": ["WX-300", "WX-350", "WX-400", "WX-450", "WX-500", "WX-550"],
    "metadata": {"decoupage": "atomique", "code_erreur": "E52"}, "prevaut": False, "similarite": 0.6,
}
BULLETIN = {
    "nom_fichier": "BT-2026-007.docx", "section_path": "BT-2026-007 > Nouvelle conduite à tenir",
    "page_content": "Pour tout code E52 sur WX-500, relever le numéro de série. S'il commence par 2503 : "
                    "mise à jour firmware 4.2 via l'application.",
    "audience": "interne", "correspondance_modele": "exacte", "gamme": "WX", "modeles_couverts": ["WX-500"],
    "metadata": {}, "prevaut": True, "similarite": 0.48,
}
ANALYSE = {"question": "Mon WX-500 affiche E52", "code": "E52", "modele": "WX-500", "gamme": "WX",
           "modeles_inconnus": [], "origine_modele": "reference", "origine_gamme": "modele"}

REPONSE_CONSEILLER = (
    "Relever le numéro de série : à partir de 2503, faire installer le firmware 4.2.\n\n"
    "Sources :\n- BT-2026-007.docx — BT-2026-007 > Nouvelle conduite à tenir"
)
MESSAGES = []


def _executer(profil):
    def rechercher(question, top_k=5):
        return {"analyse": ANALYSE, "escalade": None, "resultats": [BULLETIN, REFERENTIEL],
                "diagnostic": {"contexte_faible": False, "meilleure_similarite": 0.6,
                               "filtre_applique": "modele=WX-500", "requete_plein_texte": "e52"}}

    def generer(messages, **_):
        MESSAGES.append(messages)
        return types.SimpleNamespace(texte=REPONSE_CONSEILLER, modele="faux", fournisseur="test",
                                     duree_s=1.0, jetons_prompt=1, jetons_reponse=1, jetons_par_seconde=1)

    anciens = (recherche_pkg.__dict__.get("rechercher"), llm.generer, referentiel._ligne_en_base)
    recherche_pkg.rechercher, llm.generer = rechercher, generer
    referentiel.reponse_sous_bulletin.__defaults__ = (lambda code, modele: None,)
    MESSAGES.clear()
    try:
        return repondre(ANALYSE["question"], profil=profil)
    finally:
        if anciens[0] is None:
            del recherche_pkg.rechercher
        else:
            recherche_pkg.rechercher = anciens[0]
        llm.generer = anciens[1]
        referentiel.reponse_sous_bulletin.__defaults__ = (anciens[2],)


def test_client_lit_le_referentiel_sans_rien_du_bulletin():
    r = _executer("client")
    assert r["statut"] == "repondu" and r["motif"] == "referentiel_sous_bulletin"
    assert not MESSAGES, "le LLM ne doit pas être appelé"
    for interdit in ("2503", "4.2", "BT-", "44-3311"):
        assert interdit not in r["reponse"], interdit


def test_conseiller_obtient_le_bulletin_cite():
    r = _executer("conseiller")
    assert r["profil"] == "conseiller"
    assert r["statut"] == "repondu", (r["statut"], r["motif"])
    assert "firmware 4.2" in r["reponse"]
    assert {"nom_fichier": "BT-2026-007.docx", "section_path": "BT-2026-007 > Nouvelle conduite à tenir"} in r["sources"]


def test_le_prompt_conseiller_garde_la_colonne_technicien():
    _executer("conseiller")
    systeme, utilisateur = MESSAGES[0][0]["content"], MESSAGES[0][1]["content"]
    assert "CONSEILLER SAV" in systeme
    assert "44-3311" in utilisateur
    assert "documentation INTERNE" in utilisateur


def test_le_conseiller_peut_citer_une_reference_de_piece():
    """La colonne technicien lui est destinée : 44-3311 n'est pas une fuite pour lui."""
    global REPONSE_CONSEILLER
    ancien = REPONSE_CONSEILLER
    REPONSE_CONSEILLER = ("Si le code persiste : remplacer la sonde CTN (pièce 44-3311).\n\n"
                          "Sources :\n- Referentiel_codes_erreur.xlsx — Code E52")
    try:
        r = _executer("conseiller")
    finally:
        REPONSE_CONSEILLER = ancien
    assert r["statut"] == "repondu", (r["statut"], r["motif"], r["controle"])
    assert "44-3311" in r["reponse"]


def test_profil_inconnu_refuse():
    try:
        repondre("x", profil="admin")
    except ValueError:
        return
    raise AssertionError("profil inconnu accepté")


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
