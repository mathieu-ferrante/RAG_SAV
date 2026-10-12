"""Réessais et modèles de secours de la couche LLM — sans réseau.

    python tests/test_llm_secours.py
    pytest tests/test_llm_secours.py

Cas réel du 12/10 : `google/gemma-4-31b-it:free` répond HTTP 429 (quota
partagé du fournisseur saturé). Un SAV ne doit pas basculer en repli pour une
erreur qui passe en quelques secondes.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import rag_sav.generation.llm as llm  # noqa: E402

MESSAGES = [{"role": "user", "content": "test"}]


class Faux:
    """Remplace _poster : rend les réponses prévues, dans l'ordre, et note les appels."""

    def __init__(self, scenario):
        self.scenario, self.appels = list(scenario), []

    def __call__(self, url, charge, entetes, delai):
        self.appels.append(charge["model"])
        suite = self.scenario.pop(0)
        if isinstance(suite, int):
            raise llm.ErreurLLM(f"HTTP {suite} sur {url}", code=suite)
        return {"choices": [{"message": {"content": suite}}], "usage": {"prompt_tokens": 9, "completion_tokens": 3}}


def _lancer(scenario, secours=(), essais=2, **kw):
    faux = Faux(scenario)
    sauvegarde = (llm._poster, llm.time.sleep, llm.MODELES_SECOURS_LLM, llm.NB_ESSAIS_LLM, llm.MODELE_LLM)
    llm._poster, llm.time.sleep = faux, lambda s: None
    llm.MODELES_SECOURS_LLM, llm.NB_ESSAIS_LLM, llm.MODELE_LLM = list(secours), essais, "principal"
    try:
        try:
            return llm.generer(MESSAGES, fournisseur="openai", url="http://x/v1", **kw), faux, None
        except llm.ErreurLLM as erreur:
            return None, faux, erreur
    finally:
        llm._poster, llm.time.sleep, llm.MODELES_SECOURS_LLM, llm.NB_ESSAIS_LLM, llm.MODELE_LLM = sauvegarde


def test_un_429_passager_est_reessaye_sur_le_meme_modele():
    reponse, faux, erreur = _lancer([429, "ok"])
    assert erreur is None and reponse.texte == "ok" and reponse.modele == "principal"
    assert faux.appels == ["principal", "principal"]


def test_un_429_persistant_passe_au_modele_de_secours():
    reponse, faux, erreur = _lancer([429, 429, "ok"], secours=["secours"])
    assert erreur is None and reponse.modele == "secours"
    assert faux.appels == ["principal", "principal", "secours"]


def test_une_erreur_definitive_ne_est_pas_reessayee():
    """401 (clé invalide) : inutile de réessayer, on passe tout de suite au suivant."""
    reponse, faux, erreur = _lancer([401, "ok"], secours=["secours"])
    assert reponse.modele == "secours" and faux.appels == ["principal", "secours"]


def test_tout_echoue_leve_la_derniere_erreur():
    reponse, faux, erreur = _lancer([429, 429, 503, 503], secours=["secours"])
    assert reponse is None and isinstance(erreur, llm.ErreurLLM) and erreur.code == 503


def test_un_modele_force_n_a_pas_de_secours():
    """Benchmark : on mesure CE modèle, pas un remplaçant."""
    reponse, faux, erreur = _lancer([429, 429, "ok"], secours=["secours"], modele="force")
    assert reponse is None and faux.appels == ["force", "force"]


def test_content_null_passe_au_secours():
    """OpenRouter renvoie `content: null` quand un modèle à raisonnement a épuisé
    ses jetons : avant le 12/10, AttributeError et plantage de la console."""
    faux = Faux([])
    reponses = iter([
        {"choices": [{"message": {"content": None, "reasoning": "..."}}]},
        {"choices": [{"message": {"content": "par le secours"}}]},
    ])

    def poster(url, charge, entetes, delai):
        faux.appels.append(charge["model"])
        return next(reponses)

    sauvegarde = (llm._poster, llm.MODELES_SECOURS_LLM, llm.MODELE_LLM, llm.NB_ESSAIS_LLM)
    llm._poster, llm.MODELES_SECOURS_LLM, llm.MODELE_LLM, llm.NB_ESSAIS_LLM = poster, ["secours"], "principal", 1
    try:
        reponse = llm.generer(MESSAGES, fournisseur="openai", url="http://x/v1")
    finally:
        llm._poster, llm.MODELES_SECOURS_LLM, llm.MODELE_LLM, llm.NB_ESSAIS_LLM = sauvegarde
    assert reponse.modele == "secours" and reponse.texte == "par le secours"
    assert faux.appels == ["principal", "secours"]


def test_connexion_coupee_devient_erreur_llm():
    """IncompleteRead / RemoteDisconnected : une ErreurLLM, jamais une exception brute."""
    import http.client

    class Coupe:
        def __enter__(self):
            raise http.client.IncompleteRead(b"{")

        def __exit__(self, *a):
            return False

    sauvegarde = llm.urllib.request.urlopen
    llm.urllib.request.urlopen = lambda *a, **k: Coupe()
    try:
        try:
            llm._poster("http://x/v1/chat/completions", {}, {}, 1)
            assert False, "aucune erreur levée"
        except llm.ErreurLLM as erreur:
            assert "interrompue" in str(erreur)
    finally:
        llm.urllib.request.urlopen = sauvegarde


if __name__ == "__main__":
    echecs = 0
    for nom, fonction in sorted(globals().items()):
        if not nom.startswith("test_"):
            continue
        try:
            fonction()
            print(f"  ok   {nom}")
        except AssertionError as erreur:
            echecs += 1
            print(f"  ECHEC {nom} : {erreur}")
    print(f"\n{'TOUT PASSE' if not echecs else f'{echecs} echec(s)'}")
    sys.exit(1 if echecs else 0)
