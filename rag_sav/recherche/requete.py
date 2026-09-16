"""La requête SQL hybride : vectoriel + plein texte, sous filtre dur."""

from rag_sav.config import CONSTANTE_RRF, TAILLE_CANDIDATS
from rag_sav.stockage.connexion import curseur


def clause_filtre(analyse: dict) -> tuple[str, dict]:
    """Le filtre dur, appliqué à l'identique aux deux branches.

    Trois niveaux, du plus strict au plus permissif :

      modèle connu  -> le chunk doit couvrir CE modèle (ou être transverse)
      gamme connue  -> le chunk doit relever de CETTE gamme (ou être transverse)
      rien de connu -> aucun filtre (l'escalade a déjà écarté les cas dangereux)

    C'est une EXCLUSION, pas un critère de classement : un classement remonte
    les bons passages mais ne retire jamais les mauvais.

    « portee = global » désigne les documents applicables à tout (les CGV) :
    les exclure priverait de réponse les questions de garantie.
    """
    if analyse["modele"]:
        return (
            "(metadata->'modeles_couverts' @> to_jsonb(%(modele)s::text)"
            " OR metadata->>'portee' = 'global')",
            {"modele": analyse["modele"]},
        )
    if analyse["gamme"]:
        return (
            "(metadata->>'gamme' = %(gamme)s OR metadata->>'portee' = 'global')",
            {"gamme": analyse["gamme"]},
        )
    return ("TRUE", {})


def _construire_sql(filtre: str, plein_texte: bool) -> str:
    # Branche plein texte neutralisée proprement quand il n'y a rien à
    # chercher, au lieu d'envoyer une to_tsquery vide (qui lève une erreur).
    condition = "fts @@ to_tsquery('french', %(fts)s)" if plein_texte else "FALSE"
    classement = (
        "ts_rank_cd(fts, to_tsquery('french', %(fts)s)) DESC" if plein_texte else "id"
    )

    return f"""
        WITH candidats_vecteur AS (
            SELECT id, page_content, metadata, document_source,
                   1 - (embedding <=> %(vecteur)s::vector) AS similarite,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> %(vecteur)s::vector) AS rang_vec
            FROM chunks
            WHERE {filtre}
            ORDER BY embedding <=> %(vecteur)s::vector
            LIMIT %(candidats)s
        ),
        candidats_texte AS (
            SELECT id, page_content, metadata, document_source,
                   ROW_NUMBER() OVER (ORDER BY {classement}) AS rang_fts
            FROM chunks
            WHERE {filtre} AND {condition}
            ORDER BY {classement}
            LIMIT %(candidats)s
        ),
        fusion AS (
            SELECT COALESCE(v.id, t.id)                           AS id,
                   COALESCE(v.page_content, t.page_content)       AS page_content,
                   COALESCE(v.metadata, t.metadata)               AS metadata,
                   COALESCE(v.document_source, t.document_source) AS document_source,
                   v.similarite, v.rang_vec, t.rang_fts,
                   (1.0 / (%(k_rrf)s + COALESCE(v.rang_vec, 9999)))
                 + (1.0 / (%(k_rrf)s + COALESCE(t.rang_fts, 9999))) AS score_rrf
            FROM candidats_vecteur v
            FULL OUTER JOIN candidats_texte t ON v.id = t.id
        )
        SELECT *,
               -- Un bulletin technique prévaut explicitement sur les manuels et
               -- le référentiel pour les points qu'il traite. On ne le remonte
               -- que s'il concerne bien le code demandé, pour éviter qu'un
               -- bulletin hors sujet passe devant.
               (COALESCE((metadata->>'priorite')::int, 0) > 0
                AND %(code)s IS NOT NULL
                AND page_content ILIKE '%%' || %(code)s || '%%') AS prevaut
        FROM fusion
        ORDER BY prevaut DESC, score_rrf DESC
        LIMIT %(limite)s;
    """


def executer(analyse: dict, vecteur: list[float], plein_texte: str | None, limite: int) -> list[dict]:
    filtre, parametres_filtre = clause_filtre(analyse)

    parametres = {
        "vecteur": str(vecteur),
        "fts": plein_texte,
        "code": analyse["code"],
        "limite": limite,
        "candidats": TAILLE_CANDIDATS,
        "k_rrf": CONSTANTE_RRF,
        **parametres_filtre,
    }

    with curseur() as cur:
        cur.execute(_construire_sql(filtre, bool(plein_texte)), parametres)
        return cur.fetchall()
