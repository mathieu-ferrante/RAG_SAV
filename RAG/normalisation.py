from datetime import datetime
import re
from pathlib import Path
import pandas as pd
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from langchain_core.documents import Document

pipeline_options = PdfPipelineOptions()
pipeline_options.do_ocr = False

converter_rapide = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
    }
)


def obtenir_date_fichier(chemin: Path) -> str:
    """Retourne la date de derniere modification du fichier au format YYYY-MM-DD."""
    mtime = chemin.stat().st_mtime
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


def charger_excel(chemin: Path, categorie: str) -> list[Document]:
    documents = []
    date_modifi = obtenir_date_fichier(chemin)
    tous_les_onglets = pd.read_excel(chemin, sheet_name=None)

    for index_onglet, (nom_onglet, df) in enumerate(
        tous_les_onglets.items(), start=1
    ):
        df = df.fillna("")
        tableau_markdown = df.to_markdown(index=False)

        contenu_complet = (
            f"# {chemin.stem}\n## Onglet: {nom_onglet}\n\n{tableau_markdown}"
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
                "date_modification": date_modifi,
            },
        )
        documents.append(doc)

    return documents


def charger_html(chemin: Path, categorie: str) -> list[Document]:
    date_modifi = obtenir_date_fichier(chemin)

    try:
        texte_html = chemin.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        texte_html = chemin.read_text(encoding="latin-1")

    # Recherche d'une date de mise a jour dans le contenu HTML (ex: "9 decembre 2025")
    date_contenu = None
    match_date = re.search(
        r"(?:mise à jour le|date\s*:?)\s*([\d]{1,2}\s+[a-zA-zA-Zà-ÿ]+\s+[\d]{4})",
        texte_html,
        re.IGNORECASE,
    )
    if match_date:
        date_contenu = match_date.group(1)

    # 1. Suppression du bruit HTML
    texte_html = re.sub(
        r"<(header|nav|footer|style|script)[^>]*>.*?</\1>",
        "",
        texte_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    texte_html = re.sub(
        r'<div\s+class="updated"[^>]*>.*?</div>',
        "",
        texte_html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 2. Conversion des <summary> en titres <h3>
    texte_html = re.sub(
        r"<summary[^>]*>(.*?)</summary>",
        r"<h3>\1</h3>",
        texte_html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 3. Formattage des titres
    texte_html = re.sub(
        r"<h1[^>]*>(.*?)</h1>",
        r"\n# \1\n",
        texte_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    texte_html = re.sub(
        r"<h2[^>]*>(.*?)</h2>",
        r"\n## \1\n",
        texte_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    texte_html = re.sub(
        r"<h3[^>]*>(.*?)</h3>",
        r"\n### \1\n",
        texte_html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 4. Suppression des balises HTML restantes
    texte_propre = re.sub(r"<[^>]+>", "", texte_html)

    lignes = [
        ligne.strip() for ligne in texte_propre.splitlines() if ligne.strip()
    ]
    texte_final = "\n\n".join(lignes)

    metadata = {
        "source": str(chemin),
        "nom_fichier": chemin.name,
        "categorie": categorie,
        "type_document": "html",
        "date_modification": date_modifi,
    }
    if date_contenu:
        metadata["date_document"] = date_contenu

    return [Document(page_content=texte_final, metadata=metadata)]


def charger_avec_docling(chemin: Path, categorie: str) -> list[Document]:
    date_modifi = obtenir_date_fichier(chemin)
    resultat = converter_rapide.convert(str(chemin))
    texte_markdown = resultat.document.export_to_markdown()

    contenu_complet = f"# {chemin.stem}\n\n{texte_markdown}"

    doc = Document(
        page_content=contenu_complet,
        metadata={
            "source": str(chemin),
            "nom_fichier": chemin.name,
            "categorie": categorie,
            "type_document": chemin.suffix.replace(".", ""),
            "date_modification": date_modifi,
        },
    )

    return [doc]


def charger_document(chemin: Path) -> list[Document]:
    extension = chemin.suffix.lower()
    categorie = chemin.parent.name if chemin.parent.name != "raw" else "general"

    if extension in [".xlsx", ".xls"]:
        return charger_excel(chemin, categorie)
    elif extension in [".html", ".htm"]:
        return charger_html(chemin, categorie)
    elif extension in [".pdf", ".docx"]:
        return charger_avec_docling(chemin, categorie)
    else:
        print(f"Format ignore : {chemin.name}")
        return []