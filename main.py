from pathlib import Path
from langchain_core.documents import Document

from normalisation import charger_excel, charger_avec_docling
from nettoyage import nettoyer_texte

# -------------------------------------------------------------
# DOSSIERS D'EXPORTATION
# -------------------------------------------------------------
DOSSIER_OUTPUT_RAW = Path("data/output/raw")
DOSSIER_OUTPUT_CLEAN = Path("data/output/clean")

DOSSIER_OUTPUT_RAW.mkdir(parents=True, exist_ok=True)
DOSSIER_OUTPUT_CLEAN.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------
# BOUCLE PRINCIPALE
# -------------------------------------------------------------
data_dir = Path("data")
tous_les_documents_propres: list[Document] = []
compteur = 1

for chemin in data_dir.rglob("*"):
    if (
        chemin.is_file()
        and not chemin.name.startswith(".")
        and "output" not in chemin.parts
    ):
        categorie = chemin.parent.name if chemin.parent != data_dir else "Racine"
        ext = chemin.suffix.lower()

        print(f"Traitement de : {chemin.name} ({categorie})...")

        # 1. Normalisation (Conversion en Markdown)
        docs_traites = []
        if ext in [".xlsx", ".xls"]:
            docs_traites = charger_excel(chemin, categorie)
        elif ext in [".pdf", ".docx", ".html"]:
            docs_traites = charger_avec_docling(chemin, categorie)

        for doc in docs_traites:
            nom_source = doc.metadata["nom_fichier"]

            if doc.metadata["type_document"] == "excel":
                nom_onglet = doc.metadata["onglet"].replace(" ", "_")
                nom_export = f"{compteur}_{nom_source}_onglet_{doc.metadata['onglet_index']}_{nom_onglet}.md"
            else:
                nom_export = f"{compteur}_{nom_source}.md"

            # Sauvegarde de la version normalisée brute
            chemin_raw = DOSSIER_OUTPUT_RAW / nom_export
            with open(chemin_raw, "w", encoding="utf-8") as f:
                f.write(doc.page_content)

            # 2. Nettoyage (appliqué sur le texte normalisé)
            contenu_nettoye = nettoyer_texte(doc.page_content)
            doc.page_content = contenu_nettoye

            # Sauvegarde de la version nettoyée
            chemin_clean = DOSSIER_OUTPUT_CLEAN / nom_export
            with open(chemin_clean, "w", encoding="utf-8") as f:
                f.write(doc.page_content)

            print(f"  └─► Exporté (RAW + CLEAN) : {nom_export}")
            compteur += 1

            tous_les_documents_propres.append(doc)

print(
    f"\nTerminé ! {len(tous_les_documents_propres)} document(s) nettoyé(s) dans 'data/output/clean/'."
)