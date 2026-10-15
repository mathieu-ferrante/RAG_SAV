"""Les comptes conseillers.

Deux profils seulement :

    client      sans identifiant : la documentation interne est lue mais
                jamais citée, rien d'interne ne sort ;
    conseiller  identifiant + mot de passe : toute la documentation est
                citable, bulletins techniques et procédures SAV compris.

Les comptes vivent dans un fichier JSON (api/comptes_conseillers.json, hors
Git) : identifiant -> sel + empreinte PBKDF2-SHA256. Aucun mot de passe en
clair, nulle part. Gestion en ligne de commande (`python -m api --help`).

Pas de jeton ni de session : l'identifiant et le mot de passe accompagnent
chaque requête (HTTP Basic) et sont vérifiés à chaque fois. Supprimer un
compte coupe donc son accès immédiatement.
"""

import hashlib
import hmac
import json
import secrets
from pathlib import Path

from api.reglages import FICHIER_COMPTES

ITERATIONS = 200_000


def _lire(fichier: Path) -> dict:
    if not fichier.exists():
        return {}
    return json.loads(fichier.read_text(encoding="utf-8") or "{}")


def _ecrire(fichier: Path, comptes: dict) -> None:
    fichier.write_text(json.dumps(comptes, indent=2, ensure_ascii=False), encoding="utf-8")


def _empreinte(mot_de_passe: str, sel: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), sel, ITERATIONS).hex()


def ajouter(identifiant: str, mot_de_passe: str, fichier: Path = FICHIER_COMPTES) -> None:
    """Crée le compte, ou change son mot de passe s'il existe."""
    identifiant = identifiant.strip().lower()
    if not identifiant or ":" in identifiant:
        raise ValueError("Identifiant vide ou invalide (le caractère « : » est interdit).")
    if len(mot_de_passe) < 8:
        raise ValueError("Mot de passe trop court (8 caractères au moins).")
    sel = secrets.token_bytes(16)
    comptes = _lire(fichier)
    comptes[identifiant] = {"sel": sel.hex(), "empreinte": _empreinte(mot_de_passe, sel)}
    _ecrire(fichier, comptes)


def supprimer(identifiant: str, fichier: Path = FICHIER_COMPTES) -> bool:
    comptes = _lire(fichier)
    if comptes.pop(identifiant.strip().lower(), None) is None:
        return False
    _ecrire(fichier, comptes)
    return True


def lister(fichier: Path = FICHIER_COMPTES) -> list[str]:
    return sorted(_lire(fichier))


def verifier(identifiant: str, mot_de_passe: str, fichier: Path = FICHIER_COMPTES) -> str | None:
    """L'identifiant normalisé si le couple est bon, sinon None.

    Temps constant : un identifiant inconnu coûte autant qu'un mauvais mot de passe.
    """
    identifiant = (identifiant or "").strip().lower()
    compte = _lire(fichier).get(identifiant)
    sel = bytes.fromhex(compte["sel"]) if compte else secrets.token_bytes(16)
    calculee = _empreinte(mot_de_passe or "", sel)
    if compte and hmac.compare_digest(calculee, compte["empreinte"]):
        return identifiant
    return None
