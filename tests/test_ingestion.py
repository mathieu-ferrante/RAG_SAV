"""Non-régression de l'ingestion : portée documentaire et nettoyage.

    python tests/test_ingestion.py        (aucune base requise)
    pytest tests/test_ingestion.py

Couvre les points R3a, R3b et R4 de la revue de code. Ces trois défauts avaient
en commun de ne PAS se voir sur le corpus du jour : R3a et R3b attendaient le
prochain document ajouté, R4 était visible mais seulement à l'intérieur du
texte indexé. D'où ces tests.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag_sav.ingestion.nettoyage import nettoyer_texte  # noqa: E402
from rag_sav.ingestion.portee import (  # noqa: E402
    determiner_portee,
    metadonnees_communes,
    portee_referentiel,
)


# ---------------------------------------------------------------------------
# R4 — le nettoyage ne doit plus casser le gras markdown
# ---------------------------------------------------------------------------

def test_gras_en_tete_de_puce_preserve():
    """C'est la ligne exacte des 20 chunks du référentiel."""
    ligne = "- **Gamme :** WX (Lave-linge)"
    assert nettoyer_texte(ligne) == ligne


def test_toutes_les_puces_du_referentiel_preservees():
    texte = "\n".join([
        "- **Gamme :** WX (Lave-linge)",
        "- **Modèles concernés :** WX-300, WX-350",
        "- **Signification :** Défaut de la pompe de vidange",
        "- **Conduite à tenir (client) :** Nettoyer le filtre",
        "- **Intervention SAV (technicien) :** Contrôler la pompe",
    ])
    assert nettoyer_texte(texte) == texte
    assert "- *Gamme" not in nettoyer_texte(texte)


def test_italique_en_tete_de_puce_preserve():
    ligne = "- *italique* et la suite"
    assert nettoyer_texte(ligne) == ligne


def test_puce_doublee_toujours_reduite():
    """Le motif doit continuer à faire son travail d'origine."""
    for entree, attendu in [
        ("- - Étape 1", "- Étape 1"),
        ("* * Étape 2", "- Étape 2"),
        ("-  •  Étape 3", "- Étape 3"),
        ("• Étape 4", "- Étape 4"),
    ]:
        assert nettoyer_texte(entree) == attendu, entree


# ---------------------------------------------------------------------------
# R3a — la portée n'est déduite du contenu que pour les bulletins techniques
# ---------------------------------------------------------------------------

CGV_CITANT_UN_MODELE = (
    "# Conditions générales de vente\n"
    "La garantie couvre les appareils, par exemple le WX-450, pendant 2 ans."
)


def test_document_transverse_reste_global():
    """Le CGV qui cite un modèle en exemple ne doit pas devenir un doc WX-450.

    Sinon il disparaît des recherches de TOUS les autres appareils — et c'est
    le seul document qui répond aux questions de garantie.
    """
    portee = determiner_portee(
        Path("CGV_Electrodomus.pdf"), CGV_CITANT_UN_MODELE, categorie="Garanties"
    )
    assert portee["portee"] == "global"
    assert portee["modeles_couverts"] == []


def test_bulletin_technique_garde_la_deduction_par_contenu():
    """BT-2026-007 vise le WX-500, mais son nom de fichier ne le dit pas."""
    portee = determiner_portee(
        Path("BT-2026-007.docx"),
        "Bulletin technique — anomalie constatée sur le WX-500.",
        categorie="Bulletins_techniques",
    )
    assert portee["portee"] == "modele"
    assert portee["modeles_couverts"] == ["WX-500"]
    assert portee["gamme"] == "WX"


def test_categorie_absente_ne_deduit_pas_du_contenu():
    """Par défaut (catégorie inconnue), on ne devine pas."""
    portee = determiner_portee(Path("note_interne.pdf"), CGV_CITANT_UN_MODELE)
    assert portee["portee"] == "global"


def test_nom_de_fichier_prioritaire_sur_tout():
    """Les étapes 1 à 3 ne sont pas touchées par R3a."""
    assert determiner_portee(Path("Manuel_WX-450.pdf"))["modeles_couverts"] == ["WX-450"]

    gamme = determiner_portee(Path("PROC-WX-01_Detartrage.docx"))
    assert gamme["portee"] == "gamme" and gamme["gamme"] == "WX"
    assert len(gamme["modeles_couverts"]) == 6

    faq = determiner_portee(Path("faq-lave-linge.html"))
    assert faq["portee"] == "gamme" and faq["gamme"] == "WX"


def test_metadonnees_communes_transmet_la_categorie():
    """La régression se jouerait ici : un oubli d'argument et R3a ne sert à rien."""
    base = metadonnees_communes(
        Path(__file__), "Garanties", CGV_CITANT_UN_MODELE
    )
    assert base["portee"] == "global"
    assert base["audience"] == "client"

    interne = metadonnees_communes(
        Path(__file__), "Bulletins_techniques", "Anomalie sur le WX-500."
    )
    assert interne["portee"] == "modele"
    assert interne["audience"] == "interne"
    assert interne["priorite"] == 10


# ---------------------------------------------------------------------------
# R3b — une ligne du référentiel sans gamme ne doit pas devenir « global »
# ---------------------------------------------------------------------------

def test_portee_referentiel():
    assert portee_referentiel("WX", ["WX-300", "WX-350"]) == "gamme"
    # Onglet mal nommé, mais colonne « Modèles concernés » remplie : la ligne
    # est contrainte au modèle. « global » passerait TOUS les filtres.
    assert portee_referentiel(None, ["WX-450"]) == "modele"
    # On ne sait vraiment rien : « global » est alors le seul choix honnête.
    assert portee_referentiel(None, []) == "global"


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
