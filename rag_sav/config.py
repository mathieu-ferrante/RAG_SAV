"""Tous les réglages du projet, au même endroit.

Rien d'autre dans le code ne lit os.getenv ni ne code un chemin en dur.
Pour changer un comportement, c'est ici.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Arborescence -----------------------------------------------------------

RACINE = Path(__file__).resolve().parent.parent

DOSSIER_RAW = RACINE / "data" / "raw"
DOSSIER_SORTIE_RAW = RACINE / "data" / "output" / "raw"
DOSSIER_SORTIE_CLEAN = RACINE / "data" / "output" / "clean"
DOSSIER_SORTIE_CHUNK = RACINE / "data" / "output" / "chunk"

# Markdown déjà converti par Docling, pour ne jamais reconvertir un fichier
# inchangé. Purement une accélération : le supprimer ne change aucun résultat.
DOSSIER_CACHE = RACINE / "data" / "output" / ".cache_conversion"

# --- Base de données --------------------------------------------------------

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "rag_db")

# --- Embeddings -------------------------------------------------------------

MODELE_EMBEDDING = os.getenv("MODELE_EMBEDDING", "BAAI/bge-m3")
DIMENSION_EMBEDDING = 1024
TAILLE_LOT_EMBEDDING = 32

# --- Conversion des documents (Docling) -------------------------------------

# Reconnaissance de la structure des tableaux :
#   "fast"     modèle rapide — suffisant pour les grilles du corpus
#   "accurate" modèle précis — nettement plus lent, utile sur des tableaux
#              fusionnés ou imbriqués
MODE_TABLEAUX = os.getenv("MODE_TABLEAUX", "fast")

# Threads alloués à Docling. 0 = laisser Docling décider.
NB_THREADS_DOCLING = int(os.getenv("NB_THREADS_DOCLING", os.cpu_count() or 4))

# --- Découpage --------------------------------------------------------------

TAILLE_CHUNK = 500
CHEVAUCHEMENT_CHUNK = 50

# En dessous de ce nombre de caractères utiles (titres markdown exclus), un
# chunk n'est qu'un titre de section orphelin : il pollue le classement.
TAILLE_MINIMALE_CONTENU = 30

# --- Recherche --------------------------------------------------------------

# Candidats remontés par chaque branche (vectorielle / plein texte) avant fusion.
TAILLE_CANDIDATS = 30

# Constante de lissage du Reciprocal Rank Fusion (valeur de la publication
# d'origine : évite qu'un rang 1 écrase tout le reste).
CONSTANTE_RRF = 60.0

# ATTENTION : valeur d'attente, à recalibrer sur le jeu d'évaluation.
# En dessous, le meilleur passage retenu ne traite probablement pas le sujet.
SEUIL_SIMILARITE_PROVISOIRE = 0.45
