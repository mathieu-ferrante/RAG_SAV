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

    for doc in documents:
        if not doc.page_content or not doc.page_content.strip():
            continue

        source_name = doc.metadata.get("nom_fichier", "inconnu")

        sections = markdown_splitter.split_text(doc.page_content)
        if not sections:
            sections = [Document(page_content=doc.page_content, metadata={})]

        chunks_du_doc = []
        for section in sections:
            sub_chunks = text_splitter.split_documents([section])

            for sub_chunk in sub_chunks:
                h1 = sub_chunk.metadata.get("titre_h1", "")
                h2 = sub_chunk.metadata.get("titre_h2", "")
                h3 = sub_chunk.metadata.get("titre_h3", "")

                chemin_titres = " > ".join(
                    [t for t in [h1, h2, h3] if t]
                ) or "General"

                metadata_enrichie = {
                    **doc.metadata,
                    **sub_chunk.metadata,
                    "section_path": chemin_titres,
                    "chunk_index": len(chunks_du_doc),
                    "taille_caracteres": len(sub_chunk.page_content),
                }

                contexte_prefix = f"[{source_name} | {chemin_titres}]\n"
                contenu_contextualise = (
                    f"{contexte_prefix}{sub_chunk.page_content}"
                )

                chunks_du_doc.append(
                    Document(
                        page_content=contenu_contextualise,
                        metadata=metadata_enrichie,
                    )
                )

        for chunk in chunks_du_doc:
            chunk.metadata["total_chunks_document"] = len(chunks_du_doc)
            chunks_finaux.append(chunk)

    print(
        f"Decoupage termine : {len(documents)} document(s) -> {len(chunks_finaux)} chunk(s) enrichi(s)."
    )
    return chunks_finaux