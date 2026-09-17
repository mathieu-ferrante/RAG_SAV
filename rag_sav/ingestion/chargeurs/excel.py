"""Chargeur Excel — le référentiel des codes erreur.

Produit un document AUTONOME par ligne, donc par code erreur : il porte son
code, sa signification, sa gamme, ses modèles et les deux conduites à tenir.
Il peut ainsi être cité seul.

Avant, le tableau était converti en markdown puis tronçonné tous les 500
caractères, ce qui produisait des chunks du type « |:------|:------| » et des
lignes privées de leurs en-têtes de colonnes.
"""

from pathlib import Path

import pandas as pd
from langchain_core.documents import Document

from rag_sav.catalogue import (
    detecter_gamme_isolee,
    extraire_modeles,
    libelle_gamme,
    modeles_de_la_gamme,
    normaliser_code_erreur,
)
from rag_sav.ingestion.portee import metadonnees_communes, portee_referentiel


def _ligne_des_entetes(df: pd.DataFrame) -> int | None:
    """Localise la vraie ligne d'en-têtes.

    Le fichier Electrodomus place un titre en ligne 1 et la version en ligne 2 ;
    les noms de colonnes ne commencent qu'en ligne 3. Lu avec les options par
    défaut, pandas prend donc le TITRE pour un nom de colonne et fabrique
    « Unnamed: 1 », « Unnamed: 2 »… qui se retrouvaient dans le texte indexé.
    """
    for index, ligne in df.iterrows():
        if "code" in [str(v).strip().lower() for v in ligne.tolist()]:
            return index
    return None


def _cellule(ligne: pd.Series, colonnes: dict, intitule: str) -> str:
    """Lit une colonne par son intitulé, en tolérant son absence."""
    position = colonnes.get(intitule)
    if position is None:
        return ""
    valeur = ligne.iloc[position]
    return "" if pd.isna(valeur) else str(valeur).strip()


def _document_code_erreur(
    chemin: Path, categorie: str, nom_onglet: str, index_onglet: int,
    titre: str, version: str, code_gamme: str | None,
    ligne: pd.Series, colonnes: dict,
) -> Document | None:
    code = normaliser_code_erreur(_cellule(ligne, colonnes, "Code"))
    if not code:
        return None  # ligne vide, séparateur, sous-total…

    signification = _cellule(ligne, colonnes, "Signification")
    conduite = _cellule(ligne, colonnes, "Conduite à tenir (client)")
    intervention = _cellule(ligne, colonnes, "Intervention SAV (technicien)")

    # Priorité à la colonne « Modèles concernés » du fichier source : c'est la
    # donnée métier de référence. Le catalogue ne sert que de secours.
    modeles = extraire_modeles(
        _cellule(ligne, colonnes, "Modèles concernés")
    ) or modeles_de_la_gamme(code_gamme)

    lignes = [
        f"# {titre}",
        f"## Code {code} — {signification}" if signification else f"## Code {code}",
        f"- **Gamme :** {code_gamme} ({libelle_gamme(code_gamme)})" if code_gamme else "",
        f"- **Modèles concernés :** {', '.join(modeles)}" if modeles else "",
        f"- **Signification :** {signification}" if signification else "",
        f"- **Conduite à tenir (client) :** {conduite}" if conduite else "",
        f"- **Intervention SAV (technicien) :** {intervention}" if intervention else "",
        f"*{version}*" if version else "",
    ]

    metadata = metadonnees_communes(chemin, categorie)
    metadata.update({
        "type_document": "excel",
        "onglet": nom_onglet,
        "onglet_index": index_onglet,
        "code_erreur": code,
        "signification": signification,
        "version_referentiel": version,
        # R3b : sans gamme mais avec des modèles, la ligne est contrainte au
        # modèle — pas « global », qui passerait tous les filtres.
        "portee": portee_referentiel(code_gamme, modeles),
        "gamme": code_gamme,
        "modele": None,
        "modeles_couverts": modeles,
        # Déjà à la bonne maille : le découpeur ne doit pas le tronçonner.
        "decoupage": "atomique",
    })

    return Document(
        page_content="\n".join(l for l in lignes if l),
        metadata=metadata,
    )


def charger(chemin: Path, categorie: str) -> list[Document]:
    documents: list[Document] = []

    for index_onglet, (nom_onglet, df) in enumerate(
        pd.read_excel(chemin, sheet_name=None, header=None).items(), start=1
    ):
        entetes = _ligne_des_entetes(df)
        if entetes is None:
            documents.append(_onglet_brut(chemin, categorie, nom_onglet, index_onglet, df))
            continue

        titre = str(df.iloc[0, 0]).strip() if not pd.isna(df.iloc[0, 0]) else nom_onglet

        version = ""
        for position in range(1, entetes):
            cellule = df.iloc[position, 0]
            if not pd.isna(cellule) and "version" in str(cellule).lower():
                version = str(cellule).strip()
                break

        colonnes = {
            str(valeur).strip(): position
            for position, valeur in enumerate(df.iloc[entetes].tolist())
            if not pd.isna(valeur) and str(valeur).strip()
        }

        # La gamme se lit dans le nom de l'onglet (« Gamme WX »), le titre du
        # tableau servant de secours.
        code_gamme = detecter_gamme_isolee(f"{nom_onglet} {titre}")

        for position in range(entetes + 1, len(df)):
            document = _document_code_erreur(
                chemin, categorie, nom_onglet, index_onglet,
                titre, version, code_gamme, df.iloc[position], colonnes,
            )
            if document:
                documents.append(document)

    return documents


def _onglet_brut(
    chemin: Path, categorie: str, nom_onglet: str, index_onglet: int, df: pd.DataFrame
) -> Document:
    """Secours : onglet dont la structure n'a pas été reconnue.

    Le contenu part indexé tel quel, mais surtout PAS en « global » : un onglet
    non reconnu deviendrait un gros bloc visible depuis toutes les gammes. Le
    nom de l'onglet (« Gamme WX ») suffit presque toujours à le contraindre.
    """
    contenu = (
        f"# {chemin.stem}\n## Onglet: {nom_onglet}\n\n"
        f"{df.fillna('').to_markdown(index=False)}"
    )
    metadata = metadonnees_communes(chemin, categorie, contenu)

    code_gamme = detecter_gamme_isolee(nom_onglet)
    if code_gamme:
        metadata.update({
            "portee": "gamme",
            "gamme": code_gamme,
            "modele": None,
            "modeles_couverts": modeles_de_la_gamme(code_gamme),
        })

    metadata.update({
        "type_document": "excel",
        "onglet": nom_onglet,
        "onglet_index": index_onglet,
    })
    return Document(page_content=contenu, metadata=metadata)
