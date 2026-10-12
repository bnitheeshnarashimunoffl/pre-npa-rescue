"""Password hashing (task 5.2 seed; JWT and roles arrive in task 5.3).

bcrypt is used directly rather than through passlib, which is unmaintained and warns with
bcrypt >= 4.1. IS/ISO/IEC 27002:2022 control 8.5 (secure authentication).
"""

import bcrypt

DEFAULT_BCRYPT_ROUNDS = 12


def hash_password(password: str, *, rounds: int = DEFAULT_BCRYPT_ROUNDS) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:  # malformed hash
        return False
