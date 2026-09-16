"""Découpage des documents en chunks indexables."""

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from rag_sav.catalogue import libelle_gamme
from rag_sav.config import (
    CHEVAUCHEMENT_CHUNK,
    TAILLE_CHUNK,
    TAILLE_MINIMALE_CONTENU,
)

TITRES_MARKDOWN = [("#", "titre_h1"), ("##", "titre_h2"), ("###", "titre_h3")]


def contenu_utile(texte: str) -> str:
    """Le texte privé de ses lignes de titre markdown et de ses lignes vides."""
    return "\n".join(
        ligne
        for ligne in texte.splitlines()
        if ligne.strip() and not ligne.lstrip().startswith("#")
    ).strip()


def entete_contexte(metadata: dict, section: str) -> str:
    """En-tête injecté dans le texte indexé, donc vu par le plein texte ET par
    l'embedding.

    Mentionner l'appareil rend deux passages par ailleurs identiques (le même
    paragraphe sécurité présent dans les 18 manuels) un peu moins confondables
    pour la recherche vectorielle. Ce n'est PAS ce qui garantit l'exactitude au
    modèle près — c'est le filtre dur de la recherche — mais cela ne coûte rien.
    """
    lignes = [f"Document: {metadata.get('nom_fichier', 'inconnu')}"]

    modele, gamme = metadata.get("modele"), metadata.get("gamme")
    if modele:
        lignes.append(f"Appareil: {libelle_gamme(gamme)} {modele}")
    elif gamme:
        lignes.append(f"Appareil: {libelle_gamme(gamme)} — gamme {gamme}")

    lignes.append(f"Section: {section}")
    return "\n".join(lignes) + "\n\n"


def _chunk_atomique(doc: Document) -> Document:
    """Un document déjà à la bonne maille (une ligne du référentiel).

    Il constitue un chunk à lui seul, quelle que soit sa longueur : le
    tronçonner casserait l'unité « un code erreur = une réponse ».
    """
    section = doc.metadata.get(
        "section_path", f"Code {doc.metadata.get('code_erreur', '')}".strip()
    )
    metadata = {
        **doc.metadata,
        "section_path": section,
        "chunk_index": 0,
        "total_chunks_document": 1,
        "taille_caracteres": len(doc.page_content),
    }
    return Document(
        page_content=entete_contexte(doc.metadata, section) + doc.page_content,
        metadata=metadata,
    )


def decouper_documents(documents: list[Document]) -> list[Document]:
    decoupeur_titres = MarkdownHeaderTextSplitter(
        headers_to_split_on=TITRES_MARKDOWN, strip_headers=False
    )
    decoupeur_taille = RecursiveCharacterTextSplitter(
        chunk_size=TAILLE_CHUNK,
        chunk_overlap=CHEVAUCHEMENT_CHUNK,
        separators=["\n\n", "\n", " ", ""],
    )

    chunks_finaux: list[Document] = []
    ecartes = 0
    print(f"Début du découpage sur {len(documents)} document(s)...", flush=True)

    for doc in documents:
        if not doc.page_content or not doc.page_content.strip():
            continue

        if doc.metadata.get("decoupage") == "atomique":
            chunks_finaux.append(_chunk_atomique(doc))
            continue

        source = doc.metadata.get("nom_fichier", "inconnu")

        # 1. Par titres markdown, pour conserver la hiérarchie des sections.
        try:
            sections = decoupeur_titres.split_text(doc.page_content)
        except Exception:
            sections = []
        if not sections:
            sections = [Document(page_content=doc.page_content, metadata={})]

        chunks_du_doc: list[Document] = []

        for section in sections:
            # 2. Puis par taille, pour rester dans la fenêtre de l'embedding.
            for morceau in decoupeur_taille.split_documents([section]):
                # Un titre de section orphelin ne peut que polluer le classement.
                if len(contenu_utile(morceau.page_content)) < TAILLE_MINIMALE_CONTENU:
                    ecartes += 1
                    continue

                titres = [
                    morceau.metadata.get(cle, "")
                    for cle in ("titre_h1", "titre_h2", "titre_h3")
                ]
                retenus = [t for t in titres if t and t != source]
                chemin = " > ".join(retenus) if retenus else "Général"

                chunks_du_doc.append(
                    Document(
                        page_content=entete_contexte(doc.metadata, chemin)
                        + morceau.page_content,
                        # Les métadonnées d'origine (portée, modèle, gamme)
                        # restent prioritaires sur celles du découpage.
                        metadata={
                            **doc.metadata,
                            "titre_h1": titres[0],
                            "titre_h2": titres[1],
                            "titre_h3": titres[2],
                            "section_path": chemin,
                            "chunk_index": len(chunks_du_doc),
                        },
                    )
                )

        for chunk in chunks_du_doc:
            chunk.metadata["total_chunks_document"] = len(chunks_du_doc)
            chunk.metadata["taille_caracteres"] = len(chunk.page_content)
            chunks_finaux.append(chunk)

    print(
        f"Découpage terminé : {len(documents)} document(s) -> "
        f"{len(chunks_finaux)} chunk(s) ({ecartes} sans contenu utile écarté(s)).",
        flush=True,
    )
    return chunks_finaux
