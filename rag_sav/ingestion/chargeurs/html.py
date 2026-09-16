"""Chargeur HTML — les FAQ.

Conversion en markdown par expressions régulières : suffisant sur des pages
simples et maîtrisées, à remplacer par un vrai parseur (BeautifulSoup) si les
FAQ se complexifient.
"""

import re
from pathlib import Path

from langchain_core.documents import Document

from rag_sav.ingestion.portee import metadonnees_communes

MOTIF_DATE = re.compile(
    r"(?:mise à jour le|date\s*:?)\s*(\d{1,2}\s+[a-zA-Zà-ÿ]+\s+\d{4})",
    re.IGNORECASE,
)
MOTIF_BRUIT = re.compile(
    r"<(header|nav|footer|style|script)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE
)
MOTIF_BLOC_MAJ = re.compile(
    r'<div\s+class="updated"[^>]*>.*?</div>', re.DOTALL | re.IGNORECASE
)
MOTIF_SUMMARY = re.compile(r"<summary[^>]*>(.*?)</summary>", re.DOTALL | re.IGNORECASE)


def _en_markdown(html: str) -> str:
    html = MOTIF_BRUIT.sub("", html)
    html = MOTIF_BLOC_MAJ.sub("", html)

    # Les <summary> des blocs dépliants deviennent des titres de niveau 3.
    html = MOTIF_SUMMARY.sub(r"<h3>\1</h3>", html)

    # Titres HTML -> titres markdown, repris ensuite par le découpage par sections.
    for niveau, diese in ((1, "#"), (2, "##"), (3, "###")):
        html = re.sub(
            rf"<h{niveau}[^>]*>(.*?)</h{niveau}>",
            rf"\n{diese} \1\n",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

    texte = re.sub(r"<[^>]+>", "", html)
    return "\n\n".join(ligne.strip() for ligne in texte.splitlines() if ligne.strip())


def charger(chemin: Path, categorie: str) -> list[Document]:
    try:
        html = chemin.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        html = chemin.read_text(encoding="latin-1")

    # La date annoncée dans le contenu se lit AVANT le nettoyage, qui la retire.
    date_annoncee = MOTIF_DATE.search(html)

    texte = _en_markdown(html)

    metadata = metadonnees_communes(chemin, categorie, texte)
    metadata["type_document"] = "html"
    if date_annoncee:
        metadata["date_document"] = date_annoncee.group(1)

    return [Document(page_content=texte, metadata=metadata)]
