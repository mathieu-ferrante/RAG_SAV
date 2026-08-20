import json
from pathlib import Path
from RAG.chunking import decouper_documents
from RAG.nettoyage import nettoyer_document_langchain
from RAG.normalisation import charger_document

DOSSIER_RAW_INPUT = Path("data/raw")

DOSSIER_RAW_OUTPUT = Path("data/output/raw")
DOSSIER_CLEAN_OUTPUT = Path("data/output/clean")
DOSSIER_CHUNK_OUTPUT = Path("data/output/chunk")


def exporter_fichiers_json_par_source(
    items: list, dossier_sortie: Path, suffixe: str
) -> None:
    """Regroupe une liste de Documents/Chunks par leur nom de fichier d'origine

    et exporte un fichier JSON individuel par document source.
    """
    dossier_sortie.mkdir(parents=True, exist_ok=True)

    groupes = {}
    for item in items:
        nom_fic = item.metadata.get("nom_fichier", "document_inconnu")
        groupes.setdefault(nom_fic, []).append(item)

    for nom_fic, liste_items in groupes.items():
        fichier_sortie = dossier_sortie / f"{nom_fic}.{suffixe}.json"

        donnees = [
            {
                "id": f"{nom_fic}_{suffixe}_{idx}",
                "page_content": element.page_content,
                "metadata": element.metadata,
            }
            for idx, element in enumerate(liste_items, start=1)
        ]

        with open(fichier_sortie, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)

    print(
        f"{len(groupes)} fichier(s) JSON enregistres dans « {dossier_sortie} »."
    )


def executer_pipeline_json():
    if not DOSSIER_RAW_INPUT.exists():
        print(f"Dossier introuvable : « {DOSSIER_RAW_INPUT} ».")
        return

    # 1. Ingestion / Normalisation
    print("1. Ingestion et normalisation des documents...")
    documents_bruts = []
    for chemin in DOSSIER_RAW_INPUT.rglob("*"):
        if chemin.is_file() and not chemin.name.startswith("."):
            documents_bruts.extend(charger_document(chemin))

    if not documents_bruts:
        print("Aucun document valide trouve dans data/raw.")
        return

    print(f"   -> {len(documents_bruts)} element(s) extrait(s).")
    exporter_fichiers_json_par_source(
        documents_bruts, DOSSIER_RAW_OUTPUT, "raw"
    )

    # 2. Nettoyage
    print("2. Nettoyage des documents...")
    documents_propres = [
        nettoyer_document_langchain(doc) for doc in documents_bruts
    ]
    exporter_fichiers_json_par_source(
        documents_propres, DOSSIER_CLEAN_OUTPUT, "clean"
    )

    # 3. Chunking
    print("3. Decoupage en chunks...")
    chunks = decouper_documents(documents_propres)
    exporter_fichiers_json_par_source(
        chunks, DOSSIER_CHUNK_OUTPUT, "chunks"
    )

    print("\nPipeline execute avec succes !")


if __name__ == "__main__":
    executer_pipeline_json()