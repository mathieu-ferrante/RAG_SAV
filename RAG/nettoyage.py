import re
from langchain_core.documents import Document

def nettoyer_texte(texte: str) -> str:
    """
    Nettoie le texte Markdown en éliminant les caractères parasites et le bruit
    de conversion tout en préservant la structure des tableaux et des titres.
    """
    # 1. Suppression des caractères de contrôle invisibles et des symboles bizarres (zone Unicode 'Private Use Area')
    texte = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", texte)
    texte = re.sub(r"[\uE000-\uF8FF]", "", texte)

    # 2. Normalisation des puces déformées (ex: "-   ", "* •", double tirets)
    texte = re.sub(r"^[ \t]*[-*+•][ \t]+[-*+•][ \t]*", "- ", texte, flags=re.MULTILINE)
    texte = re.sub(r"^[ \t]*[•▪►][ \t]*", "- ", texte, flags=re.MULTILINE)

    # 3. Suppression du bruit de conversion (HTML résiduel et placeholders d'images)
    texte = re.sub(r"<[^>]+>", "", texte)
    texte = re.sub(r"!\[.*?\]\(.*?\)", "", texte)

    # 4. Remplacement des entités HTML (&nbsp;, &amp;, etc.)
    texte = re.sub(r"&nbsp;", " ", texte)
    texte = re.sub(r"&[a-zA-Z]+;", "", texte)

    # 5. Suppression des numéros de page répétitifs (ex: "Page 1 sur 12")
    texte = re.sub(r"(?i)page\s+\d+(\s*(sur|/)\s*\d+)?", "", texte)

    # 6. Suppression des titres Markdown vides (ex: "## " sans texte)
    texte = re.sub(r"^#{1,6}\s*$", "", texte, flags=re.MULTILINE)

    # 7. Nettoyage des espaces superflus ligne par ligne
    lignes_nettoyees = []
    for ligne in texte.split("\n"):
        ligne_traitee = re.sub(r"[ \t]+", " ", ligne.strip())
        lignes_nettoyees.append(ligne_traitee)

    texte = "\n".join(lignes_nettoyees)

    # 8. Unification des sauts de ligne (max 2 consécutifs pour garder la structure des paragraphes)
    texte = re.sub(r"\n{3,}", "\n\n", texte)

    return texte.strip()


def nettoyer_document_langchain(doc: Document) -> Document:
    """
    Applique le nettoyage sur l'objet Document LangChain et retourne le Document à jour.
    """
    doc.page_content = nettoyer_texte(doc.page_content)
    return doc