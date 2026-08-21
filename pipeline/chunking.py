from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)


def decouper_documents(documents: list[Document]) -> list[Document]:
    headers_to_split_on = [
        ("#", "titre_h1"),
        ("##", "titre_h2"),
        ("###", "titre_h3"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on, strip_headers=False
    )

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", " ", ""],
    )

    chunks_finaux = []
    print(f"Début du découpage sur {len(documents)} document(s)...", flush=True)

    for doc in documents:
        if not doc.page_content or not doc.page_content.strip():
            continue

        # Sauvegarde stricte de toutes les métadonnées d'origine
        metadata_base = dict(doc.metadata)
        source_name = metadata_base.get("nom_fichier", "inconnu")

        # 1. Découpage par titres Markdown
        try:
            sections = markdown_splitter.split_text(doc.page_content)
        except Exception:
            sections = []

        if not sections:
            sections = [Document(page_content=doc.page_content, metadata={})]

        chunks_du_doc = []

        for section in sections:
            # 2. Découpage par taille de texte
            sub_chunks = text_splitter.split_documents([section])

            for sub_chunk in sub_chunks:
                h1 = sub_chunk.metadata.get("titre_h1", "")
                h2 = sub_chunk.metadata.get("titre_h2", "")
                h3 = sub_chunk.metadata.get("titre_h3", "")

                # Reconstitution propre de la hiérarchie
                titres_existants = [t for t in [h1, h2, h3] if t and t != source_name]
                chemin_titres = " > ".join(titres_existants) if titres_existants else "Général"

                # En-tête injecté explicitement dans page_content pour BM25 + Vectoriel
                contexte_prefix = f"Document: {source_name}\nSection: {chemin_titres}\n\n"
                contenu_contextualise = f"{contexte_prefix}{sub_chunk.page_content}"

                # Fusion des métadonnées (Metadata d'origine prioritaires !)
                metadata_enrichie = {
                    **metadata_base,
                    "titre_h1": h1,
                    "titre_h2": h2,
                    "titre_h3": h3,
                    "section_path": chemin_titres,
                    "chunk_index": len(chunks_du_doc),
                    "taille_caracteres": len(contenu_contextualise),
                }

                chunks_du_doc.append(
                    Document(
                        page_content=contenu_contextualise,
                        metadata=metadata_enrichie,
                    )
                )

        # Ajout du total de chunks par document
        for chunk in chunks_du_doc:
            chunk.metadata["total_chunks_document"] = len(chunks_du_doc)
            chunks_finaux.append(chunk)

    print(
        f"Découpage terminé : {len(documents)} document(s) -> {len(chunks_finaux)} chunk(s) enrichi(s).",
        flush=True
    )
    return chunks_finaux