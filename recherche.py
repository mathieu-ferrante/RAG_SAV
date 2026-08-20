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
    "fait", "faire", "veux", "dire", "ça", "affiche", "s'affiche"
}

def preparer_requete_fts(question: str) -> str:
    """Détecte s'il y a un code technique (ex: E60, F12) et l'impose obligatoirement.
    Sinon, applique une recherche souple sur les mots utiles.
    """
    # Détection d'un code type lettre + chiffres (ex: E60, E57, F12...)
    codes_techniques = re.findall(r'\b[a-zA-Z]\d+\b', question)
    
    mots = re.findall(r'\b[a-zA-Z0-9à-ÿÀ-Ÿ]+\b', question.lower())
    mots_utiles = [m for m in mots if len(m) > 1 and m not in STOPWORDS_FR]

    # SI UN CODE TECHNIQUE EST DÉTECTÉ (ex: e60) -> Règle stricte AND (&)
    if codes_techniques:
        code_principal = codes_techniques[0].lower()
        print(f"  [Info] Code technique strict détecté : {code_principal.upper()}")
        # Le code est obligatoire, les autres mots utiles sont optionnels pour le contexte
        autres_mots = [m for m in mots_utiles if m != code_principal]
        if autres_mots:
            return f"{code_principal} & ({' | '.join(autres_mots)})"
        else:
            return code_principal

    # Sinon, recherche souple classique
    if not mots_utiles:
        return question
    return " | ".join(mots_utiles)

def tester_recherche_hybride(question: str, top_k: int = 5):
    print(f"\n--- RECHERCHE : « {question} » ---")
    
    vector_requete = embedding_model.encode(question, normalize_embeddings=True).tolist()
    vector_str = str(vector_requete)

    fts_query_str = preparer_requete_fts(question)
    print(f"  [Info] Requête textuelle FTS générée : {fts_query_str}")

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
            LIMIT 20
        ),
        fts_search AS (
            SELECT id, page_content, metadata, document_source,
                   ROW_NUMBER() OVER (ORDER BY ts_rank_cd(fts, to_tsquery('french', %s)) DESC) as rank_fts
            FROM chunks
            WHERE fts @@ to_tsquery('french', %s)
            ORDER BY ts_rank_cd(fts, to_tsquery('french', %s)) DESC
            LIMIT 20
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
        SELECT * FROM combined
        ORDER BY rrf_score DESC
        LIMIT %s;
        """
        
        cur.execute(query, (vector_str, vector_str, fts_query_str, fts_query_str, fts_query_str, top_k))
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
        
        print(f"[{idx}] Confiance : {confiance:.1f}% (Score RRF: {score_brut:.5f})")
        print(f"    Source  : {source} | Section : {section}")
        print(f"    Rang Vecto : {res['rank_vec']} | Rang Mots-clés : {res['rank_fts']}")
        print(f"    Extrait : {res['page_content'][:150]}...")
        print("-" * 60)


if __name__ == "__main__":
    tester_recherche_hybride("Quelles sont les exigences pour la niche d'encastrement ?")