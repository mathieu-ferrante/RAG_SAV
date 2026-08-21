import html
import re
from langchain_core.documents import Document


def nettoyer_texte(texte: str) -> str:
    if not texte:
        return ""

    texte = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", texte)
    texte = re.sub(r"[\uE000-\uF8FF]", "", texte)

    texte = html.unescape(texte)

    texte = re.sub(
        r"^[ \t]*[-*+•][ \t]+[-*+•][ \t]*", "- ", texte, flags=re.MULTILINE
    )
    texte = re.sub(r"^[ \t]*[•▪►][ \t]*", "- ", texte, flags=re.MULTILINE)

    texte = re.sub(r"!\[.*?\]\(.*?\)", "", texte)
    texte = re.sub(r"(?i)page\s+\d+(\s*(sur|/)\s*\d+)?", "", texte)

    texte = re.sub(r"^#{1,6}\s*$", "", texte, flags=re.MULTILINE)

    lignes_nettoyees = []
    for ligne in texte.splitlines():
        ligne_traitee = re.sub(r"[ \t]+", " ", ligne.strip())
        lignes_nettoyees.append(ligne_traitee)

    texte = "\n".join(lignes_nettoyees)
    texte = re.sub(r"\n{3,}", "\n\n", texte)

    return texte.strip()


def nettoyer_document_langchain(doc: Document) -> Document:
    doc.page_content = nettoyer_texte(doc.page_content)
    return doc