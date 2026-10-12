"""Couche d'abstraction LLM : une fonction, plusieurs dorsales.

Décision du 15/09 : Ollama en local par défaut, bascule vers une API par une
variable du `.env`. Ce module tient cette promesse sans que le reste du code
sache jamais quel modèle répond.

Deux dorsales suffisent à couvrir à peu près tout :

    ollama   POST {URL}/api/chat              — Ollama en local
    openai   POST {URL}/chat/completions      — le format « compatible OpenAI »,
                                                que parlent Groq, Mistral,
                                                OpenRouter, Gemini (endpoint
                                                compatible), llama.cpp, vLLM…

Conséquence pratique : changer de fournisseur, c'est trois lignes de `.env`,
jamais une ligne de Python. C'est ce qui rend le benchmark local / API
possible sans toucher au moteur.

**Aucune dépendance nouvelle.** `urllib.request` est dans la bibliothèque
standard. Ajouter `requests` ou un SDK propriétaire ici, ce serait faire
entrer un fournisseur dans le code que la couche est censée en sortir.

Toutes les mesures utiles au benchmark (latence, jetons) sont remontées par la
même structure, quelle que soit la dorsale.
"""

import http.client
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from rag_sav.config import (
    ATTENTE_ENTRE_ESSAIS_LLM,
    CLE_API_LLM,
    DELAI_LLM,
    FENETRE_CONTEXTE_LLM,
    FOURNISSEUR_LLM,
    MODELE_LLM,
    MODELES_SECOURS_LLM,
    NB_ESSAIS_LLM,
    TEMPERATURE_LLM,
    URL_LLM,
)

# Erreurs HTTP qui passent d'elles-mêmes : quota saturé, service surchargé.
CODES_REESSAYABLES = (429, 500, 502, 503, 504)


class ErreurLLM(RuntimeError):
    """Le modèle n'a pas répondu. Jamais silencieux, jamais fatal.

    L'appelant transforme cette erreur en escalade : un SAV qui tombe en
    panne doit dire « je transmets à un conseiller », pas afficher une trace.
    """

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


@dataclass
class ReponseLLM:
    """Ce que rend un appel, identique d'une dorsale à l'autre."""

    texte: str
    modele: str
    fournisseur: str
    duree_s: float
    jetons_prompt: int | None = None
    jetons_reponse: int | None = None
    brut: dict = field(default_factory=dict, repr=False)

    @property
    def jetons_par_seconde(self) -> float | None:
        if not self.jetons_reponse or not self.duree_s:
            return None
        return round(self.jetons_reponse / self.duree_s, 1)


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def _poster(url: str, charge: dict, entetes: dict, delai: int) -> dict:
    corps = json.dumps(charge).encode("utf-8")
    requete = urllib.request.Request(url, data=corps, headers=entetes, method="POST")

    try:
        with urllib.request.urlopen(requete, timeout=delai) as flux:
            return json.loads(flux.read().decode("utf-8"))
    except urllib.error.HTTPError as erreur:
        detail = erreur.read().decode("utf-8", errors="replace")[:400]
        raise ErreurLLM(f"HTTP {erreur.code} sur {url} : {detail}", code=erreur.code) from erreur
    except urllib.error.URLError as erreur:
        # Cas le plus fréquent en local : Ollama n'est pas lancé.
        raise ErreurLLM(f"{url} injoignable ({erreur.reason})") from erreur
    except TimeoutError as erreur:
        raise ErreurLLM(f"{url} n'a pas répondu en {delai} s") from erreur
    except json.JSONDecodeError as erreur:
        raise ErreurLLM(f"réponse illisible de {url}") from erreur
    except (http.client.HTTPException, ConnectionError, OSError) as erreur:
        # Connexion coupée en cours de réponse (IncompleteRead, RemoteDisconnected,
        # ConnectionResetError…) : un incident réseau, pas un plantage de
        # l'assistant — on passe au modèle suivant comme pour une erreur HTTP.
        raise ErreurLLM(f"connexion interrompue avec {url} ({type(erreur).__name__})") from erreur


# ---------------------------------------------------------------------------
# Les deux dorsales
# ---------------------------------------------------------------------------

def _appel_ollama(messages: list[dict], modele: str, url: str, delai: int) -> tuple[str, dict]:
    donnees = _poster(
        f"{url.rstrip('/')}/api/chat",
        {
            "model": modele,
            "messages": messages,
            "stream": False,
            "options": {
                # Température 0 : un SAV doit répondre deux fois la même chose
                # à la même question, et un benchmark n'a aucun sens sinon.
                "temperature": TEMPERATURE_LLM,
                # num_ctx par défaut d'Ollama est court : un contexte de
                # 5 passages tronqué en silence donnerait une réponse
                # incomplète sans qu'aucun message ne le signale.
                "num_ctx": FENETRE_CONTEXTE_LLM,
            },
        },
        {"Content-Type": "application/json"},
        delai,
    )
    texte = (donnees.get("message") or {}).get("content") or ""
    return texte, donnees


def _appel_openai(messages: list[dict], modele: str, url: str, delai: int) -> tuple[str, dict]:
    entetes = {"Content-Type": "application/json"}
    if CLE_API_LLM:
        entetes["Authorization"] = f"Bearer {CLE_API_LLM}"

    donnees = _poster(
        f"{url.rstrip('/')}/chat/completions",
        {"model": modele, "messages": messages, "temperature": TEMPERATURE_LLM},
        entetes,
        delai,
    )
    choix = donnees.get("choices") or []
    if not choix:
        raise ErreurLLM(f"aucune réponse dans la charge renvoyée par {url}")
    # `content` peut valoir null : un modèle « à raisonnement » (nemotron chez
    # OpenRouter) qui a consommé tous ses jetons à réfléchir. C'est une
    # réponse vide — on passe au modèle suivant, on ne plante pas.
    texte = (choix[0].get("message") or {}).get("content") or ""
    return texte, donnees


DORSALES = {"ollama": _appel_ollama, "openai": _appel_openai}


# ---------------------------------------------------------------------------
# Jetons — chaque fournisseur les nomme autrement
# ---------------------------------------------------------------------------

def _jetons(fournisseur: str, brut: dict) -> tuple[int | None, int | None]:
    if fournisseur == "ollama":
        return brut.get("prompt_eval_count"), brut.get("eval_count")
    usage = brut.get("usage") or {}
    return usage.get("prompt_tokens"), usage.get("completion_tokens")


# ---------------------------------------------------------------------------
# L'unique porte d'entrée
# ---------------------------------------------------------------------------

def generer(
    messages: list[dict],
    modele: str | None = None,
    fournisseur: str | None = None,
    url: str | None = None,
    delai: int | None = None,
) -> ReponseLLM:
    """Appelle le modèle configuré et rend un objet uniforme.

    Les quatre paramètres sont surchargeables : c'est ce qui permet au
    benchmark de comparer plusieurs modèles dans un même processus, sans
    toucher au `.env` entre deux mesures.
    """
    fournisseur = (fournisseur or FOURNISSEUR_LLM).lower()
    modele_force = modele is not None
    modele = modele or MODELE_LLM
    url = url or URL_LLM
    delai = delai or DELAI_LLM

    dorsale = DORSALES.get(fournisseur)
    if dorsale is None:
        raise ErreurLLM(
            f"fournisseur « {fournisseur} » inconnu — "
            f"attendu : {', '.join(sorted(DORSALES))}"
        )

    # Les modèles de secours ne valent que pour le modèle du `.env` : quand on
    # force `modele=` (benchmark), on mesure CE modèle, pas un remplaçant.
    candidats = [modele] if modele_force else [modele, *MODELES_SECOURS_LLM]

    depart = time.perf_counter()
    derniere: ErreurLLM | None = None

    for nom in candidats:
        for essai in range(max(1, NB_ESSAIS_LLM)):
            try:
                texte, brut = dorsale(messages, nom, url, delai)
                if not texte.strip():
                    raise ErreurLLM(f"{nom} a renvoyé une réponse vide")
            except ErreurLLM as erreur:
                derniere = erreur
                if erreur.code in CODES_REESSAYABLES and essai + 1 < max(1, NB_ESSAIS_LLM):
                    time.sleep(ATTENTE_ENTRE_ESSAIS_LLM * (essai + 1))
                    continue
                break  # autre erreur, ou essais épuisés : modèle suivant

            jetons_prompt, jetons_reponse = _jetons(fournisseur, brut)
            return ReponseLLM(
                texte=texte.strip(),
                modele=nom,
                fournisseur=fournisseur,
                duree_s=round(time.perf_counter() - depart, 2),
                jetons_prompt=jetons_prompt,
                jetons_reponse=jetons_reponse,
                brut=brut,
            )

    raise derniere


def disponible(fournisseur: str | None = None, url: str | None = None) -> bool:
    """Le service répond-il ? À appeler avant un benchmark, pas par requête."""
    fournisseur = (fournisseur or FOURNISSEUR_LLM).lower()
    url = (url or URL_LLM).rstrip("/")
    sonde = f"{url}/api/tags" if fournisseur == "ollama" else f"{url}/models"

    entetes = {}
    if fournisseur != "ollama" and CLE_API_LLM:
        entetes["Authorization"] = f"Bearer {CLE_API_LLM}"

    try:
        requete = urllib.request.Request(sonde, headers=entetes)
        with urllib.request.urlopen(requete, timeout=5) as flux:
            return flux.status == 200
    except Exception:
        return False
