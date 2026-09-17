"""Recherche hybride contrainte au modèle.

    question client
        -> analyser_question()   quel code erreur, quel modèle, quelle gamme
        -> decider_escalade()    peut-on répondre sans risque, sinon on escalade
        -> requete.executer()    vectoriel + plein texte, FILTRÉS sur le modèle,
                                 fusionnés par Reciprocal Rank Fusion
        -> formater()            résultats + diagnostic de confiance

Voir README.md pour le raisonnement derrière ce découpage.

**Imports paresseux (R8).** Ce module n'importe au chargement que `analyse`,
qui est de la logique pure. Tout ce qui touche PostgreSQL (`escalade`,
`requete`) ou le modèle d'embedding n'est importé qu'à l'appel de
`rechercher()`. Sans cela, `import rag_sav.recherche.analyse` — pas une seule
requête SQL — échouait sur `ModuleNotFoundError: psycopg2`, et le jeu
d'évaluation prévu en étape 9 ne pouvait pas tourner sans base.
"""

from rag_sav.recherche.analyse import analyser_question, preparer_requete_plein_texte

__all__ = [
    "rechercher",
    "analyser_question",
    "preparer_requete_plein_texte",
    "decider_escalade",
    "codes_ambigus",
]

# Noms réexportés qui tirent psycopg2 : résolus au premier accès, pas à
# l'import du package (PEP 562).
_PARESSEUX = {
    "decider_escalade": "rag_sav.recherche.escalade",
    "codes_ambigus": "rag_sav.recherche.escalade",
    "codes_referentiel": "rag_sav.recherche.escalade",
    "code_connu": "rag_sav.recherche.escalade",
}


def __getattr__(nom: str):
    module = _PARESSEUX.get(nom)
    if module is None:
        raise AttributeError(f"module {__name__!r} n'a pas d'attribut {nom!r}")

    from importlib import import_module

    return getattr(import_module(module), nom)


def rechercher(question: str, top_k: int = 5) -> dict:
    """Renvoie le contexte ET son diagnostic.

    Le moteur de réponse a besoin de savoir non seulement quels passages ont
    été retenus, mais à quel point il peut leur faire confiance.

    {
      "analyse":    ce qui a été compris de la question,
      "escalade":   None, ou le motif et le message à afficher,
      "resultats":  les passages retenus,
      "diagnostic": filtre appliqué, meilleure similarité, contexte faible…
    }
    """
    from rag_sav.embeddings import vectoriser
    from rag_sav.recherche import requete
    from rag_sav.recherche.escalade import decider_escalade
    from rag_sav.recherche.resultats import diagnostic, formater

    analyse = analyser_question(question)

    escalade = decider_escalade(analyse)
    if escalade:
        return {"analyse": analyse, "escalade": escalade, "resultats": [], "diagnostic": None}

    plein_texte = preparer_requete_plein_texte(analyse)
    lignes = requete.executer(analyse, vectoriser(question), plein_texte, top_k)
    resultats = [formater(ligne, analyse) for ligne in lignes]

    return {
        "analyse": analyse,
        "escalade": None,
        "resultats": resultats,
        "diagnostic": diagnostic(analyse, resultats, plein_texte),
    }
