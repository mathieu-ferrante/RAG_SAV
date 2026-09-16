"""Chaîne d'ingestion : fichiers sources -> chunks indexables."""

import time
from pathlib import Path

from langchain_core.documents import Document

from rag_sav.config import (
    DOSSIER_RAW,
    DOSSIER_SORTIE_CHUNK,
    DOSSIER_SORTIE_CLEAN,
    DOSSIER_SORTIE_RAW,
)
from rag_sav.ingestion.chargeurs import charger_document
from rag_sav.ingestion.chunking import decouper_documents
from rag_sav.ingestion.export import exporter_par_source, vider_dossier
from rag_sav.ingestion.nettoyage import nettoyer_document

__all__ = ["executer_pipeline", "charger_document", "decouper_documents"]


def _fichiers_sources() -> list[Path]:
    return [
        chemin
        for chemin in sorted(DOSSIER_RAW.rglob("*"))
        if chemin.is_file() and not chemin.name.startswith(".")
    ]


def _lire_corpus() -> list[Document]:
    """Convertit tous les fichiers sources, en annonçant l'avancement.

    L'affichage compte : la conversion des PDF prend plusieurs minutes au
    premier passage, et sans retour à l'écran on ne distingue pas un pipeline
    qui travaille d'un pipeline bloqué.
    """
    fichiers = _fichiers_sources()
    documents: list[Document] = []
    debut = time.perf_counter()

    for position, chemin in enumerate(fichiers, start=1):
        print(f"  [{position}/{len(fichiers)}] {chemin.name}", flush=True)
        documents.extend(charger_document(chemin))

    print(f"  Conversion terminée en {time.perf_counter() - debut:.1f} s.")
    return documents


def executer_pipeline() -> list[Document]:
    """Ingestion -> nettoyage -> découpage, avec une sortie JSON par étape."""
    if not DOSSIER_RAW.exists():
        print(f"Dossier introuvable : « {DOSSIER_RAW} ».")
        return []

    print("1. Ingestion et normalisation des documents...")
    bruts = _lire_corpus()
    if not bruts:
        print(f"Aucun document valide trouvé dans « {DOSSIER_RAW} ».")
        return []
    print(f"   -> {len(bruts)} élément(s) extrait(s).")
    vider_dossier(DOSSIER_SORTIE_RAW, "*.raw.json")
    exporter_par_source(bruts, DOSSIER_SORTIE_RAW, "raw")

    print("2. Nettoyage des documents...")
    propres = [nettoyer_document(doc) for doc in bruts]
    vider_dossier(DOSSIER_SORTIE_CLEAN, "*.clean.json")
    exporter_par_source(propres, DOSSIER_SORTIE_CLEAN, "clean")

    print("3. Découpage en chunks...")
    chunks = decouper_documents(propres)
    vider_dossier(DOSSIER_SORTIE_CHUNK, "*.chunks.json")
    exporter_par_source(chunks, DOSSIER_SORTIE_CHUNK, "chunks")

    print("\nPipeline exécuté avec succès.")
    return chunks
