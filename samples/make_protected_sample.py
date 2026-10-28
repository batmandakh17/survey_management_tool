"""Write a passphrase-protected copy of the E07 sample assignment (decision D11), for trying and testing.

Run from the tool folder:  python3 samples/make_protected_sample.py
Needs the Python package `cryptography`. The passphrase of this SYNTHETIC sample is: synthetic-E07
The envelope is the one src/core.js writes and reads (rtm-sealed-1.0): PBKDF2-SHA-256 (600,000 iterations,
16-byte salt) derives an AES-256-GCM key; the header is bound to the ciphertext as additional data.
"""
import base64
import json
import os
import sys
import unicodedata

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_samples import canon, clean  # noqa: E402

ITER = 600000


def key_of(passphrase, salt, iterations=ITER):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(unicodedata.normalize("NFC", passphrase).encode("utf-8"))


def header(env):
    return clean({k: env.get(k) for k in ("schema", "contains", "program", "round", "enumerator_id")})


def seal(obj, passphrase, head, iterations=ITER):
    salt, iv = os.urandom(16), os.urandom(12)
    env = clean(dict({"schema": "rtm-sealed-1.0"}, **head))
    ct = AESGCM(key_of(passphrase, salt, iterations)).encrypt(iv, json.dumps(obj, ensure_ascii=False).encode("utf-8"), canon(header(env)).encode("utf-8"))
    env.update({"note": "Protected file. Open it in the RTM interview tool with the passphrase your leader gave you.",
                "kdf": {"name": "PBKDF2", "hash": "SHA-256", "iterations": iterations, "salt": base64.b64encode(salt).decode()},
                "cipher": {"name": "AES-GCM", "iv": base64.b64encode(iv).decode(), "tag_bits": 128},
                "data": base64.b64encode(ct).decode()})
    return env


def unseal(env, passphrase):
    kd, ci = env["kdf"], env["cipher"]
    key = key_of(passphrase, base64.b64decode(kd["salt"]), kd["iterations"])
    pt = AESGCM(key).decrypt(base64.b64decode(ci["iv"]), base64.b64decode(env["data"]), canon(header(env)).encode("utf-8"))
    return json.loads(pt.decode("utf-8"))


if __name__ == "__main__":
    src = os.path.join(HERE, "round05", "E07_assignment_R05.json")
    A = json.load(open(src, encoding="utf-8"))
    env = seal(A, "synthetic-E07", {"contains": "rtm-assign-1.0", "program": A["program"], "round": A["round"], "enumerator_id": A["enumerator_id"]})
    assert unseal(env, "synthetic-E07") == A
    out = os.path.join(HERE, "round05", "E07_assignment_R05_protected.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(env, f, ensure_ascii=False, indent=1)
    print("written", out)
