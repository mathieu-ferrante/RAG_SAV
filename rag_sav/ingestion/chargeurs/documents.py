"""Chargeur PDF / DOCX via Docling — manuels, procédures, bulletins, garanties.

C'est l'étape la plus coûteuse du pipeline. Trois leviers sont appliqués ici,
par ordre d'efficacité :

1. CACHE DE CONVERSION (rag_sav/ingestion/cache.py) — un fichier inchangé n'est
   jamais reconverti. C'est ce qui fait passer un relancement de plusieurs
   minutes à quelques secondes.
2. RECONNAISSANCE DE TABLEAUX EN MODE RAPIDE — voir MODE_TABLEAUX dans
   config.py. Les tableaux du corpus (codes erreur) sont des grilles simples,
   le mode précis n'y apporte rien.
3. PARALLÉLISME — Docling utilise par défaut peu de threads.

L'OCR, lui, est déjà désactivé : le corpus est composé de PDF nativement
textuels, il n'y a aucune image de texte à reconnaître.

Docling est importé paresseusement : ouvrir la recherche ou l'API ne doit pas
coûter le chargement de ses modèles.
"""

import time
from pathlib import Path

from langchain_core.documents import Document

from rag_sav.config import MODE_TABLEAUX, NB_THREADS_DOCLING
from rag_sav.ingestion import cache
from rag_sav.ingestion.portee import metadonnees_communes

_convertisseur = None


def _options_pdf():
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    options = PdfPipelineOptions()

    # Pas d'OCR : les PDF du corpus contiennent déjà leur texte. L'activer
    # ferait tourner un moteur de reconnaissance d'images sur chaque page,
    # pour rien. À réactiver si des documents scannés entrent dans le corpus.
    options.do_ocr = False

    # Reconnaissance de la structure des tableaux : indispensable, les tableaux
    # de codes erreur des manuels en dépendent. Seul le MODE est ajustable.
    options.do_table_structure = True

    if MODE_TABLEAUX == "fast":
        try:
            from docling.datamodel.pipeline_options import TableFormerMode

            options.table_structure_options.mode = TableFormerMode.FAST
        except (ImportError, AttributeError):
            pass  # version de Docling sans ce réglage : on garde le défaut

    if NB_THREADS_DOCLING:
        try:
            from docling.datamodel.pipeline_options import AcceleratorOptions

            options.accelerator_options = AcceleratorOptions(
                num_threads=NB_THREADS_DOCLING
            )
        except (ImportError, TypeError):
            pass

    return options


def obtenir_convertisseur():
    global _convertisseur
    if _convertisseur is None:
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import DocumentConverter, PdfFormatOption

        print(
            "Initialisation de Docling "
            f"(tableaux : {MODE_TABLEAUX}, threads : {NB_THREADS_DOCLING or 'défaut'})...",
            flush=True,
        )
        print(
            "   Au tout premier lancement, Docling télécharge ses modèles "
            "(plusieurs centaines de Mo). C'est fait une fois pour toutes.",
            flush=True,
        )

        _convertisseur = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=_options_pdf())
            }
        )
    return _convertisseur


def convertir_en_markdown(chemin: Path) -> tuple[str, bool]:
    """Renvoie (markdown, depuis_le_cache)."""
    en_cache = cache.lire(chemin)
    if en_cache is not None:
        return en_cache, True

    markdown = obtenir_convertisseur().convert(str(chemin)).document.export_to_markdown()
    cache.ecrire(chemin, markdown)
    return markdown, False


def charger(chemin: Path, categorie: str) -> list[Document]:
    debut = time.perf_counter()
    markdown, depuis_cache = convertir_en_markdown(chemin)
    duree = time.perf_counter() - debut

    origine = "cache" if depuis_cache else f"converti en {duree:.1f} s"
    print(f"   {chemin.name} ({origine})", flush=True)

    if not markdown.strip():
        print(f"   /!\\ Extraction vide pour {chemin.name} — document scanné ?")

    contenu = f"# {chemin.stem}\n\n{markdown}"
    metadata = metadonnees_communes(chemin, categorie, contenu)
    metadata["type_document"] = chemin.suffix.removeprefix(".")

    return [Document(page_content=contenu, metadata=metadata)]
