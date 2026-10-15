"""L'application FastAPI : les routes et rien d'autre.

    POST /questions      {"question": "..."}   -> statut, réponse, sources
    GET  /sante                                -> base et LLM joignables ?
    POST /cache/vider                          -> à appeler après une réindexation

Deux profils, choisis par l'authentification HTTP Basic :

    aucun identifiant           -> profil « client » : rien d'interne ne sort ;
    identifiant + mot de passe  -> profil « conseiller » : toute la doc est citable.

Dans /docs : bouton « Authorize », identifiant et mot de passe une seule fois,
puis toutes les requêtes partent en conseiller. Un identifiant faux rend 401 :
on ne retombe jamais en silence sur le profil client.

Solution temporaire, en attendant le front : le mot de passe accompagne chaque
requête (HTTPS obligatoire hors de la machine locale). Le front web passera à
un cookie de session.

L'API n'ajoute aucune logique : elle appelle `repondre()`, exactement comme la
console, et ne renvoie que ce que le profil a le droit de lire. Routes en
`def` (pas `async def`) : `repondre()` est bloquant (PostgreSQL, embedding,
LLM), FastAPI l'exécute dans son pool de threads sans figer le serveur.
"""

import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from api import comptes
from api.reglages import API_DETAILS, API_ORIGINES
from rag_sav.generation import repondre

journal = logging.getLogger("api")

app = FastAPI(
    title="Assistant SAV Electrodomus",
    version="1.1",
    description=(
        "Répond aux questions SAV à partir de la documentation indexée, ou "
        "explique pourquoi la question est transmise à un conseiller. "
        "Sans identifiant : profil client. Avec identifiant et mot de passe "
        "(bouton Authorize) : profil conseiller."
    ),
)

if API_ORIGINES:
    app.add_middleware(
        CORSMiddleware, allow_origins=API_ORIGINES, allow_methods=["GET", "POST"],
        allow_headers=["*"], allow_credentials=True,
    )


# ---------------------------------------------------------------------------
# Contrat d'échange
# ---------------------------------------------------------------------------

class Question(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, examples=["Mon lave-linge WX-450 affiche E23"])
    details: bool = Field(False, description="Diagnostic complet (conseiller, ou API_DETAILS=1).")


class Source(BaseModel):
    nom_fichier: str
    section_path: str


class Analyse(BaseModel):
    code: str | None
    modele: str | None
    gamme: str | None


class Reponse(BaseModel):
    question: str
    statut: str = Field(description="repondu | escalade | refus | non_conforme | erreur_llm")
    motif: str | None
    reponse: str = Field(description="Le texte à afficher, quel que soit le statut.")
    sources: list[Source]
    analyse: Analyse
    profil: str = Field(description="client | conseiller")
    conseiller: str | None = None
    details: dict | None = None


def _details(resultat: dict) -> dict:
    """Le diagnostic, sans le texte des passages."""
    return {
        "diagnostic": resultat.get("diagnostic"),
        "controle": resultat.get("controle"),
        "llm": resultat.get("llm"),
        "reponse_brute": resultat.get("reponse_brute"),
        "reparation": resultat.get("reparation"),
        "passages": [
            {
                "nom_fichier": p.get("nom_fichier"),
                "section_path": p.get("section_path"),
                "audience": p.get("audience_origine", p.get("audience")),
                "correspondance_modele": p.get("correspondance_modele"),
                "similarite": p.get("similarite"),
                "prevaut": p.get("prevaut"),
            }
            for p in (resultat.get("passages") or resultat.get("candidats") or [])
        ],
    }


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------

_basic = HTTPBasic(auto_error=False, description="Compte conseiller (laisser vide pour le profil client).")


def conseiller_connecte(identification: HTTPBasicCredentials | None = Depends(_basic)) -> str | None:
    """None = profil client. Identifiant présenté mais faux = 401."""
    if identification is None:
        return None
    identifiant = comptes.verifier(identification.username, identification.password)
    if identifiant is None:
        journal.warning("Identification refusée pour %r", identification.username)
        raise HTTPException(
            401, "Identifiant ou mot de passe incorrect.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return identifiant


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/questions", response_model=Reponse)
def poser_question(entree: Question, conseiller: str | None = Depends(conseiller_connecte)) -> Reponse:
    question = entree.question.strip()
    if not question:
        raise HTTPException(422, "La question est vide.")
    # Un conseiller voit déjà toute la documentation : les détails lui sont ouverts.
    if entree.details and not (API_DETAILS or conseiller):
        raise HTTPException(403, "Le mode détails est réservé aux conseillers (ou API_DETAILS=1).")

    profil = "conseiller" if conseiller else "client"
    try:
        resultat = repondre(question, profil=profil)
    except Exception:
        # Base injoignable, modèle d'embedding absent… Une panne du LLM, elle,
        # n'arrive jamais ici : repondre() la transforme en statut erreur_llm.
        journal.exception("Échec de repondre() pour %r", question)
        raise HTTPException(
            503, "Service momentanément indisponible. Votre demande peut être transmise à un conseiller."
        )

    analyse = resultat["analyse"]
    return Reponse(
        question=question,
        statut=resultat["statut"],
        motif=resultat["motif"],
        reponse=resultat["reponse"],
        sources=[Source(**s) for s in resultat["sources"]],
        analyse=Analyse(code=analyse.get("code"), modele=analyse.get("modele"), gamme=analyse.get("gamme")),
        profil=profil,
        conseiller=conseiller,
        details=_details(resultat) if entree.details else None,
    )


@app.get("/sante")
def sante() -> dict:
    """Base et LLM joignables ? 200 dans tous les cas : c'est l'état qui renseigne."""
    from rag_sav.generation.llm import disponible

    try:
        from rag_sav.stockage.connexion import curseur

        with curseur() as cur:
            cur.execute("SELECT count(*) AS n FROM chunks;")
            chunks = cur.fetchone()["n"]
        base = True
    except Exception:
        journal.exception("Base injoignable")
        chunks, base = None, False

    llm = disponible()
    return {"statut": "ok" if base and llm else "degrade", "base": base, "chunks": chunks, "llm": llm}


@app.post("/cache/vider")
def vider_cache(conseiller: str | None = Depends(conseiller_connecte)) -> dict:
    """Après `python indexer.py`, le serveur relit le référentiel sans redémarrer. Conseiller uniquement."""
    if not conseiller:
        raise HTTPException(401, "Réservé aux conseillers.", headers={"WWW-Authenticate": "Basic"})
    from rag_sav.recherche.escalade import vider_cache as vider

    vider()
    return {"statut": "ok"}
