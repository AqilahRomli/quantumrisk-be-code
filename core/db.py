from psycopg2 import pool
from contextlib import contextmanager
from core.config import settings

# ==============================
# SYNC (psycopg2)
# ==============================
from psycopg2 import pool
from contextlib import contextmanager

rw_pool = pool.SimpleConnectionPool(
    1, 20,
    host=settings.DB_HOST,
    port=settings.DB_PORT_RW,
    user=settings.DB_USER,
    password=settings.DB_PASSWORD,
    database=settings.DB_NAME
)

r_pool = pool.SimpleConnectionPool(
    1, 20,
    host=settings.DB_HOST,
    port=settings.DB_PORT_R,
    user=settings.DB_USER,
    password=settings.DB_PASSWORD,
    database=settings.DB_NAME
)


def get_connection(mode="rw"):
    pool_ref = r_pool if mode == "r" else rw_pool

    for _ in range(2):
        conn = pool_ref.getconn()

        if is_connection_alive(conn):
            return conn

        # ❌ kill bad connection
        try:
            conn.close()
        except:
            pass

    raise Exception("No valid DB connection available")

def release_connection(conn, mode: str = "rw"):
    selected_pool = r_pool if mode == "r" else rw_pool

    if conn.closed != 0:
        # ❌ connection already closed → don't return to pool
        return

    try:
        selected_pool.putconn(conn)
    except:
        try:
            conn.close()
        except:
            pass

# ==============================
# Connection Health Check
# ==============================
def is_connection_alive(conn):
    if conn.closed != 0:
        return False
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except:
        return False

@contextmanager
def get_db(mode="rw"):
    conn = get_connection(mode)
    try:
        yield conn
    except Exception:
        # ❌ connection is unsafe → destroy it
        try:
            conn.close()
        except:
            pass
        raise
    else:
        # ✅ only return healthy connection
        release_connection(conn, mode)


# ==============================
# ASYNC (asyncpg)
# ==============================
import asyncpg
from contextlib import asynccontextmanager

async_rw_pool = None
async_r_pool = None


async def init_async_db():
    global async_rw_pool, async_r_pool

    async_rw_pool = await asyncpg.create_pool(
        host=settings.DB_HOST,
        port=settings.DB_PORT_RW,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        min_size=1,
        max_size=20
    )

    async_r_pool = await asyncpg.create_pool(
        host=settings.DB_HOST,
        port=settings.DB_PORT_R,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        min_size=1,
        max_size=20
    )


@asynccontextmanager
async def get_async_db(mode="rw"):
    pool = async_r_pool if mode == "r" else async_rw_pool
    async with pool.acquire() as conn:
        yield conn