"""Le prompt : une réponse d'abord, et rien de technicien dans le contexte.

    python tests/test_prompt.py
    pytest tests/test_prompt.py

Sans base, sans LLM, sans réseau.
"""

import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from rag_sav.generation import prompt  # noqa: E402

REFERENTIEL = """Document: Referentiel_codes_erreur.xlsx
Appareil: Lave-linge — gamme WX
Section: Code E52

# Référentiel des codes erreur — Lave-linge serie WX
## Code E52 — Sonde de température de lavage défectueuse
- **Gamme :** WX (Lave-linge)
- **Signification :** Sonde de température de lavage défectueuse
- **Conduite à tenir (client) :** Contacter le SAV. L'appareil peut continuer a
  laver a froid en attendant l'intervention.
- **Intervention SAV (technicien) :** Remplacer la sonde CTN (pièce 44-3311),
  puis vérifier le faisceau.
*Version 2025-T4 (arrêtée au 15 décembre 2025) — maintenu par le bureau d'études*"""

PASSAGE = {
    "nom_fichier": "Referentiel_codes_erreur.xlsx",
    "section_path": "Code E52",
    "page_content": REFERENTIEL,
    "audience": "client",
    "correspondance_modele": "gamme",
    "modeles_couverts": ["WX-450"],
}

ANALYSE = {"question": "mon wx450 affiche e52", "code": "E52", "modele": "WX-450", "gamme": "WX"}


def test_la_colonne_technicien_n_entre_pas_dans_le_contexte():
    messages = prompt.construire(ANALYSE["question"], [PASSAGE], ANALYSE)
    utilisateur = messages[1]["content"]
    assert "Intervention SAV" not in utilisateur
    assert "44-3311" not in utilisateur
    assert "faisceau" not in utilisateur


def test_la_conduite_client_et_la_version_restent():
    corps = prompt.corps_du_passage(REFERENTIEL)
    assert "Conduite à tenir (client)" in corps
    assert "laver a froid" in corps  # la ligne de suite de la conduite client
    assert "Version 2025-T4" in corps
    assert "Signification" in corps


def test_un_passage_sans_colonne_technicien_est_intact():
    texte = "Document: Manuel_WX-450.pdf\nSection: 9\n\nNettoyer le filtre de vidange."
    assert prompt.corps_du_passage(texte) == "Nettoyer le filtre de vidange."


def test_une_ligne_technicien_en_derniere_position_est_retiree():
    texte = "- **Conduite à tenir (client) :** Contacter le SAV.\n- **Intervention SAV (technicien) :** Pièce 12-3456."
    corps = prompt.corps_du_passage(texte)
    assert "12-3456" not in corps and "Contacter le SAV." in corps


def test_un_passage_interne_n_est_pas_etiquete_source_autorisee():
    interne = {**PASSAGE, "nom_fichier": "BT-2026-007.docx", "section_path": "BT-2026-007", "audience": "interne"}
    contexte = prompt.formater_contexte([PASSAGE, interne], "Lave-linge WX-450")
    assert "[1] SOURCE AUTORISÉE : Referentiel_codes_erreur.xlsx" in contexte
    assert "[2] SOURCE INTERNE, NON CITABLE : BT-2026-007.docx" in contexte
    assert "SOURCE AUTORISÉE : BT-2026-007.docx" not in contexte


def test_consigne_plusieurs_gammes_seulement_sans_appareil():
    wx = {**PASSAGE, "gamme": "WX"}
    lv = {**PASSAGE, "nom_fichier": "Manuel_LV-200.pdf", "section_path": "Garantie", "gamme": "LV"}
    sans = {"question": "durée de garantie", "code": None, "modele": None, "gamme": None}
    avec_consigne = prompt.construire(sans["question"], [wx, lv], sans)[1]["content"]
    assert "CONSIGNE PARTICULIÈRE" in avec_consigne and "LV, WX" in avec_consigne
    # une seule gamme, ou un appareil connu : pas de consigne
    assert "CONSIGNE PARTICULIÈRE" not in prompt.construire("q", [wx], sans)[1]["content"]
    connu = {"question": "q", "code": None, "modele": "WX-450", "gamme": "WX"}
    assert "CONSIGNE PARTICULIÈRE" not in prompt.construire("q", [wx, lv], connu)[1]["content"]


def test_le_prompt_demande_la_reponse_avant_les_passages():
    forme = prompt.SYSTEME.split("FORME")[1]
    assert "commences par LA RÉPONSE" in forme
    assert "ne les recopies pas" in forme
    assert not re.search(r"\bpièce\b.*\b\d{2}-\d{3,4}\b", prompt.SYSTEME)


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
