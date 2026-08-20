import os
from dotenv import load_dotenv

# Forcer l'encodage client et la langue des messages en UTF-8/Anglais
os.environ["PGCLIENTENCODING"] = "UTF8"
os.environ["LC_MESSAGES"] = "C"

# Chargement du fichier .env
try:
    load_dotenv(encoding="utf-8")
except Exception:
    load_dotenv(encoding="latin1")

import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}


def init_database():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=RealDictCursor)

        print("Connexion a PostgreSQL reussie.")

        # 1. Verification et activation de pgvector
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(
            "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
        )
        ext = cur.fetchone()
        if ext:
            print(f"Extension pgvector active (version {ext['extversion']}).")

        # 2. Table parent : documents
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                source_file VARCHAR(255) UNIQUE NOT NULL,
                metadata JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """
        )
        print("Table 'documents' prete.")

        # 3. Table enfant : chunks (dimension 1024 pour BGE-M3)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id VARCHAR(255) PRIMARY KEY,
                document_source VARCHAR(255) REFERENCES documents(source_file) ON DELETE CASCADE,
                page_content TEXT NOT NULL,
                metadata JSONB,
                embedding vector(1024), 
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """
        )
        print("Table 'chunks' prete (colonne embedding vector(1024)).")

        cur.close()
        conn.close()
        print("\nBase de donnees initialisee avec succes.")

    except Exception as e:
        print("\nErreur lors de l'initialisation :")
        print(e)


if __name__ == "__main__":
    init_database()