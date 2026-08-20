import json
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Remonte de RAG/ vers la racine si besoin, ou adapte selon ta structure
DOSSIER_CLEAN = Path("data/output/clean")
DOSSIER_CHUNK = Path("data/output/chunk")


def chunker_fichiers():
    DOSSIER_CHUNK.mkdir(parents=True, exist_ok=True)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", " ", ""],
        keep_separator=True,
    )

    fichiers = list(DOSSIER_CLEAN.glob("*.json"))

    if not fichiers:
        print(f"Aucun fichier JSON trouvé dans « {DOSSIER_CLEAN} ».")
        return

    for fichier in fichiers:
        with open(fichier, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Si le JSON est une liste d'éléments, on boucle dessus, sinon on le traite comme un seul élément
        elements = data if isinstance(data, list) else [data]

        chunks_objets = []
        global_chunk_idx = 0

        for elem in elements:
            page_content = elem.get("page_content", "")
            if not page_content:
                continue

            # Découpage du texte du bloc/page
            chunks_textes = text_splitter.split_text(page_content)
            metadata_base = elem.get("metadata", {})

            for chunk in chunks_textes:
                chunks_objets.append(
                    {
                        "id": f"{fichier.stem}_chunk_{global_chunk_idx}",
                        "page_content": chunk,
                        "metadata": {
                            **metadata_base,
                            "chunk_index": global_chunk_idx,
                            "source": fichier.name,
                        },
                    }
                )
                global_chunk_idx += 1

        # Sauvegarde aérée avec indent=2
        fichier_sortie = DOSSIER_CHUNK / f"{fichier.stem}.chunks.json"
        with open(fichier_sortie, "w", encoding="utf-8") as f:
            json.dump(chunks_objets, f, ensure_ascii=False, indent=2)

    print(
        f"Chunking terminé : fichiers structurés enregistrés dans « {DOSSIER_CHUNK} »."
    )


if __name__ == "__main__":
    chunker_fichiers()