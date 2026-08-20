from pathlib import Path
import pandas as pd
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from langchain_core.documents import Document

# Configuration Docling (sans OCR)
pipeline_options = PdfPipelineOptions()
pipeline_options.do_ocr = False

converter_rapide = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
    }
)


def charger_excel(chemin: Path, categorie: str) -> list[Document]:
    """Charge un fichier Excel (tous les onglets) et le convertit en tableaux Markdown."""
    documents = []
    tous_les_onglets = pd.read_excel(chemin, sheet_name=None)

    for index_onglet, (nom_onglet, df) in enumerate(
        tous_les_onglets.items(), start=1
    ):
        df = df.fillna("")
        tableau_markdown = df.to_markdown(index=False)

        contenu_complet = (
            f"--- DOCUMENT EXCEL : {chemin.name} ---\n"
            f"--- FEUILLE N°{index_onglet} : {nom_onglet} ---\n\n"
            f"{tableau_markdown}"
        )

        doc = Document(
            page_content=contenu_complet,
            metadata={
                "source": str(chemin),
                "nom_fichier": chemin.name,
                "categorie": categorie,
                "onglet": nom_onglet,
                "onglet_index": index_onglet,
                "type_document": "excel",
            },
        )
        documents.append(doc)

    return documents


def charger_avec_docling(chemin: Path, categorie: str) -> list[Document]:
    """Charge un fichier PDF, DOCX ou HTML avec Docling et le convertit en Markdown."""
    resultat = converter_rapide.convert(str(chemin))
    texte_markdown_complet = resultat.document.export_to_markdown()

    contenu_complet = (
        f"--- DOCUMENT : {chemin.name} ---\n\n"
        f"{texte_markdown_complet}"
    )

    doc = Document(
        page_content=contenu_complet,
        metadata={
            "source": str(chemin),
            "nom_fichier": chemin.name,
            "categorie": categorie,
            "type_document": chemin.suffix.replace(".", ""),
        },
    )

    return [doc]


def charger_document(chemin: Path) -> list[Document]:
    """Achemine le fichier vers la fonction appropriée et renvoie une liste de Documents."""
    extension = chemin.suffix.lower()
    categorie = chemin.parent.name if chemin.parent.name != "raw" else "general"

    if extension in [".xlsx", ".xls"]:
        return charger_excel(chemin, categorie)
    elif extension in [".pdf", ".docx", ".html", ".htm"]:
        return charger_avec_docling(chemin, categorie)
    else:
        print(f"⚠️ Format ignoré (non pris en charge) : {chemin.name}")
        return []