import json
import os
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# 1. Variables d'environnement pour la connexion PostgreSQL
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "rag_db")

DOSSIER_CHUNK_INPUT = Path("data/output/chunk")

# 2. Chargement du modèle BGE-M3 (s'exécute une seule fois au démarrage)
print("Chargement du modèle d'embedding BGE-M3...")
embedding_model = SentenceTransformer("BAAI/bge-m3")


def obtenir_connexion():
    """Crée une connexion à la base PostgreSQL."""
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )


def inserer_document_parent(conn, nom_fichier: str, metadata: dict):
    """Insère la référence du fichier dans la table 'documents'.
    
    ON CONFLICT permet d'éviter les erreurs si le fichier existe déjà.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (source_file, metadata)
            VALUES (%s, %s)
            ON CONFLICT (source_file) 
            DO UPDATE SET metadata = EXCLUDED.metadata, created_at = CURRENT_TIMESTAMP;
        """,
            (nom_fichier, json.dumps(metadata, ensure_ascii=False)),
        )


def indexer_fichiers_chunks(batch_size: int = 32):
    fichiers_json = list(DOSSIER_CHUNK_INPUT.glob("*.chunks.json"))
    if not fichiers_json:
        print(f"Aucun fichier chunk trouvé dans « {DOSSIER_CHUNK_INPUT} ».")
        return

    conn = obtenir_connexion()
    conn.autocommit = True

    for fichier in fichiers_json:
        print(f"\nIndexation de : {fichier.name}")
        with open(fichier, "r", encoding="utf-8") as f:
            chunks_data = json.load(f)

        if not chunks_data:
            continue

        # A. Insertion du document parent
        premier_chunk = chunks_data[0]
        nom_source = premier_chunk["metadata"].get(
            "nom_fichier", fichier.stem
        )
        inserer_document_parent(conn, nom_source, premier_chunk["metadata"])

        # B. Préparation des textes à vectoriser
        textes_a_vectoriser = [c["page_content"] for c in chunks_data]
        print(f"  -> Calcul des embeddings pour {len(textes_a_vectoriser)} chunk(s)...")

        # C. Vectorisation par lots (normalize_embeddings=True garantit un score Cosine propre)
        embeddings = embedding_model.encode(
            textes_a_vectoriser,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )

        # D. Structure des données pour SQL
        lignes_a_inserer = []
        for idx, chunk_obj in enumerate(chunks_data):
            chunk_id = chunk_obj["id"]
            page_content = chunk_obj["page_content"]
            metadata_json = json.dumps(
                chunk_obj["metadata"], ensure_ascii=False
            )
            # Conversion de la liste de float en chaîne de caractères pour pgvector : '[0.01, -0.05, ...]'
            vector_str = str(embeddings[idx].tolist())

            lignes_a_inserer.append(
                (chunk_id, nom_source, page_content, metadata_json, vector_str)
            )

        # E. Nettoyage de l'ancien contenu et insertion groupée (Bulk Insert)
        with conn.cursor() as cur:
            # Si le fichier avait déjà été indexé, on efface ses anciens chunks
            cur.execute(
                "DELETE FROM chunks WHERE document_source = %s;", (nom_source,)
            )

            # Insertion rapide par paquet via execute_values
            # Remarque : %s::vector force PostgreSQL à caster le texte en type vectoriel pgvector
            query = """
                INSERT INTO chunks (id, document_source, page_content, metadata, embedding)
                VALUES %s
            """
            execute_values(
                cur, query, lignes_a_inserer, template="(%s, %s, %s, %s, %s::vector)"
            )

        print(f"  -> {len(lignes_a_inserer)} chunk(s) insérés avec succès.")

    conn.close()
    print("\nIndexation globale terminée !")


if __name__ == "__main__":
    indexer_fichiers_chunks()