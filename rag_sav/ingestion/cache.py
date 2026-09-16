"""Cache de conversion des documents.

La conversion d'un PDF par Docling coûte plusieurs secondes : elle fait tourner
un modèle de mise en page sur chaque page, plus un modèle de reconnaissance de
tableaux sur chaque tableau détecté. Sur 22 PDF, cela représente l'essentiel du
temps d'exécution du pipeline — et ce travail est refait à l'identique à chaque
lancement alors que les fichiers sources, eux, ne changent jamais.

On garde donc le markdown produit, indexé sur (chemin, date de modification,
taille). Un fichier modifié change de clé et sera reconverti ; les autres sont
relus instantanément.

Le cache est une simple accélération : le supprimer ne change aucun résultat.
"""

import hashlib
from pathlib import Path

from rag_sav.config import DOSSIER_CACHE


def _cle(chemin: Path) -> str:
    """Empreinte du fichier source : chemin + date de modification + taille.

    Pas de hachage du contenu : lire 150 Ko pour décider si on peut éviter
    4 secondes de calcul est inutile, et mtime + taille suffisent largement
    pour un corpus documentaire.
    """
    infos = chemin.stat()
    signature = f"{chemin.resolve()}|{int(infos.st_mtime)}|{infos.st_size}"
    return hashlib.sha1(signature.encode("utf-8")).hexdigest()


def lire(chemin: Path) -> str | None:
    """Le markdown déjà converti pour ce fichier, ou None."""
    fichier = DOSSIER_CACHE / f"{_cle(chemin)}.md"
    if not fichier.exists():
        return None
    try:
        return fichier.read_text(encoding="utf-8")
    except OSError:
        return None  # cache illisible : on reconvertit, ce n'est jamais bloquant


def ecrire(chemin: Path, contenu: str) -> None:
    DOSSIER_CACHE.mkdir(parents=True, exist_ok=True)
    try:
        (DOSSIER_CACHE / f"{_cle(chemin)}.md").write_text(contenu, encoding="utf-8")
    except OSError as erreur:
        print(f"  (cache non écrit pour {chemin.name} : {erreur})")


def vider() -> int:
    """Supprime tout le cache. Renvoie le nombre de fichiers supprimés."""
    if not DOSSIER_CACHE.exists():
        return 0
    fichiers = list(DOSSIER_CACHE.glob("*.md"))
    for fichier in fichiers:
        fichier.unlink()
    return len(fichiers)
