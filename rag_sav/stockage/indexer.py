"""Indexation des chunks : vecteurs BGE-M3 + plein texte PostgreSQL."""

import json

from psycopg2.extras import execute_values

from rag_sav.config import DOSSIER_SORTIE_CHUNK, TAILLE_LOT_EMBEDDING
from rag_sav.embeddings import vectoriser_lot
from rag_sav.stockage.connexion import connexion

# Métadonnées qui décrivent le DOCUMENT et non un chunk particulier.
# La version initiale recopiait telles quelles les métadonnées du PREMIER
# chunk, donc son chunk_index et ses titres — des informations fausses au
# niveau du document.
CLES_DOCUMENT = (
    "source", "nom_fichier", "categorie", "type_document",
    "date_modification", "date_document",
    "portee", "modele", "gamme", "modeles_couverts",
    "audience", "priorite", "version_referentiel",
)

INSERTION_DOCUMENT = """
INSERT INTO documents (source_file, metadata)
VALUES (%s, %s)
ON CONFLICT (source_file)
DO UPDATE SET metadata = EXCLUDED.metadata, created_at = CURRENT_TIMESTAMP;
"""

INSERTION_CHUNKS = """
INSERT INTO chunks (id, document_source, page_content, metadata, embedding)
VALUES %s
"""


def metadonnees_document(chunks: list[dict]) -> dict:
    source = chunks[0]["metadata"]
    metadata = {cle: source[cle] for cle in CLES_DOCUMENT if cle in source}
    metadata["nb_chunks"] = len(chunks)
    return metadata


def purger_documents_retires(conn, sources_presentes: set[str]) -> None:
    """Supprime de la base les documents absents du corpus.

    Sans cette purge, un bulletin technique annulé ou une procédure remplacée
    continue d'être servi aux clients : risque de conformité direct sur la
    contrainte « documentation officielle ». La suppression en cascade emporte
    les chunks associés.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT source_file FROM documents;")
        obsoletes = {ligne[0] for ligne in cur.fetchall()} - sources_presentes

        if not obsoletes:
            print("Purge : aucun document obsolète en base.")
            return

        cur.execute("DELETE FROM documents WHERE source_file = ANY(%s);", (list(obsoletes),))
        print(f"Purge : {len(obsoletes)} document(s) retiré(s) du corpus :")
        for nom in sorted(obsoletes):
            print(f"   - {nom}")


def _indexer_fichier(conn, fichier) -> str | None:
    chunks = json.loads(fichier.read_text(encoding="utf-8"))
    if not chunks:
        return None

    source = chunks[0]["metadata"].get(
        "nom_fichier", fichier.name.removesuffix(".chunks.json")
    )

    with conn.cursor() as cur:
        cur.execute(INSERTION_DOCUMENT, (source, json.dumps(metadonnees_document(chunks), ensure_ascii=False)))

    print(f"  -> embeddings pour {len(chunks)} chunk(s)...")
    vecteurs = vectoriser_lot(
        [chunk["page_content"] for chunk in chunks], TAILLE_LOT_EMBEDDING
    )

    lignes = [
        (
            chunk["id"],
            source,
            chunk["page_content"],
            json.dumps(chunk["metadata"], ensure_ascii=False),
            str(vecteurs[index].tolist()),
        )
        for index, chunk in enumerate(chunks)
    ]

    with conn.cursor() as cur:
        cur.execute("DELETE FROM chunks WHERE document_source = %s;", (source,))
        execute_values(cur, INSERTION_CHUNKS, lignes, template="(%s, %s, %s, %s, %s::vector)")

    print(f"  -> {len(lignes)} chunk(s) insérés.")
    return source


def indexer() -> None:
    fichiers = sorted(DOSSIER_SORTIE_CHUNK.glob("*.chunks.json"))
    if not fichiers:
        print(f"Aucun fichier chunk trouvé dans « {DOSSIER_SORTIE_CHUNK} ».")
        return

    sources: set[str] = set()

    with connexion(autocommit=True) as conn:
        for fichier in fichiers:
            print(f"\nIndexation de : {fichier.name}")
            source = _indexer_fichier(conn, fichier)
            if source:
                sources.add(source)

        print()
        purger_documents_retires(conn, sources)

    print("\nIndexation terminée.")
