"""Réponse déterministe tirée du référentiel — sans LLM, sans base.

    python tests/test_referentiel.py
    pytest tests/test_referentiel.py

Quand la question donne un code ET un appareil, et que le référentiel couvre
le couple, la réponse client est déjà rédigée dans le corpus. Ces tests
vérifient qu'on la rend telle quelle, qu'on ne rend jamais la colonne
technicien, et qu'on s'efface devant un bulletin qui fait autorité.
"""

import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from rag_sav.generation.referentiel import reponse_directe  # noqa: E402

# Recopié caractère pour caractère depuis data/output/chunk.
CONTENU_E23_LV = """Document: Referentiel_codes_erreur.xlsx
Appareil: Lave-vaisselle — gamme LV
Section: Code E23

# Référentiel des codes erreur — Lave-vaisselle serie LV
## Code E23 — Sonde de température défectueuse
- **Gamme :** LV (Lave-vaisselle)
- **Modèles concernés :** LV-100, LV-150, LV-200, LV-250, LV-300, LV-350
- **Signification :** Sonde de température défectueuse
- **Conduite à tenir (client) :** Contacter le SAV. Le lavage a température élevée est indisponible en attendant l'intervention.
- **Intervention SAV (technicien) :** Remplacer la sonde CTN (pièce 51-0790).
*Version 2025-T4 (arrêtée au 15 décembre 2025) — maintenu par le bureau d'études*"""

LIGNE_REFERENTIEL = {
    "nom_fichier": "Referentiel_codes_erreur.xlsx",
    "section_path": "Code E23",
    "page_content": CONTENU_E23_LV,
    "audience": "client",
    "code_erreur": "E23",
    "modeles_couverts": ["LV-100", "LV-150", "LV-200", "LV-250", "LV-300", "LV-350"],
    "prevaut": False,
    "metadata": {"decoupage": "atomique", "code_erreur": "E23"},
}

MANUEL = {
    "nom_fichier": "Manuel_LV-200.pdf",
    "section_path": "Manuel_LV-200 > 9. Codes erreur",
    "page_content": "Tableau des codes erreur du lave-vaisselle.",
    "audience": "client",
    "modeles_couverts": ["LV-200"],
    "prevaut": False,
    "metadata": {},
}

ANALYSE = {"code": "E23", "modele": "LV-200", "gamme": "LV"}


def test_reponse_rendue_depuis_la_conduite_a_tenir():
    directe = reponse_directe(ANALYSE, [MANUEL, LIGNE_REFERENTIEL])
    assert directe is not None
    assert "Sonde de température défectueuse" in directe["texte"]
    assert "Contacter le SAV" in directe["texte"]
    assert "LV-200" in directe["texte"]


def test_la_colonne_technicien_n_est_jamais_rendue():
    """Référence de pièce et jargon technicien ne sortent pas au client."""
    texte = reponse_directe(ANALYSE, [LIGNE_REFERENTIEL])["texte"]
    assert "51-0790" not in texte
    assert "CTN" not in texte
    assert "technicien" not in texte.lower()


def test_la_source_est_citee():
    directe = reponse_directe(ANALYSE, [LIGNE_REFERENTIEL])
    assert "Sources :" in directe["texte"]
    assert "Referentiel_codes_erreur.xlsx — Code E23" in directe["texte"]
    assert directe["sources"] == [
        {"nom_fichier": "Referentiel_codes_erreur.xlsx", "section_path": "Code E23"}
    ]


def test_un_bulletin_qui_fait_autorite_rend_la_main_au_llm():
    """Le cas E52 / WX-500 : le bulletin prévaut, ce raccourci ne sait pas arbitrer."""
    bulletin = dict(MANUEL, nom_fichier="BT-2026-007.docx", audience="interne", prevaut=True)
    assert reponse_directe(ANALYSE, [LIGNE_REFERENTIEL, bulletin]) is None


def test_modele_hors_de_la_ligne_ne_repond_pas():
    assert reponse_directe({"code": "E23", "modele": "WX-450"}, [LIGNE_REFERENTIEL]) is None


def test_sans_code_ou_sans_modele_pas_de_raccourci():
    assert reponse_directe({"code": "E23", "modele": None}, [LIGNE_REFERENTIEL]) is None
    assert reponse_directe({"code": None, "modele": "LV-200"}, [LIGNE_REFERENTIEL]) is None


def test_question_de_procedure_passe_par_le_llm():
    """Pas de code erreur : le référentiel n'a rien à dire, le LLM reprend."""
    assert reponse_directe({"code": None, "modele": "WX-400"}, [MANUEL]) is None


def test_toutes_les_lignes_du_referentiel_du_corpus_sont_exploitables():
    """Sur le corpus réel : chaque ligne atomique doit rendre une réponse.

    Ignoré si l'ingestion n'a pas encore tourné sur cette machine.
    """
    fichier = RACINE / "data" / "output" / "chunk" / "Referentiel_codes_erreur.xlsx.chunks.json"
    if not fichier.exists():
        print("  (ignoré : data/output/chunk absent)")
        return

    chunks = json.loads(fichier.read_text(encoding="utf-8"))
    testees = 0
    for chunk in chunks:
        metadata = chunk["metadata"]
        couverts = metadata.get("modeles_couverts") or []
        if metadata.get("decoupage") != "atomique" or not couverts:
            continue
        passage = {
            "nom_fichier": metadata["nom_fichier"],
            "section_path": metadata["section_path"],
            "page_content": chunk["page_content"],
            "audience": metadata.get("audience", "client"),
            "code_erreur": metadata.get("code_erreur"),
            "modeles_couverts": couverts,
            "prevaut": False,
            "metadata": metadata,
        }
        analyse = {"code": metadata["code_erreur"], "modele": couverts[0]}
        directe = reponse_directe(analyse, [passage])
        assert directe is not None, f"aucune réponse pour {metadata['section_path']}"
        # « pièce » au sens du linge (E31) et « technicien » (E23/WX) figurent
        # légitimement dans la colonne client. Ce qui ne doit JAMAIS sortir,
        # c'est une référence de pièce détachée.
        assert not re.search(r"\b\d{2}-\d{3,4}\b", directe["texte"]), metadata["section_path"]
        testees += 1
    assert testees >= 20, f"seulement {testees} lignes atomiques testées"


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
