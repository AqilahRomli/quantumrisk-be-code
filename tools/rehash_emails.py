"""Make every stored email_hash ignore upper / lower case.

New users already get the hash of the lower-case email (services/getUserAuth.py,
hash_email). This updates the users registered before that. Login also updates
a user's hash when it finds the old one, so running this is about duplicate
checks at registration: without it, "Abu@tm.com.my" registered before could be
registered again as "abu@tm.com.my".

Run once per environment after deploying, from quantumrisk-backend/:
    $env:APP_ENV = 'dev'
    python -m tools.rehash_emails            # dry run: only shows what would change
    python -m tools.rehash_emails --apply    # writes the changes

Users whose emails differ only in upper / lower case are listed and left as they
are: they would share one login, so decide by hand which account to keep first.
"""
import sys
from collections import defaultdict

from psycopg2.extras import RealDictCursor
from cryptography.fernet import InvalidToken

from core.db import get_db
from core.security import decrypt
from services.getUserAuth import hash_email


def main(apply: bool):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute("SELECT id, username, email, email_hash FROM risk_user_table ORDER BY id")
            users = cursor.fetchall()

            by_hash = defaultdict(list)
            unreadable = []
            for user in users:
                try:
                    email = decrypt(user["email"]) if user["email"] else ""
                except InvalidToken:
                    email = user["email"]  # stored without encryption
                if not email:
                    unreadable.append(user)
                    continue
                by_hash[hash_email(email)].append((user, email))

            changes, clashes = [], []
            for new_hash, same in by_hash.items():
                if len(same) > 1:
                    clashes.append(same)
                    continue
                user, email = same[0]
                if user["email_hash"] != new_hash:
                    changes.append((user, email, new_hash))

            print(f"{len(users)} user(s), {len(changes)} hash(es) to update")
            for user, email, _ in changes:
                print(f"  update  id={user['id']}  {user['username']}  {email}")
            for same in clashes:
                print("  SKIPPED (same email in different case, fix by hand): "
                      + ", ".join(f"id={u['id']} {u['username']} {e}" for u, e in same))
            for user in unreadable:
                print(f"  SKIPPED (no email): id={user['id']} {user['username']}")

            if not apply:
                print("Dry run: nothing written. Run with --apply to update.")
                conn.rollback()
                return

            for user, _, new_hash in changes:
                cursor.execute("UPDATE risk_user_table SET email_hash = %s WHERE id = %s", (new_hash, user["id"]))
            conn.commit()
            print(f"Updated {len(changes)} user(s).")
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv[1:])
