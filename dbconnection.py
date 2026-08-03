import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from passlib.context import CryptContext
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta
import secrets

from fastapi import HTTPException

# Load environment variables
from dotenv import load_dotenv
import os

# Load environment variables
# Get environment (if not set, default to using .env)
APP_ENV = os.getenv("APP_ENV")

if APP_ENV:
    env_path = f"env/.env.{APP_ENV}"
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv("env/.env")  # Default to .env in root


db_pool_rw = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT_RW"),
    database=os.getenv("DB_NAME")
)

db_pool_read = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT_R"),
    database=os.getenv("DB_NAME")
)

# Function to connect to the database
# def connect_to_db_rw():
#     try:
#         conn = psycopg2.connect(
#             host = os.getenv("DB_HOST"),
#             user = os.getenv("DB_USER"),
#             password = os.getenv("DB_PASSWORD"),
#             database = os.getenv("DB_NAME"),
#             port = os.getenv("DB_PORT_RW")
#         )
#         return conn
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")
    
#     # Function to connect to the database
# def connect_to_db_read():
#     try:
#         conn = psycopg2.connect(
#             host = os.getenv("DB_HOST"),
#             user = os.getenv("DB_USER"),
#             password = os.getenv("DB_PASSWORD"),
#             database = os.getenv("DB_NAME"),
#             port = os.getenv("DB_PORT_R")
#         )
#         return conn
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

def get_connection(type: str):
    if (type == "rw"):
        #print("in read write mode")
        try:
            return db_pool_rw.getconn()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DB pool error: {str(e)}")
        
    if (type == "read"):
        #print("in read mode")
        try:
            return db_pool_read.getconn()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DB pool error: {str(e)}")

def release_connection(conn, type: str):
    if (type == "rw"):
        #print("in read write mode")
        try:
            db_pool_rw.putconn(conn)
        except Exception:
            conn.close()  # fallback if pool closed

    if (type == "read"):
        #print("in read mode")
        try:
            db_pool_read.putconn(conn)
        except Exception:
            conn.close()  # fallback if pool closed
