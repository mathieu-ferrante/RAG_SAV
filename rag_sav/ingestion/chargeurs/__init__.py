"""Aiguillage vers le chargeur correspondant au format du fichier."""

from pathlib import Path

from langchain_core.documents import Document

from rag_sav.ingestion.chargeurs import documents, excel, html

CHARGEURS_PAR_EXTENSION = {
    ".xlsx": excel.charger,
    ".xls": excel.charger,
    ".html": html.charger,
    ".htm": html.charger,
    ".pdf": documents.charger,
    ".docx": documents.charger,
}


def charger_document(chemin: Path) -> list[Document]:
    """Un fichier source -> un ou plusieurs Document LangChain.

    La catégorie vient du dossier parent (Manuels, FAQ, Garanties…) : elle
    détermine l'audience et la priorité du document.
    """
    chargeur = CHARGEURS_PAR_EXTENSION.get(chemin.suffix.lower())
    if chargeur is None:
        print(f"Format ignoré : {chemin.name}")
        return []

    categorie = chemin.parent.name if chemin.parent.name != "raw" else "general"
    return chargeur(chemin, categorie)
