"""Recherche hybride contrainte au modèle.

    question client
        -> analyser_question()   quel code erreur, quel modèle, quelle gamme
        -> decider_escalade()    peut-on répondre sans risque, sinon on escalade
        -> requete.executer()    vectoriel + plein texte, FILTRÉS sur le modèle,
                                 fusionnés par Reciprocal Rank Fusion
        -> formater()            résultats + diagnostic de confiance

Voir README.md pour le raisonnement derrière ce découpage.
"""

from rag_sav.embeddings import vectoriser
from rag_sav.recherche import requete
from rag_sav.recherche.analyse import analyser_question, preparer_requete_plein_texte
from rag_sav.recherche.escalade import codes_ambigus, decider_escalade
from rag_sav.recherche.resultats import diagnostic, formater

__all__ = [
    "rechercher",
    "analyser_question",
    "decider_escalade",
    "codes_ambigus",
]


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
