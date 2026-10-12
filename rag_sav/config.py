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
# C'est une similarité cosinus BGE-M3 (0 à 1), pas une probabilité de bonne
# réponse. Réglable par SEUIL_SIMILARITE dans le .env ; une valeur illisible
# ou hors de [0, 1] est ignorée au profit de 0.45, avec un avertissement.
SEUIL_SIMILARITE_DEFAUT = 0.45


def _lire_seuil() -> float:
    brut = os.getenv("SEUIL_SIMILARITE")
    if brut is None or not brut.strip():
        return SEUIL_SIMILARITE_DEFAUT
    try:
        valeur = float(brut.strip().replace(",", "."))
    except ValueError:
        valeur = -1.0
    if not 0.0 <= valeur <= 1.0:
        print(
            f"/!\\ SEUIL_SIMILARITE={brut!r} invalide (attendu : un nombre entre 0 et 1) : "
            f"{SEUIL_SIMILARITE_DEFAUT} retenu."
        )
        return SEUIL_SIMILARITE_DEFAUT
    return valeur


SEUIL_SIMILARITE_PROVISOIRE = _lire_seuil()

# --- Génération (LLM) -------------------------------------------------------

# Décision du 15/09 : Ollama en local par défaut, bascule vers une API par le
# .env. Trois lignes de .env suffisent à changer de fournisseur ; aucune ligne
# de Python ne connaît le nom d'un modèle.
#
#   FOURNISSEUR_LLM=ollama   URL_LLM=http://localhost:11434
#   FOURNISSEUR_LLM=openai   URL_LLM=<base compatible OpenAI>/v1  + CLE_API_LLM
FOURNISSEUR_LLM = os.getenv("FOURNISSEUR_LLM", "ollama")
URL_LLM = os.getenv("URL_LLM", "http://localhost:11434")
MODELE_LLM = os.getenv("MODELE_LLM", "llama3.2")
CLE_API_LLM = os.getenv("CLE_API_LLM")

# 0 = déterministe. Un SAV doit répondre deux fois la même chose à la même
# question, et un benchmark n'a aucun sens à température non nulle.
TEMPERATURE_LLM = float(os.getenv("TEMPERATURE_LLM", "0"))

# Ollama tronque le contexte en SILENCE au-delà de num_ctx (2048 par défaut
# sur beaucoup de modèles) : 5 passages de 500 caractères plus le prompt
# système ne tiennent pas dedans.
FENETRE_CONTEXTE_LLM = int(os.getenv("FENETRE_CONTEXTE_LLM", "8192"))

DELAI_LLM = int(os.getenv("DELAI_LLM", "120"))

# Qui rédige la réponse quand le référentiel couvre déjà code + appareil ?
#   0 (défaut) : le LLM, à partir de la ligne du référentiel — le client lit
#                toujours une réponse rédigée, jamais un passage recopié.
#   1          : raccourci sans LLM (referentiel.reponse_directe) : la colonne
#                « Conduite à tenir (client) » est rendue telle quelle. Plus
#                rapide, aucun risque d'invention, mais le client lit un extrait.
REPONSE_DIRECTE_REFERENTIEL = os.getenv("REPONSE_DIRECTE_REFERENTIEL", "0").lower() in (
    "1", "true", "oui", "vrai",
)

# Question sans appareil dont les passages relèvent de plusieurs gammes
# (« quelle est la durée de la garantie ? ») :
#   0 (défaut) : le LLM répond quand même, gamme par gamme ou « pour tous nos
#                appareils », puis invite à préciser la référence.
#   1          : refus déterministe : on redemande la référence, sans réponse.
REFUSER_SI_APPAREIL_NON_PRECISE = os.getenv("REFUSER_SI_APPAREIL_NON_PRECISE", "0").lower() in (
    "1", "true", "oui", "vrai",
)

# Les API gratuites (OpenRouter « :free », paliers gratuits) renvoient souvent
# HTTP 429 : le quota partagé du fournisseur est saturé. Ces erreurs passent
# presque toujours en quelques secondes.
#   NB_ESSAIS_LLM            essais par modèle avant de passer au suivant
#   ATTENTE_ENTRE_ESSAIS_LLM secondes, multipliées par le numéro de l'essai
#   MODELES_SECOURS_LLM      modèles de rechange, séparés par des virgules
NB_ESSAIS_LLM = int(os.getenv("NB_ESSAIS_LLM", "2"))
ATTENTE_ENTRE_ESSAIS_LLM = float(os.getenv("ATTENTE_ENTRE_ESSAIS_LLM", "4"))
MODELES_SECOURS_LLM = [
    nom.strip() for nom in os.getenv("MODELES_SECOURS_LLM", "").split(",") if nom.strip()
]

# Passages envoyés au modèle. Au-delà, les doublons du corpus reviennent et
# diluent le contexte sans rien apporter.
NB_PASSAGES_CONTEXTE = int(os.getenv("NB_PASSAGES_CONTEXTE", "5"))

# Rattachements acceptés dans le contexte (cf. resultats._correspondance_modele).
# « non_contrainte » est volontairement absent : c'est le cas où le filtre dur
# n'avait rien à filtrer, donc où le passage peut venir d'une autre gamme.
CORRESPONDANCES_ACCEPTEES = ("exacte", "gamme", "transverse")
