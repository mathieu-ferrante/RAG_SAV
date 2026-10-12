"""R8 — la logique pure doit s'importer sans PostgreSQL ni Docling.

    python tests/test_imports.py
    pytest tests/test_imports.py

Ce test garde une propriété d'architecture, pas un comportement : importer un
module de logique ne doit rien coûter. C'est ce qui permettra au jeu
d'évaluation (étape 9) de tourner sans base, et ce qui évite qu'un simple
`import` charge 2 Go de modèles d'embedding.

Chaque cas tourne dans un interpréteur NEUF (sous-processus) : dans le
processus courant, les modules sont déjà chargés et le test ne prouverait rien.
"""

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

# module importé -> modules qui ne doivent PAS avoir été chargés au passage
CAS = [
    ("rag_sav.recherche.analyse", ["psycopg2", "sentence_transformers", "torch"]),
    ("rag_sav.recherche", ["psycopg2", "sentence_transformers", "torch"]),
    ("rag_sav.recherche.escalade", ["psycopg2"]),
    ("rag_sav.catalogue", ["psycopg2", "pandas", "docling"]),
    ("rag_sav.ingestion.portee", ["pandas", "docling", "psycopg2"]),
    ("rag_sav.ingestion.nettoyage", ["pandas", "docling", "psycopg2"]),
    ("rag_sav.ingestion", ["pandas", "docling"]),
    # Étape 10 : le moteur de réponse ne doit pas davantage tirer la base ni
    # les modèles. C'est ce qui permettra au jeu d'évaluation de mesurer le
    # verrou et le contrôle des citations sans PostgreSQL.
    ("rag_sav.generation.verrou", ["psycopg2", "sentence_transformers", "torch"]),
    ("rag_sav.generation.controle", ["psycopg2", "pandas", "docling"]),
    ("rag_sav.generation.prompt", ["psycopg2", "pandas", "docling"]),
    ("rag_sav.generation.llm", ["psycopg2", "sentence_transformers", "torch"]),
    ("rag_sav.generation", ["psycopg2", "sentence_transformers", "torch"]),
]

MODELE = (
    "import sys; import {module}; "
    "interdits = [m for m in {interdits!r} if m in sys.modules]; "
    "print(','.join(interdits))"
)


def _modules_charges(module: str, interdits: list[str]) -> list[str]:
    resultat = subprocess.run(
        [sys.executable, "-c", MODELE.format(module=module, interdits=interdits)],
        capture_output=True, text=True, cwd=str(RACINE),
    )
    assert resultat.returncode == 0, (
        f"import {module} a échoué :\n{resultat.stderr.strip()}"
    )
    return [m for m in resultat.stdout.strip().split(",") if m]


def test_imports_sans_dependances_lourdes():
    for module, interdits in CAS:
        charges = _modules_charges(module, interdits)
        assert not charges, (
            f"importer {module} a chargé {', '.join(charges)} — "
            "l'import doit rester paresseux"
        )


def test_api_publique_toujours_accessible():
    """Les imports paresseux ne doivent pas casser les noms réexportés.

    On ne touche pas ici à `charger_document` / `decouper_documents` : les
    résoudre chargerait pandas et Docling, ce que les cas ci-dessus
    interdisent précisément. Leur accessibilité est vérifiée par le pipeline
    lui-même (`python main.py`).
    """
    from rag_sav import ingestion, recherche

    for nom in ("rechercher", "analyser_question", "decider_escalade", "codes_ambigus"):
        assert callable(getattr(recherche, nom)), nom

    assert callable(ingestion.executer_pipeline)

    from rag_sav import generation

    assert callable(generation.repondre)

    # Un nom inconnu doit lever AttributeError, pas ImportError : sinon
    # `from rag_sav.ingestion import cache` (un vrai sous-module) casserait.
    for module in (recherche, ingestion):
        try:
            module.nom_qui_nexiste_pas
        except AttributeError:
            pass
        else:
            raise AssertionError(f"{module.__name__} : AttributeError attendue")

    from rag_sav.ingestion import cache

    assert callable(cache.vider)


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
