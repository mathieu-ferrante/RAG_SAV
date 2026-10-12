"""Le moteur de réponse sans base ni LLM : le repli quand le modèle échoue.

    python tests/test_repli.py
    pytest tests/test_repli.py

Cas réel du 12/10 : `llama3.2:1b` répond « Je suis désolé, je ne peux pas
répondre » à « j'ai un code erreur E60 sur mon WX-450 », alors que le
référentiel porte la réponse. Le contrôle écarte à juste titre ce refus sans
citation — mais le client ne doit pas pour autant repartir sans réponse.

`rechercher` et `generer` sont remplacés : seule la logique de décision tourne.
"""

import sys
import types
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import rag_sav.generation.llm as llm  # noqa: E402
import rag_sav.recherche as recherche_pkg  # noqa: E402
from rag_sav.generation import repondre  # noqa: E402

LIGNE_E60 = {
    "nom_fichier": "Referentiel_codes_erreur.xlsx",
    "section_path": "Code E60",
    "page_content": """Document: Referentiel_codes_erreur.xlsx
Appareil: Lave-linge — gamme WX
Section: Code E60

# Référentiel des codes erreur — Lave-linge serie WX
## Code E60 — Défaut de communication carte electronique
- **Gamme :** WX (Lave-linge)
- **Modèles concernés :** WX-300, WX-350, WX-400, WX-450, WX-500, WX-550
- **Signification :** Défaut de communication carte electronique
- **Conduite à tenir (client) :** Débrancher l'appareil 10 minutes puis relancer. Si le code réapparaît, contacter le SAV.
- **Intervention SAV (technicien) :** Remplacer la carte de commande (pièce 44-0001).
*Version 2025-T4*""",
    "audience": "client",
    "correspondance_modele": "gamme",
    "modeles_couverts": ["WX-300", "WX-350", "WX-400", "WX-450", "WX-500", "WX-550"],
    "gamme": "WX",
    "code_erreur": "E60",
    "metadata": {"decoupage": "atomique", "code_erreur": "E60"},
    "prevaut": False,
    "similarite": 0.6968,
}

ANALYSE = {
    "question": "j'ai un code erreur E60 sur mon WX-450",
    "code": "E60", "modele": "WX-450", "gamme": "WX",
    "modeles_inconnus": [], "origine_modele": "reference", "origine_gamme": "modele",
}


def _faux_rechercher(passages, contexte_faible=False):
    def rechercher(question, top_k=5):
        return {
            "analyse": ANALYSE, "escalade": None, "resultats": passages,
            "diagnostic": {"contexte_faible": contexte_faible, "meilleure_similarite": 0.6968,
                           "filtre_applique": "modele=WX-450", "requete_plein_texte": "e60"},
        }
    return rechercher


def _faux_llm(texte=None, panne=False):
    def generer(messages, modele=None, fournisseur=None, url=None):
        if panne:
            raise llm.ErreurLLM("Ollama injoignable")
        return types.SimpleNamespace(texte=texte, modele="petit", fournisseur="ollama",
                                     duree_s=1.0, jetons_prompt=1797, jetons_reponse=55,
                                     jetons_par_seconde=2.6)
    return generer


def _repondre(texte=None, panne=False, passages=None):
    ancien = (recherche_pkg.__dict__.get("rechercher"), llm.generer)
    recherche_pkg.rechercher = _faux_rechercher(passages if passages is not None else [LIGNE_E60])
    llm.generer = _faux_llm(texte, panne)
    try:
        return repondre(ANALYSE["question"])
    finally:
        if ancien[0] is None:
            del recherche_pkg.rechercher
        else:
            recherche_pkg.rechercher = ancien[0]
        llm.generer = ancien[1]


def test_un_refus_du_modele_laisse_la_reponse_du_referentiel():
    r = _repondre("Je suis désolé, mais je ne peux pas répondre à cette question.")
    assert r["statut"] == "repondu" and r["motif"] == "repli_referentiel"
    assert "Débrancher l'appareil 10 minutes" in r["reponse"]
    assert "désolé" in r["reponse_brute"]
    assert r["sources"] == [{"nom_fichier": "Referentiel_codes_erreur.xlsx", "section_path": "Code E60"}]
    assert "44-0001" not in r["reponse"]


def test_une_reponse_conforme_du_modele_n_est_pas_remplacee():
    texte = ("Débranchez l'appareil 10 minutes puis relancez-le.\n\nSources :\n"
             "- Referentiel_codes_erreur.xlsx — Code E60")
    r = _repondre(texte)
    assert r["statut"] == "repondu" and r["motif"] is None
    assert r["reponse"] == texte


def test_les_sources_distinguent_les_sections_d_un_meme_fichier():
    """Cas réel du 12/10 : citer « Referentiel… — Code E60 » ne cite pas « … — Code E40 »."""
    e40 = {**LIGNE_E60, "section_path": "Code E40", "code_erreur": "E40",
           "page_content": LIGNE_E60["page_content"].replace("E60", "E40")}
    texte = ("Débranchez l'appareil 10 minutes puis relancez-le.\n\nSources :\n"
             "- Referentiel_codes_erreur.xlsx — Code E60")
    r = _repondre(texte, passages=[LIGNE_E60, e40])
    assert r["statut"] == "repondu"
    assert r["sources"] == [{"nom_fichier": "Referentiel_codes_erreur.xlsx", "section_path": "Code E60"}]


def test_source_reformulee_garde_le_fichier_entier():
    """Si le modèle n'a pas recopié la section, on ne perd pas la source."""
    texte = "Débranchez 10 minutes.\n\nSources :\n- Referentiel_codes_erreur.xlsx"
    r = _repondre(texte)
    assert r["sources"] == [{"nom_fichier": "Referentiel_codes_erreur.xlsx", "section_path": "Code E60"}]


def test_tirets_typographiques_toleres():
    texte = "Débranchez 10 minutes.\n\nSources :\n- Referentiel_codes_erreur.xlsx – Code E60"
    r = _repondre(texte)
    assert r["sources"] == [{"nom_fichier": "Referentiel_codes_erreur.xlsx", "section_path": "Code E60"}]


def test_panne_du_llm_avec_repli():
    r = _repondre(panne=True)
    assert r["statut"] == "repondu" and r["motif"] == "repli_referentiel"
    assert "Débrancher" in r["reponse"]


def test_sans_ligne_de_referentiel_le_refus_reste_un_refus():
    autre = {**LIGNE_E60, "nom_fichier": "Manuel_WX-450.pdf", "section_path": "9. Codes erreur",
             "metadata": {"decoupage": "normal"}, "code_erreur": None}
    r = _repondre("Je ne sais pas.", passages=[autre])
    assert r["statut"] == "non_conforme"


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
