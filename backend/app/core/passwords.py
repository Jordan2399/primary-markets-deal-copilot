"""Password hashing with scrypt from the standard library (no extra dependency).

Stored format:  scrypt$N$r$p$<salt, base64>$<hash, base64>
The parameters are stored with the hash, so they can be raised later without breaking old hashes.
"""

import base64
import hashlib
import hmac
import secrets

# scrypt cost settings: N = CPU/memory cost (2**14 is the common interactive-login default),
# r = block size, p = parallelism. Higher N makes each guess slower for an attacker.
_N, _R, _P = 2**14, 8, 1
_KEY_LEN = 32  # length of the derived key in bytes


def _b64(data: bytes) -> str:
    """Encode bytes as text so salt and hash can be stored in one string."""
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    """Return a salted scrypt hash string for storing; the plain password is never stored."""
    # A fresh random salt per password means equal passwords get different hashes.
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_KEY_LEN)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """True when the password matches. Never raises on malformed input; returns False."""
    try:
        # Split the stored string back into its parts (wrong shape raises ValueError below).
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        # Recompute the hash with the stored salt and the stored cost settings.
        actual = hashlib.scrypt(
            password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    # compare_digest takes the same time however many bytes match, so timing leaks nothing.
    return hmac.compare_digest(actual, expected)


# A hash of a random password, computed once. Checking a login for an unknown user against it
# keeps the response time the same, so the API does not reveal which usernames exist.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
