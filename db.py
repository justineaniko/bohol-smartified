"""Database connection, shared by app.py and auth.py."""
import os

import certifi
import pymysql
from dotenv import load_dotenv

load_dotenv()  # reads secrets from the .env file into os.environ

DB_CONFIG = {
    "host": os.environ.get("DB_HOST"),
    "port": int(os.environ.get("DB_PORT") or 4000),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "database": os.environ.get("DB_NAME", "supplies_tracker"),
    "cursorclass": pymysql.cursors.DictCursor,  # rows come back as dicts
    "ssl": {"ca": certifi.where()},  # TiDB requires an encrypted connection
}


def get_db():
    """Open and return a new database connection. Remember conn.commit() after writes."""
    return pymysql.connect(**DB_CONFIG)
