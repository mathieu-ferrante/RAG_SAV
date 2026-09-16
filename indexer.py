"""Point d'entrée : indexation des chunks en base.

    python indexer.py

Calcule les embeddings BGE-M3 et charge data/output/chunk dans PostgreSQL.
Purge au passage les documents retirés du corpus.
"""

from rag_sav.stockage import indexer

if __name__ == "__main__":
    indexer()
