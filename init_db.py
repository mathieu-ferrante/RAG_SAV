"""Point d'entrée : création de la base et du schéma.

    python init_db.py

À lancer une seule fois, avant la première indexation.
"""

from rag_sav.stockage import initialiser

if __name__ == "__main__":
    try:
        initialiser()
    except Exception as erreur:
        print(f"\nErreur lors de l'initialisation : {erreur}")
