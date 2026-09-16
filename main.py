"""Point d'entrée : ingestion du corpus.

    python main.py                  ingestion (les fichiers inchangés sont relus
                                    depuis le cache de conversion)
    python main.py --vider-cache    force la reconversion complète

Lit data/raw, produit data/output/{raw,clean,chunk}.
Étape suivante : python indexer.py
"""

import sys

from rag_sav.ingestion import cache, executer_pipeline

if __name__ == "__main__":
    if "--vider-cache" in sys.argv:
        print(f"Cache de conversion vidé ({cache.vider()} fichier(s)).")

    executer_pipeline()
