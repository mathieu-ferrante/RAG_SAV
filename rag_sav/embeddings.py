"""Accès au modèle d'embedding, chargé une seule fois.

Le modèle pèse environ 2 Go : on le charge au premier appel, jamais à
l'import. Indispensable pour une API (un seul chargement au démarrage) comme
pour les tests, qui n'ont pas besoin de vecteurs.
"""

from rag_sav.config import MODELE_EMBEDDING

_modele = None


def obtenir_modele():
    global _modele
    if _modele is None:
        from sentence_transformers import SentenceTransformer

        print(f"Chargement du modèle d'embedding {MODELE_EMBEDDING}...", flush=True)
        _modele = SentenceTransformer(MODELE_EMBEDDING)
    return _modele


def vectoriser(texte: str) -> list[float]:
    """Vecteur normalisé d'un texte unique (une question)."""
    return obtenir_modele().encode(texte, normalize_embeddings=True).tolist()


def vectoriser_lot(textes: list[str], taille_lot: int = 32):
    """Vecteurs normalisés d'une liste de textes (l'indexation)."""
    return obtenir_modele().encode(
        textes,
        batch_size=taille_lot,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
