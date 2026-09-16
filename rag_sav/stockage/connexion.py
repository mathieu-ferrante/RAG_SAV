"""Connexions PostgreSQL."""

from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from rag_sav.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER


def ouvrir(base: str | None = None):
    """Connexion brute. `base` permet de viser « postgres » à la création."""
    return psycopg2.connect(
        dbname=base or DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )


@contextmanager
def connexion(base: str | None = None, autocommit: bool = False):
    """Connexion refermée quoi qu'il arrive.

    La version initiale appelait conn.close() en fin de fonction : la moindre
    exception SQL laissait la connexion ouverte.
    """
    conn = ouvrir(base)
    conn.autocommit = autocommit
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def curseur(base: str | None = None, autocommit: bool = False):
    """Curseur renvoyant des dictionnaires, sur une connexion éphémère."""
    with connexion(base, autocommit) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
