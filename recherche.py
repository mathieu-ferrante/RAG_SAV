import os
import re
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "rag_db")

print("Chargement du modèle d'embedding pour la requête...")
embedding_model = SentenceTransformer("BAAI/bge-m3")

STOPWORDS_FR = {
    "le", "la", "les", "un", "une", "des", "et", "ou", "de", "du", "à", "en", 
    "que", "qui", "quoi", "dont", "où", "ce", "cette", "ces", "je", "tu", "il", 
    "elle", "nous", "vous", "ils", "elles", "mon", "ton", "son", "sa", "ses", 
    "ma", "ta", "mes", "tes", "nos", "vos", "leurs", "aux", "par", "pour", 
    "sur", "sous", "dans", "avec", "sans", "est", "sont", "ont", "suis", "es", 
    "fait", "faire", "veux", "dire", "ça", "affiche", "s'affiche", "comment",
    "fais", "sortir", "men", "stp", "perdu", "merde", "chui"
}


def extraire_entites(question: str):
    """Extrait les codes erreurs et les modèles de la question."""
    # Détection code erreur : 1 lettre + 2 à 3 chiffres (ex: E60, E42, F12)
    codes_erreur = re.findall(r'(?i)\be\d{2}\b', question)
    
    # Détection modèle : 2 lettres + tirat + 3 chiffres (ex: FR-750, WX-400)
    modeles = re.findall(r'\b[a-zA-Z]{2}-\d{3,4}\b', question, re.IGNORECASE)
    
    code_exact = codes_erreur[0].upper() if codes_erreur else None
    modele_exact = modeles[0].upper() if modeles else None
    
    return code_exact, modele_exact


def preparer_requete_fts(question: str, code_exact: str | None, modele_exact: str | None) -> str:
    # Si un code erreur est présent, on filtre FTS UNIQUEMENT sur ce code
    if code_exact:
        if modele_exact:
            return f"{code_exact.lower()} & {modele_exact.lower()}"
        return code_exact.lower()

    # Sinon, traitement normal des mots-clés
    mots_bruts = re.findall(r'\b[a-zA-Z0-9à-ÿÀ-Ÿ]+\b', question.lower())
    mots_propres = [
        m for m in mots_bruts 
        if m not in STOPWORDS_FR and len(m) > 1 and not re.search(r'(.)\1{3,}', m)
    ]

    elements = []
    if modele_exact:
        elements.append(modele_exact.lower())
    elements.extend(mots_propres)

    return " | ".join(elements) if elements else question


def tester_recherche_hybride(question: str, top_k: int = 5):
    print(f"\n--- RECHERCHE : « {question} » ---")
    
    code_exact, modele_exact = extraire_entites(question)
    print(f"  [Info] Entités détectées -> Code Erreur: {code_exact} | Modèle: {modele_exact}")

    vector_requete = embedding_model.encode(question, normalize_embeddings=True).tolist()
    vector_str = str(vector_requete)

    fts_query_str = preparer_requete_fts(question, code_exact, modele_exact)

    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    )
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        query = """
        WITH vector_search AS (
            SELECT id, page_content, metadata, document_source,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) as rank_vec
            FROM chunks
            ORDER BY embedding <=> %s::vector
            LIMIT 30
        ),
        fts_search AS (
            SELECT id, page_content, metadata, document_source,
                ROW_NUMBER() OVER (
                    ORDER BY 
                   -- Priorité 1 : Le chunk contient VRAIMENT la chaîne exacte E51 entourée de limites de mots
                   CASE WHEN %s IS NOT NULL AND page_content ~* ('\\y' || %s || '\\y') THEN 0 ELSE 1 END,
                   -- Priorité 2 : Densité textuelle BM25 classique
                   ts_rank_cd(fts, to_tsquery('french', %s)) DESC
                ) as rank_fts
            FROM chunks
            WHERE fts @@ to_tsquery('french', %s)
            ORDER BY 
                CASE WHEN %s IS NOT NULL AND page_content ~* ('\\y' || %s || '\\y') THEN 0 ELSE 1 END,
                ts_rank_cd(fts, to_tsquery('french', %s)) DESC
            LIMIT 30
        ),
        combined AS (
            SELECT 
                COALESCE(v.id, f.id) as id,
                COALESCE(v.page_content, f.page_content) as page_content,
                COALESCE(v.metadata, f.metadata) as metadata,
                COALESCE(v.document_source, f.document_source) as document_source,
                COALESCE(v.rank_vec, 999) as rank_vec,
                COALESCE(f.rank_fts, 999) as rank_fts,
                (1.0 / (60.0 + COALESCE(v.rank_vec, 999))) + (1.0 / (60.0 + COALESCE(f.rank_fts, 999))) as rrf_score
            FROM vector_search v
            FULL OUTER JOIN fts_search f ON v.id = f.id
        )
        SELECT *,
            CASE WHEN %s IS NOT NULL AND page_content ~* ('\\y' || %s || '\\y') THEN 1 ELSE 0 END as boost_code,
            CASE WHEN %s IS NOT NULL AND (document_source ~* %s OR page_content ~* %s) THEN 1 ELSE 0 END as boost_modele
        FROM combined
        ORDER BY 
            boost_code DESC,
            boost_modele DESC,
            rrf_score DESC
        LIMIT %s;
        """
        
        # Passage exact des 16 paramètres attendus par la requête SQL
        cur.execute(query, (
            # vector_search (2)
            vector_str, vector_str,
            # fts_search ORDER BY 1 (2: code_exact, code_exact)
            code_exact, code_exact,
            # fts_search ORDER BY 2 (1: fts_query_str)
            fts_query_str,
            # fts_search WHERE (1: fts_query_str)
            fts_query_str,
            # fts_search final ORDER BY (3: code_exact, code_exact, fts_query_str)
            code_exact, code_exact, fts_query_str,
            # SELECT boost_code (2: code_exact, code_exact)
            code_exact, code_exact,
            # SELECT boost_modele (3: modele_exact, modele_exact, modele_exact)
            modele_exact, modele_exact, modele_exact,
            # LIMIT (1)
            top_k
        ))
        resultats = cur.fetchall()

    conn.close()

    if not resultats:
        print("Aucun résultat trouvé.")
        return

    score_rrf_max = (1.0 / 61.0) + (1.0 / 61.0)

    print(f"\nTop {len(resultats)} résultats trouvés :\n")
    for idx, res in enumerate(resultats, start=1):
        score_brut = float(res["rrf_score"])
        confiance = min(100.0, (score_brut / score_rrf_max) * 100.0)
        
        source = res["metadata"].get("nom_fichier", "Inconnu")
        section = res["metadata"].get("section_path", "Général")
        
        print(f"[{idx}] Confiance : {confiance:.1f}% (CodeBoost: {res['boost_code']} | ModeleBoost: {res['boost_modele']})")
        print(f"    Source  : {source} | Section : {section}")
        print(f"    Rang Vecto : {res['rank_vec']} | Rang Mots-clés : {res['rank_fts']}")
        print(f"    Extrait : {res['page_content'][:150]}...")
        print("-" * 60)

if __name__ == "__main__":
    tester_recherche_hybride("J'ai un Lave-vaisselle LV-200 qui affiche le code erreur E40 Que doije faire je suis perdu a laide svp tout va bruler si il y a un probleme sinon je vais pas réussir et je vais tout perdre ?")