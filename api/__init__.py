"""L'API REST de l'assistant SAV — tout ce qui touche HTTP vit ici.

    python -m api                                  # lance l'API (http://127.0.0.1:8000/docs)
    python -m api --ajouter-conseiller jdupont     # crée un compte (ou change son mot de passe)
    python -m api --supprimer-conseiller jdupont
    python -m api --conseillers                    # liste les comptes

    api/reglages.py   réglages propres à l'API (.env)
    api/comptes.py    comptes conseillers : mots de passe hachés
    api/routes.py     l'application FastAPI et ses routes
    api/__main__.py   lancement et gestion des comptes

Le moteur (`rag_sav/`) ne sait rien de l'API : elle appelle `repondre()`,
exactement comme la console.
"""
