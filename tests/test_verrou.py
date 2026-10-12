"""Le garde-fou d'entrée du moteur de réponse — sans LLM ni base.

    python tests/test_verrou.py
    pytest tests/test_verrou.py

Ces tests portent sur la DÉCISION, pas sur la recherche : les résultats sont
fabriqués à la main, exactement dans la forme que produit
`recherche/resultats.formater()`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag_sav.generation.verrou import decider_generation  # noqa: E402


def passage(
    correspondance="exacte",
    audience="client",
    fichier="Manuel_WX-450.pdf",
    gamme="WX",
    portee="modele",
):
    return {
        "nom_fichier": fichier,
        "section_path": f"{fichier} > 9. Codes erreur",
        "correspondance_modele": correspondance,
        "audience": audience,
        "modeles_couverts": ["WX-450"],
        "gamme": gamme,
        "portee": portee,
        "prevaut": False,
        "page_content": "contenu",
    }


def recherche(resultats, contexte_faible=False, modele="WX-450", gamme="WX"):
    return {
        "analyse": {"question": "q", "modele": modele, "gamme": gamme, "code": "E23"},
        "escalade": None,
        "resultats": resultats,
        "diagnostic": {"contexte_faible": contexte_faible, "meilleure_similarite": 0.71},
    }


def test_aucun_resultat():
    decision = decider_generation(recherche([]))
    assert decision["autorise"] is False
    assert decision["motif"] == "aucun_contexte"


def test_contexte_non_contraint():
    """Filtre dur à TRUE : les passages peuvent venir d'une autre gamme."""
    decision = decider_generation(recherche([passage(correspondance="non_contrainte")] * 3))
    assert decision["motif"] == "contexte_non_contraint"


def test_contexte_faible():
    decision = decider_generation(recherche([passage()], contexte_faible=True))
    assert decision["motif"] == "contexte_faible"


def test_aucune_source_citable():
    """Décision du 15/09 : l'interne se lit, il ne se cite pas."""
    internes = [
        passage(audience="interne", fichier="BT-2026-007.docx"),
        passage(audience="interne", fichier="PROC-WX-02.docx"),
    ]
    decision = decider_generation(recherche(internes))
    assert decision["motif"] == "aucune_source_citable"


def test_cas_nominal():
    decision = decider_generation(recherche([passage(), passage(correspondance="gamme")]))
    assert decision["autorise"] is True
    assert len(decision["passages"]) == 2
    assert len(decision["citables"]) == 2


def test_les_passages_non_contraints_sont_retires():
    """Un seul passage douteux ne doit pas entrer dans le contexte du LLM."""
    resultats = [
        passage(),
        passage(correspondance="non_contrainte", fichier="Manuel_LV-200.pdf"),
        passage(correspondance="transverse", fichier="CGV_Electrodomus.pdf"),
    ]
    decision = decider_generation(recherche(resultats))
    fichiers = [p["nom_fichier"] for p in decision["passages"]]
    assert "Manuel_LV-200.pdf" not in fichiers
    assert len(fichiers) == 2


def test_interne_admis_si_une_source_client_existe():
    """Un bulletin peut entrer dans le contexte : il rend la réponse exacte."""
    resultats = [passage(), passage(audience="interne", fichier="BT-2026-011.docx")]
    decision = decider_generation(recherche(resultats))
    assert decision["autorise"] is True
    assert len(decision["passages"]) == 2      # l'interne est LU
    assert len(decision["citables"]) == 1      # mais pas CITABLE


def test_ordre_des_verifications():
    """Le motif rendu doit être le plus grossier, pas le plus fin.

    Contexte non contraint ET faible : c'est « non contraint » qu'il faut
    dire, sinon on laisse croire qu'un meilleur passage aurait suffi.
    """
    decision = decider_generation(
        recherche([passage(correspondance="non_contrainte")], contexte_faible=True)
    )
    assert decision["motif"] == "contexte_non_contraint"


def test_message_toujours_renseigne():
    for decision in (
        decider_generation(recherche([])),
        decider_generation(recherche([passage(correspondance="non_contrainte")])),
        decider_generation(recherche([passage()], contexte_faible=True)),
        decider_generation(recherche([passage(audience="interne")])),
    ):
        assert decision["message"].strip(), decision["motif"]
        assert decision["passages"] == []


# ---------------------------------------------------------------------------
# Bulletin interne qui prévaut — option 3 (12/10) : un humain reprend la main
# ---------------------------------------------------------------------------

def bulletin(audience="interne", prevaut=True):
    b = passage(audience=audience, fichier="BT-2026-007.docx")
    b["prevaut"] = prevaut
    return b


def test_bulletin_interne_qui_prevaut_escalade():
    """WX-500 + E52 : le manuel est dépassé, le bulletin ne se diffuse pas."""
    decision = decider_generation(recherche([bulletin(), passage()]))
    assert decision["autorise"] is False
    assert decision["motif"] == "bulletin_prevaut"
    assert decision["statut"] == "escalade"
    assert decision["passages"] == []
    assert "numéro de série" in decision["message"]


def test_bulletin_qui_prevaut_ne_fuit_pas_dans_le_message():
    message = decider_generation(recherche([bulletin(), passage()]))["message"]
    for interdit in ("BT-", "firmware", "2503", "44-3311", "bulletin"):
        assert interdit not in message, interdit


def test_bulletin_prevaut_passe_avant_le_seuil():
    """Retrouvé par le code exact : sa pertinence ne se discute pas."""
    decision = decider_generation(recherche([bulletin(), passage()], contexte_faible=True))
    assert decision["motif"] == "bulletin_prevaut"


def test_bulletin_client_qui_prevaut_se_cite_normalement():
    decision = decider_generation(recherche([bulletin(audience="client"), passage()]))
    assert decision["autorise"] is True


def test_bulletin_qui_ne_prevaut_pas_reste_lu():
    """Bulletin sans le code demandé : simple contexte, pas d'escalade."""
    decision = decider_generation(recherche([bulletin(prevaut=False), passage()]))
    assert decision["autorise"] is True


def test_bulletin_d_un_autre_appareil_ignore():
    """Écarté par le rattachement à l'appareil avant d'être examiné."""
    autre = bulletin()
    autre["correspondance_modele"] = "non_contrainte"
    decision = decider_generation(recherche([autre, passage()]))
    assert decision["autorise"] is True


def test_les_refus_ordinaires_restent_des_refus():
    assert decider_generation(recherche([]))["statut"] == "refus"


# ---------------------------------------------------------------------------
# Question sans appareil — il faut répondre si le corpus répond
# ---------------------------------------------------------------------------

def sans_appareil(resultats):
    return recherche(resultats, modele=None, gamme=None)


def test_document_transverse_repond_sans_appareil():
    """« Quelle est la durée de la garantie ? » : les CGV valent pour tous.

    Rejeu du 18/09 : cette question était refusée en « contexte_non_contraint »
    avec 0 passage retenu, alors que la similarité du meilleur passage était de
    0,68. Sans modèle ni gamme, le filtre dur ne filtre rien, donc TOUT
    ressortait « non_contrainte » et la règle générale écartait tout.
    """
    cgv = passage(
        correspondance="transverse", fichier="CGV_Electrodomus.pdf",
        gamme=None, portee="global",
    )
    decision = decider_generation(sans_appareil([cgv, passage(correspondance="non_contrainte")]))
    assert decision["autorise"] is True
    assert decision["passages"] == [cgv]


def test_une_seule_gamme_repond_sans_appareil():
    """Rien à transposer : tous les passages parlent du même type d'appareil."""
    resultats = [
        passage(correspondance="non_contrainte", fichier="faq-lave-linge.html"),
        passage(correspondance="non_contrainte", fichier="Manuel_WX-400.pdf"),
    ]
    decision = decider_generation(sans_appareil(resultats))
    assert decision["autorise"] is True
    assert len(decision["passages"]) == 2


def _deux_gammes():
    return [
        passage(correspondance="non_contrainte", fichier="Manuel_WX-400.pdf", gamme="WX"),
        passage(correspondance="non_contrainte", fichier="Manuel_LV-200.pdf", gamme="LV"),
    ]


def test_plusieurs_gammes_sans_appareil_repond_par_defaut():
    """Le client veut une réponse : le LLM répond gamme par gamme (le prompt
    l'y oblige) et le moteur le signale pour que la consigne soit ajoutée."""
    decision = decider_generation(sans_appareil(_deux_gammes()))
    assert decision["autorise"] is True
    assert decision["plusieurs_gammes"] is True
    assert len(decision["passages"]) == 2


def test_plusieurs_gammes_sans_appareil_refus_si_demande():
    """Réglage REFUSER_SI_APPAREIL_NON_PRECISE=1 : on redemande la référence."""
    from rag_sav.generation import verrou

    ancien = verrou.REFUSER_SI_APPAREIL_NON_PRECISE
    verrou.REFUSER_SI_APPAREIL_NON_PRECISE = True
    try:
        decision = decider_generation(sans_appareil(_deux_gammes()))
    finally:
        verrou.REFUSER_SI_APPAREIL_NON_PRECISE = ancien
    assert decision["autorise"] is False
    assert decision["motif"] == "appareil_non_precise"
    assert "étiquette signalétique" in decision["message"]


def test_une_seule_gamme_n_est_pas_signalee_plusieurs_gammes():
    decision = decider_generation(
        sans_appareil([passage(correspondance="non_contrainte", fichier="Manuel_WX-400.pdf", gamme="WX")])
    )
    assert decision["autorise"] is True and decision["plusieurs_gammes"] is False


def test_appareil_connu_reste_strict():
    """La souplesse ne vaut QUE sans appareil : sinon le filtre dur prime."""
    decision = decider_generation(recherche([passage(correspondance="non_contrainte")]))
    assert decision["autorise"] is False
    assert decision["motif"] == "contexte_non_contraint"


def test_contexte_faible_toujours_verifie_sans_appareil():
    cgv = passage(correspondance="transverse", gamme=None, portee="global")
    decision = decider_generation(
        recherche([cgv], contexte_faible=True, modele=None, gamme=None)
    )
    assert decision["autorise"] is False
    assert decision["motif"] == "contexte_faible"


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
