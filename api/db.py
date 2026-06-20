import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    """Open read only connection with credential in env variables"""
    return psycopg2.connect(
        host=os.getenv("API_DB_HOST","locahost"),
        port=os.getenv("API_DB_PORT","5433"),
        dbname=os.getenv("API_DB_NAME","eudr"),
        user=os.getenv("API_DB_USER","eudr_readonly"),
        password=os.environ["READONLY_DB_PASSWORD"],
        cursor_factory=RealDictCursor,
    )

def fetch_all(query, params=None):
    """Run SELECT and return all row as dictionary, params: a tuple/dict of values, passed separately from query string"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query,params)
            return cur.fetchall()
    finally:
        conn.close()