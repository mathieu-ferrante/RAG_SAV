"""Contrôle des citations — la seule barrière contre une source inventée.

    python tests/test_controle.py
    pytest tests/test_controle.py

Le prompt DEMANDE de citer correctement ; ce module VÉRIFIE. Ces tests
portent sur la vérification, donc les réponses du modèle sont écrites à la
main, y compris les mauvaises.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag_sav.generation.controle import (  # noqa: E402
    motif_non_conformite,
    reparer,
    sources_probables,
    verifier,
)

MANUEL = {
    "nom_fichier": "Manuel_WX-450.pdf",
    "section_path": "Manuel_WX-450 > 9. Codes erreur",
    "audience": "client",
}
REFERENTIEL = {
    "nom_fichier": "Referentiel_codes_erreur.xlsx",
    "section_path": "Referentiel > Code E23",
    "audience": "client",
}
BULLETIN = {
    "nom_fichier": "BT-2026-007.docx",
    "section_path": "BT-2026-007 > Procédure",
    "audience": "interne",
}

PASSAGES = [MANUEL, REFERENTIEL, BULLETIN]

BONNE_REPONSE = """Le code E23 signale un défaut de la pompe de vidange.
Nettoyez le filtre de vidange, puis relancez un programme Vidange seule.

Sources :
- Manuel_WX-450.pdf — Manuel_WX-450 > 9. Codes erreur"""


def test_citation_conforme():
    controle = verifier(BONNE_REPONSE, PASSAGES)
    assert controle["conforme"] is True
    assert controle["cites"] == ["Manuel_WX-450.pdf"]
    assert motif_non_conformite(controle) is None


def test_aucune_citation():
    controle = verifier("Nettoyez le filtre de vidange.", PASSAGES)
    assert controle["aucune_citation"] is True
    assert controle["conforme"] is False
    assert motif_non_conformite(controle) == "aucune_citation"


def test_citation_interne_refusee():
    """Le bulletin peut être LU, jamais cité à un client."""
    reponse = "…\n\nSources :\n- BT-2026-007.docx — BT-2026-007 > Procédure"
    controle = verifier(reponse, PASSAGES)
    assert controle["internes"] == ["BT-2026-007.docx"]
    assert controle["conforme"] is False
    assert motif_non_conformite(controle) == "citation_interne"


def test_citation_inventee_detectee():
    """Le cas qu'aucun prompt ne peut empêcher : une source plausible, fausse."""
    reponse = "…\n\nSources :\n- Manuel_WX-460.pdf — Manuel_WX-460 > 9. Codes erreur"
    controle = verifier(reponse, PASSAGES)
    assert controle["inventes"] == ["Manuel_WX-460.pdf"]
    assert controle["conforme"] is False
    assert motif_non_conformite(controle) == "citation_inventee"


def test_priorite_des_motifs():
    """Inventée d'abord : c'est la faute la plus grave des trois."""
    reponse = (
        "…\n\nSources :\n- BT-2026-007.docx — x\n- Manuel_LV-999.pdf — y"
    )
    assert motif_non_conformite(verifier(reponse, PASSAGES)) == "citation_inventee"


def test_plusieurs_citations_valides():
    reponse = (
        "…\n\nSources :\n"
        "- Manuel_WX-450.pdf — Manuel_WX-450 > 9. Codes erreur\n"
        "- Referentiel_codes_erreur.xlsx — Referentiel > Code E23"
    )
    controle = verifier(reponse, PASSAGES)
    assert controle["conforme"] is True
    assert len(controle["cites"]) == 2


def test_fichier_a_la_fois_client_et_interne():
    """Deux chunks du même fichier, l'un client l'autre interne.

    Le fichier reste citable : il existe une version destinée au client.
    Sans ce départage, un seul chunk interne rendrait tout le document
    incitable et le moteur refuserait des réponses correctes.
    """
    passages = [
        {"nom_fichier": "faq-lave-linge.html", "section_path": "FAQ > Vidange", "audience": "client"},
        {"nom_fichier": "faq-lave-linge.html", "section_path": "FAQ > Interne", "audience": "interne"},
    ]
    controle = verifier("… faq-lave-linge.html …", passages)
    assert controle["internes"] == []
    assert controle["conforme"] is True


def test_mention_dans_le_corps_compte_comme_citation():
    """Un modèle qui cite bien mais formate mal son bloc n'est pas fautif."""
    reponse = "D'après le Manuel_WX-450.pdf (section 9. Codes erreur), nettoyez le filtre."
    controle = verifier(reponse, PASSAGES)
    assert controle["conforme"] is True


# ---------------------------------------------------------------------------
# Accents — le faux positif du rejeu du 18/09
# ---------------------------------------------------------------------------

def test_citation_accentuee_reconnue():
    """Le corpus dit « Referentiel », le modèle écrit « Référentiel ».

    Rejeu réel du 18/09 : la réponse sur le code E23 du LV-200 était exacte et
    complète, et elle a été rejetée en « citation_inventee » sur ce seul
    caractère. Le nom du classeur n'a pas d'accent, l'orthographe française en
    a un : la comparaison doit se faire sur la forme normalisée.
    """
    reponse = (
        "Le code E23 signale une sonde de température défectueuse.\n\n"
        "Sources :\n- Référentiel_codes_erreur.xlsx — Referentiel > Code E23"
    )
    controle = verifier(reponse, PASSAGES)
    assert controle["cites"] == ["Referentiel_codes_erreur.xlsx"]
    assert controle["inventes"] == []
    assert controle["conforme"] is True


def test_casse_indifferente():
    controle = verifier("Voir MANUEL_WX-450.PDF pour la procédure.", PASSAGES)
    assert controle["cites"] == ["Manuel_WX-450.pdf"]
    assert controle["inventes"] == []


def test_invention_toujours_detectee_malgre_la_normalisation():
    """Normaliser ne doit pas rendre le contrôle complaisant."""
    controle = verifier("D'après Guide_Dépannage.pdf, nettoyez la pompe.", PASSAGES)
    assert controle["inventes"] == ["Guide_Dépannage.pdf"]
    assert motif_non_conformite(controle) == "citation_inventee"


# ---------------------------------------------------------------------------
# Fuite de documentation interne
# ---------------------------------------------------------------------------

def test_reference_de_piece_interne_detectee():
    """Citer l'interne sans le nommer restait invisible jusqu'ici."""
    interne = dict(BULLETIN, page_content="Remplacer le module (pièce 44-2050).")
    client = dict(MANUEL, page_content="Nettoyer le filtre de vidange.")
    reponse = (
        "Faites remplacer la pièce 44-2050 par un technicien.\n\n"
        "Sources :\n- Manuel_WX-450.pdf — Manuel_WX-450 > 9. Codes erreur"
    )
    controle = verifier(reponse, [client, interne])
    assert controle["pieces_internes"] == ["44-2050"]
    assert controle["conforme"] is False
    assert motif_non_conformite(controle) == "fuite_interne"


def test_reference_de_piece_de_la_colonne_technicien_detectee():
    """Le référentiel est client, mais PAS sa colonne « Intervention SAV (technicien) ».

    `prompt.py` retire ce champ avant l'envoi au modèle : une référence qui
    n'existe que là ne peut venir que d'un bulletin. Avant le 12/10, elle
    passait pour une information client (44-3311 sur WX-500).
    """
    referentiel = dict(
        REFERENTIEL,
        page_content="- **Conduite à tenir (client) :** Contacter le SAV.\n"
        "- **Intervention SAV (technicien) :** sonde CTN (pièce 51-0790).",
    )
    reponse = (
        "La sonde CTN (pièce 51-0790) doit être remplacée.\n\n"
        "Sources :\n- Referentiel_codes_erreur.xlsx — Referentiel > Code E23"
    )
    controle = verifier(reponse, [referentiel])
    assert controle["pieces_internes"] == ["51-0790"]
    assert controle["conforme"] is False


def test_reference_de_piece_lue_cote_client_autorisee():
    """Une référence que le client lit dans le corps d'un passage client reste citable."""
    referentiel = dict(
        REFERENTIEL,
        page_content="- **Conduite à tenir (client) :** commander le filtre (pièce 51-0790).\n"
        "- **Intervention SAV (technicien) :** remplacer le filtre (pièce 51-0790).",
    )
    reponse = (
        "Vous pouvez commander le filtre (pièce 51-0790).\n\n"
        "Sources :\n- Referentiel_codes_erreur.xlsx — Referentiel > Code E23"
    )
    controle = verifier(reponse, [referentiel])
    assert controle["pieces_internes"] == []
    assert controle["conforme"] is True


def test_44_3311_reel_detecte():
    """Le cas réel : référentiel E52 (client, colonne technicien) + bulletin BT-2026-007."""
    referentiel = dict(
        REFERENTIEL,
        page_content="## Code E52 — Sonde de température de lavage défectueuse\n"
        "- **Conduite à tenir (client) :** Contacter le SAV. L'appareil peut continuer a laver a froid.\n"
        "- **Intervention SAV (technicien) :** Remplacer la sonde CTN (pièce 44-3311).\n"
        "*Version 2025-T4 (arrêtée au 15 décembre 2025)*",
    )
    reponse = (
        "La pièce à commander est la sonde CTN 44‑3311.\n\n"
        "Sources :\n- Referentiel_codes_erreur.xlsx — Referentiel > Code E23"
    )
    controle = verifier(reponse, [referentiel, dict(BULLETIN, page_content="sonde CTN 44-3311")])
    assert "44-3311" in controle["pieces_internes"] + controle["marqueurs_internes"]
    assert motif_non_conformite(controle) == "fuite_interne"


# ---------------------------------------------------------------------------
# Réparation du bloc « Sources : »
# ---------------------------------------------------------------------------

REPONSE_SANS_SOURCES = (
    "Le code E23 signale un défaut de la pompe de vidange. Nettoyez le filtre "
    "de vidange, puis relancez un programme Vidange seule. Si le code "
    "réapparaît, contactez le SAV : la pompe doit être contrôlée."
)
PASSAGE_UTILISE = dict(
    MANUEL,
    page_content=(
        "| E23 | Défaut de la pompe de vidange | Nettoyer le filtre de vidange "
        "puis relancer un programme Vidange seule. Si le code réapparaît, "
        "contacter le SAV : la pompe doit être contrôlée par un technicien. |"
    ),
)
PASSAGE_ETRANGER = dict(
    REFERENTIEL,
    nom_fichier="Manuel_WX-400.pdf",
    section_path="Manuel_WX-400 > 4. Détartrage",
    page_content=(
        "Détartrage : versez le détartrant Electrodomus DT-200 directement "
        "dans le tambour, programme Coton 60 degrés à vide, tous les 3 mois."
    ),
)


def test_reparation_ajoute_le_bloc_manquant():
    repare = reparer(REPONSE_SANS_SOURCES, [PASSAGE_UTILISE, PASSAGE_ETRANGER])
    assert repare is not None
    texte, sources = repare
    assert texte.startswith(REPONSE_SANS_SOURCES[:40])
    assert "Sources :" in texte
    assert [s["nom_fichier"] for s in sources] == ["Manuel_WX-450.pdf"]
    assert verifier(texte, [PASSAGE_UTILISE, PASSAGE_ETRANGER])["conforme"] is True


def test_reparation_ne_cite_pas_un_passage_non_utilise():
    assert PASSAGE_ETRANGER not in sources_probables(
        REPONSE_SANS_SOURCES, [PASSAGE_UTILISE, PASSAGE_ETRANGER]
    )


def test_reparation_ne_cite_jamais_l_interne():
    interne = dict(BULLETIN, page_content=PASSAGE_UTILISE["page_content"])
    assert sources_probables(REPONSE_SANS_SOURCES, [interne]) == []
    assert reparer(REPONSE_SANS_SOURCES, [interne]) is None


def test_reparation_refusee_si_la_reponse_ne_reprend_rien():
    """Une réponse de mémoire ne doit pas se voir attribuer une source."""
    hors_sol = (
        "Débranchez votre appareil pendant dix minutes, cela résout la "
        "plupart des anomalies électroniques courantes."
    )
    assert reparer(hors_sol, [PASSAGE_ETRANGER]) is None


# ---------------------------------------------------------------------------
# Fuite de contenu interne sous une citation client — option 3 (12/10)
# ---------------------------------------------------------------------------

MANUEL_500 = {
    "nom_fichier": "Manuel_WX-500.pdf",
    "section_path": "Manuel_WX-500 > 9. Codes erreur",
    "audience": "client",
    "page_content": "| E52 | Sonde de température de lavage défectueuse | Contacter le SAV. "
    "L'appareil peut continuer a laver a froid. | E60 | Débrancher 10 minutes.",
}
BT_007 = {
    "nom_fichier": "BT-2026-007.docx",
    "section_path": "BT-2026-007 > Nouvelle conduite à tenir",
    "audience": "interne",
    "page_content": "Pour tout code E52 sur WX-500, relever le numéro de série. S'il commence "
    "par 2503 : mise à jour firmware 4.2 via l'application. Sinon remplacement sonde 44-3311.",
}

# La réponse réellement obtenue le 12/10 avec nemotron, à la ponctuation près.
REPONSE_FUITE = (
    "Pour le code E52 sur votre lave‑linge WX‑500, relevez d'abord le numéro de série. "
    "S'il commence par 2503, faites installer la mise à jour firmware 4.2 puis lancez un "
    "cycle court. Sinon, contactez le SAV.\n\nSources :\n- Manuel_WX-500.pdf — Manuel_WX-500 > 9. Codes erreur"
)


def test_fuite_interne_sous_citation_client_detectee():
    controle = verifier(REPONSE_FUITE, [MANUEL_500, BT_007])
    assert controle["conforme"] is False
    assert controle["marqueurs_internes"] == ["2503", "4.2"]
    assert motif_non_conformite(controle) == "fuite_interne"


def test_reponse_issue_du_manuel_seul_conforme():
    propre = (
        "Le code E52 signale un défaut de la sonde de température. Contactez le SAV ; "
        "vous pouvez continuer à laver à froid.\n\nSources :\n- Manuel_WX-500.pdf"
    )
    assert verifier(propre, [MANUEL_500, BT_007])["conforme"] is True


def test_marqueur_aussi_present_cote_client_n_est_pas_une_fuite():
    client = dict(MANUEL_500, page_content=MANUEL_500["page_content"] + " Firmware 4.2.")
    controle = verifier(REPONSE_FUITE.replace("2503", "récent"), [client, BT_007])
    assert controle["marqueurs_internes"] == []


def test_marqueur_donne_par_le_client_n_est_pas_une_fuite():
    """Le client peut redonner son propre numéro de série."""
    controle = verifier(
        REPONSE_FUITE.replace(" firmware 4.2", ""), [MANUEL_500, BT_007],
        question="Mon WX-500 affiche E52, son numéro de série commence par 2503",
    )
    assert controle["marqueurs_internes"] == []


def test_numeros_d_etapes_et_petits_nombres_ignores():
    """« 1. … 2. … 10 minutes » ne doivent pas accuser une réponse fondée."""
    interne = dict(BT_007, page_content="Étape 1, 2, 3 puis 5. Attendre 10 minutes.")
    texte = "1. Débranchez.\n2. Attendez 10 minutes.\n5. Relancez.\n\nSources :\n- Manuel_WX-500.pdf"
    assert verifier(texte, [MANUEL_500, interne])["marqueurs_internes"] == []


def test_tiret_insecable_et_virgule_decimale_normalises():
    texte = "Pièce 44‑3311, version 4,2.\n\nSources :\n- Manuel_WX-500.pdf"
    controle = verifier(texte, [MANUEL_500, BT_007])
    assert set(controle["marqueurs_internes"]) == {"44-3311", "4.2"}


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
