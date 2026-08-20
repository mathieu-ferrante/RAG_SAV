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

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
TARGET_DB = os.getenv("DB_NAME", "rag_db")


def create_database_if_not_exists():
    # Connexion a la base par defaut 'postgres' pour verifier/creer la base cible
    conn = psycopg2.connect(
        dbname="postgres",
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Verification de l'existence de la base
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (TARGET_DB,))
    exists = cur.fetchone()

    if not exists:
        cur.execute(f'CREATE DATABASE "{TARGET_DB}";')
        print(f"Base de donnees '{TARGET_DB}' creee avec succes.")
    else:
        print(f"Base de donnees '{TARGET_DB}' existe deja.")

    cur.close()
    conn.close()


def init_tables():
    # Connexion a la base cible pour creer l'extension et les tables
    conn = psycopg2.connect(
        dbname=TARGET_DB,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print(f"Connexion a la base '{TARGET_DB}' reussie.")

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

    # 3. Table enfant : chunks (vector 1024 pour BGE-M3)
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
    print("\nInitialisation complete de la base de donnees terminee.")


if __name__ == "__main__":
    try:
        create_database_if_not_exists()
        init_tables()
    except Exception as e:
        print("\nErreur lors de l'initialisation :")
        print(e)