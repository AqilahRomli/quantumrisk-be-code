"""Set a user's password, for username + password login on a local machine.

Users normally sign in with Entra ID and have a random password nobody knows.
To try password login locally, give one user a password you choose:

    python -m tools.set_password <username>

It asks for the new password twice (not shown while typing). Run it from
quantumrisk-backend/ with the LOCAL env file (APP_ENV not set): it refuses to
run unless PASSWORD_LOGIN_ENABLED=true, which is only set in env/.env.
"""
import getpass
import sys

from passlib.context import CryptContext
from psycopg2.extras import RealDictCursor

from core.config import settings
from core.db import get_db

# Same hashing as login (pwd_context in services/getUserAuth.py). Not imported
# from there, so this tool needs only the database packages.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

MIN_LENGTH = 8


def main(username: str):
    if not settings.PASSWORD_LOGIN_ENABLED:
        sys.exit("Refused: password login is not enabled for this environment "
                 "(PASSWORD_LOGIN_ENABLED). This tool is for a local machine only.")

    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute("SELECT id, username, is_active FROM risk_user_table WHERE username = %s", (username,))
            user = cursor.fetchone()
            if not user:
                sys.exit(f"User '{username}' not found.")
            if not user["is_active"]:
                print(f"Note: '{username}' is inactive, so login will still be refused until reactivated.")

            password = getpass.getpass("New password: ")
            if len(password) < MIN_LENGTH:
                sys.exit(f"Refused: the password must be at least {MIN_LENGTH} characters.")
            if getpass.getpass("Type it again: ") != password:
                sys.exit("Refused: the two passwords are different.")

            cursor.execute("UPDATE risk_user_table SET password = %s WHERE id = %s",
                           (pwd_context.hash(password), user["id"]))
            conn.commit()
            print(f"Password set for '{username}'. You can now log in with it on this machine.")
        except BaseException:
            conn.rollback()
            raise
        finally:
            cursor.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m tools.set_password <username>")
    main(sys.argv[1])
