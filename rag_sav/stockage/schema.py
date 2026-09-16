"""Création de la base et du schéma (pgvector + plein texte)."""

from rag_sav.config import DB_NAME, DIMENSION_EMBEDDING
from rag_sav.stockage.connexion import curseur

TABLE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    source_file VARCHAR(255) UNIQUE NOT NULL,
    metadata    JSONB,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

TABLE_CHUNKS = f"""
CREATE TABLE IF NOT EXISTS chunks (
    id              VARCHAR(255) PRIMARY KEY,
    document_source VARCHAR(255) REFERENCES documents(source_file) ON DELETE CASCADE,
    page_content    TEXT NOT NULL,
    metadata        JSONB,
    embedding       vector({DIMENSION_EMBEDDING}),
    fts             tsvector GENERATED ALWAYS AS (to_tsvector('french', page_content)) STORED,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

INDEX = [
    # Recherche plein texte
    "CREATE INDEX IF NOT EXISTS chunks_fts_idx ON chunks USING GIN(fts);",
    # Recherche vectorielle approchée
    "CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx "
    "ON chunks USING hnsw (embedding vector_cosine_ops);",
    # Filtre dur sur le modèle : sans cet index GIN, le filtre par métadonnées
    # imposerait un parcours complet de la table à chaque question.
    "CREATE INDEX IF NOT EXISTS chunks_metadata_idx ON chunks USING GIN(metadata);",
]


def creer_base_si_absente() -> None:
    with curseur(base="postgres", autocommit=True) as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (DB_NAME,))
        if cur.fetchone():
            print(f"Base de données « {DB_NAME} » déjà présente.")
            return
        cur.execute(f'CREATE DATABASE "{DB_NAME}";')
        print(f"Base de données « {DB_NAME} » créée.")


def creer_tables() -> None:
    with curseur(autocommit=True) as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
        )
        version = cur.fetchone()
        if version:
            print(f"Extension pgvector active (version {version['extversion']}).")

        cur.execute(TABLE_DOCUMENTS)
        cur.execute(TABLE_CHUNKS)
        print("Tables « documents » et « chunks » prêtes.")

        for requete in INDEX:
            cur.execute(requete)
        print(f"{len(INDEX)} index vérifiés / créés.")


def initialiser() -> None:
    creer_base_si_absente()
    creer_tables()
    print("\nInitialisation de la base terminée.")
