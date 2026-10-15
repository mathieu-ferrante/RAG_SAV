"""Réglages propres à l'API, lus dans le .env (chargé par rag_sav.config)."""

import os
from pathlib import Path

from rag_sav.config import RACINE  # importer config charge aussi le .env

DOSSIER_API = RACINE / "api"

# 127.0.0.1 : l'API n'écoute que la machine locale. 0.0.0.0 pour l'ouvrir au
# réseau (derrière un pare-feu ou un reverse proxy, en HTTPS : la connexion
# conseiller fait circuler identifiant et mot de passe à chaque requête).
API_HOTE = os.getenv("API_HOTE", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Origines autorisées depuis un navigateur (CORS), séparées par des virgules.
API_ORIGINES = [o.strip() for o in os.getenv("API_ORIGINES", "").split(",") if o.strip()]

# `details: true` pour un client (non connecté) : refusé tant que ce n'est pas
# activé. Toujours ouvert à un conseiller.
API_DETAILS = os.getenv("API_DETAILS", "0").lower() in ("1", "true", "oui", "vrai")

# Comptes conseillers : identifiant -> sel + empreinte. Hors Git.
FICHIER_COMPTES = Path(os.getenv("FICHIER_COMPTES", str(DOSSIER_API / "comptes_conseillers.json")))
