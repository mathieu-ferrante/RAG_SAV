"""Le moteur de réponse — étape 10.

    question
       │
       ├─ rechercher()          analyse + escalade + SQL filtré + diagnostic
       │                        ↳ escalade déclenchée : on s'arrête, statut « escalade »
       │
       ├─ decider_generation()  le contexte ramené est-il exploitable ?
       │                        ↳ non : statut « refus », le LLM n'est pas appelé
       │                        ↳ bulletin interne prévaut : statut « escalade »
       │
       ├─ referentiel.reponse_directe()  OPTIONNEL (REPONSE_DIRECTE_REFERENTIEL=1)
       │                        ↳ le référentiel couvre code+appareil : réponse sans LLM
       │
       ├─ prompt.construire()   les règles client, en texte
       ├─ llm.generer()         dorsale Ollama ou compatible OpenAI
       │                        ↳ panne : statut « erreur_llm », message d'attente
       │
       └─ controle.verifier()   les citations tiennent-elles ? rien d'interne n'a fui ?
                                ↳ bloc « Sources : » absent : on le reconstitue
                                ↳ citation fausse/interne : « non_conforme »

**Cinq statuts, un seul produit une réponse rédigée par le modèle.** C'est
voulu : sur ce projet, le silence est toujours préférable à l'invention
(contrainte client n° 2). Les quatre autres statuts portent tous un message
prêt à afficher et un motif explicable.

Imports paresseux (R8) : importer ce package ne doit charger ni psycopg2 ni
les 2 Go du modèle d'embedding, pour que le jeu d'évaluation de l'étape 11
tourne sans base.
"""

from rag_sav.config import NB_PASSAGES_CONTEXTE, REPONSE_DIRECTE_REFERENTIEL

__all__ = ["repondre"]


def _normaliser(texte: str) -> str:
    """Tirets typographiques et espaces insécables ramenés à leur forme simple."""
    for car in "‐‑‒–—―−":
        texte = texte.replace(car, "-")
    return " ".join(texte.replace("\u00a0", " ").replace("\u202f", " ").lower().split())


def _sources(texte_controle: dict, passages: list[dict], texte: str = "") -> list[dict]:
    """Les passages effectivement cités, dans l'ordre du classement.

    Le contrôle ne sait que quels FICHIERS sont nommés. Or un fichier compte
    plusieurs sections (le référentiel : une par code erreur) : citer
    « Referentiel_codes_erreur.xlsx — Code E60 » ne cite pas « … — Code E40 ».
    On affine donc par la ligne « fichier — section » telle que le prompt la
    demande ; si le modèle l'a reformulée au point de n'en retrouver aucune
    pour un fichier, on retombe sur le fichier entier plutôt que de perdre la source.
    """
    cites = set(texte_controle["cites"])
    reponse = _normaliser(texte)

    precis = {
        (p["nom_fichier"], p["section_path"])
        for p in passages
        if p["nom_fichier"] in cites
        and _normaliser(f"{p['nom_fichier']} — {p['section_path']}") in reponse
    }
    fichiers_precis = {fichier for fichier, _ in precis}

    vues, sources = set(), []
    for passage in passages:
        cle = (passage["nom_fichier"], passage["section_path"])
        if passage["nom_fichier"] not in cites or cle in vues:
            continue
        if passage["nom_fichier"] in fichiers_precis and cle not in precis:
            continue
        vues.add(cle)
        sources.append({"nom_fichier": cle[0], "section_path": cle[1]})
    return sources


def _enveloppe(recherche: dict, statut: str, message: str, motif: str | None = None) -> dict:
    return {
        "reponse_brute": None,
        "reparation": None,
        "question": recherche["analyse"]["question"],
        "analyse": recherche["analyse"],
        "diagnostic": recherche.get("diagnostic"),
        "statut": statut,
        "motif": motif,
        "reponse": message,
        "sources": [],
        "passages": [],
        # Les passages les plus proches, NON utilisés pour répondre : la
        # console les montre en annexe même quand l'assistant ne répond pas.
        "candidats": recherche.get("resultats") or [],
        "controle": None,
        "llm": None,
    }


def repondre(
    question: str,
    top_k: int | None = None,
    modele: str | None = None,
    fournisseur: str | None = None,
    url: str | None = None,
) -> dict:
    """Répond à une question client, ou explique pourquoi elle n'est pas traitée.

    `modele` / `fournisseur` / `url` ne servent qu'au benchmark : laissés à
    None, tout vient du `.env` via `config.py`.
    """
    from rag_sav.generation import controle as mod_controle
    from rag_sav.generation import prompt as mod_prompt
    from rag_sav.generation.llm import ErreurLLM, generer
    from rag_sav.generation.referentiel import reponse_directe
    from rag_sav.generation.verrou import decider_generation
    from rag_sav.recherche import rechercher

    recherche = rechercher(question, top_k=top_k or NB_PASSAGES_CONTEXTE)

    # 1. Escalade décidée avant même de chercher (escalade.py).
    if recherche["escalade"]:
        return _enveloppe(
            recherche,
            "escalade",
            recherche["escalade"]["message"],
            recherche["escalade"]["motif"],
        )

    # 2. Le contexte ramené est-il exploitable ? (verrou.py)
    decision = decider_generation(recherche)
    if not decision["autorise"]:
        return _enveloppe(
            recherche, decision.get("statut", "refus"), decision["message"], decision["motif"]
        )

    passages = decision["passages"]

    # 3. Raccourci optionnel : le référentiel couvre déjà le couple code +
    #    appareil, et sa colonne « Conduite à tenir (client) » est rendue telle
    #    quelle, sans LLM. Désactivé par défaut : le client doit lire une
    #    réponse rédigée par l'assistant, les passages n'étant que ses sources.
    directe = (
        reponse_directe(recherche["analyse"], passages)
        if REPONSE_DIRECTE_REFERENTIEL
        else None
    )
    if directe:
        enveloppe = _enveloppe(recherche, "repondu", directe["texte"], "reponse_referentiel")
        enveloppe["sources"] = directe["sources"]
        enveloppe["passages"] = passages
        return enveloppe

    messages = mod_prompt.construire(question, passages, recherche["analyse"])

    # 4. Génération. Une panne du LLM est un incident d'exploitation, pas une
    #    erreur à afficher au client.
    try:
        sortie = generer(messages, modele=modele, fournisseur=fournisseur, url=url)
    except ErreurLLM as erreur:
        repli = reponse_directe(recherche["analyse"], passages)
        if repli:
            enveloppe = _enveloppe(recherche, "repondu", repli["texte"], "repli_referentiel")
            enveloppe["sources"] = repli["sources"]
            enveloppe["passages"] = passages
            enveloppe["reponse_brute"] = f"(LLM indisponible : {erreur})"
            return enveloppe
        enveloppe = _enveloppe(
            recherche,
            "erreur_llm",
            "Notre assistant est momentanément indisponible. Je transmets "
            "votre demande à un conseiller.",
            str(erreur),
        )
        enveloppe["passages"] = passages
        return enveloppe

    # 5. Les citations tiennent-elles ? (controle.py)
    texte = sortie.texte
    verification = mod_controle.verifier(texte, passages, question)
    motif = mod_controle.motif_non_conformite(verification)
    reparation = None

    # Bloc « Sources : » oublié ou mal formaté : c'est un défaut de forme, pas
    # une invention. Nous savons quels passages ont été envoyés — on
    # reconstitue le bloc plutôt que de jeter une réponse fondée.
    if motif == "aucune_citation":
        repare = mod_controle.reparer(texte, passages)
        if repare:
            texte, _ = repare
            verification = mod_controle.verifier(texte, passages, question)
            motif = mod_controle.motif_non_conformite(verification)
            reparation = "sources_ajoutees"

    # Un petit modèle local refuse parfois de répondre, ou oublie toute
    # citation, alors que le contexte est bon. Quand le référentiel couvre
    # le couple code + appareil, le client lit sa « conduite à tenir » plutôt
    # qu'un renvoi vers un conseiller. La réponse du modèle reste conservée
    # (`reponse_brute`) pour comprendre ce qui s'est passé.
    repli = None if verification["conforme"] else reponse_directe(recherche["analyse"], passages)
    if repli:
        motif = "repli_referentiel"

    enveloppe = {
        "question": question,
        "analyse": recherche["analyse"],
        "diagnostic": recherche["diagnostic"],
        "statut": "repondu" if (verification["conforme"] or repli) else "non_conforme",
        "motif": motif,
        "reponse": (
            texte
            if verification["conforme"]
            else (repli["texte"] if repli else mod_controle.MESSAGE_NON_CONFORME)
        ),
        # La réponse brute est conservée même écartée : sans elle, impossible
        # de comprendre en benchmark POURQUOI un modèle échoue.
        "reponse_brute": sortie.texte,
        "reparation": reparation,
        "sources": (
            _sources(verification, passages, texte)
            if verification["conforme"] or not repli
            else repli["sources"]
        ),
        "passages": passages,
        "controle": verification,
        "llm": {
            "modele": sortie.modele,
            "fournisseur": sortie.fournisseur,
            "duree_s": sortie.duree_s,
            "jetons_prompt": sortie.jetons_prompt,
            "jetons_reponse": sortie.jetons_reponse,
            "jetons_par_seconde": sortie.jetons_par_seconde,
        },
    }
    return enveloppe
