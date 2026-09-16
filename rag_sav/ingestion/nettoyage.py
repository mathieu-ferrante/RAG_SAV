"""Nettoyage du texte extrait, avant découpage."""

import html
import re

from langchain_core.documents import Document

MOTIF_CARACTERES_CONTROLE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
MOTIF_ZONE_PRIVEE = re.compile(r"[-]")  # glyphes d'icônes des PDF
MOTIF_IMAGE_MARKDOWN = re.compile(r"!\[.*?\]\(.*?\)")
MOTIF_PUCE_DOUBLE = re.compile(r"^[ \t]*[-*+•][ \t]+[-*+•][ \t]*", re.MULTILINE)
MOTIF_PUCE = re.compile(r"^[ \t]*[•▪►][ \t]*", re.MULTILINE)
MOTIF_TITRE_VIDE = re.compile(r"^#{1,6}\s*$", re.MULTILINE)

# Numéro de page isolé, en pied de page : « page 12 », « page 3 sur 40 ».
# On exige que le motif occupe la ligne entière, sinon un renvoi utile comme
# « voir page 12 » perdrait sa référence.
MOTIF_PIED_DE_PAGE = re.compile(
    r"^[ \t]*page\s+\d+(\s*(sur|/)\s*\d+)?[ \t]*$", re.IGNORECASE | re.MULTILINE
)


def nettoyer_texte(texte: str) -> str:
    if not texte:
        return ""

    texte = MOTIF_CARACTERES_CONTROLE.sub("", texte)
    texte = MOTIF_ZONE_PRIVEE.sub("", texte)
    texte = html.unescape(texte)
    texte = MOTIF_PUCE_DOUBLE.sub("- ", texte)
    texte = MOTIF_PUCE.sub("- ", texte)
    texte = MOTIF_IMAGE_MARKDOWN.sub("", texte)
    texte = MOTIF_PIED_DE_PAGE.sub("", texte)
    texte = MOTIF_TITRE_VIDE.sub("", texte)

    lignes = [re.sub(r"[ \t]+", " ", ligne.strip()) for ligne in texte.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lignes)).strip()


def nettoyer_document(doc: Document) -> Document:
    doc.page_content = nettoyer_texte(doc.page_content)
    return doc
