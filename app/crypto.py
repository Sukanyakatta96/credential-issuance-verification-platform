import base64
import hashlib
import hmac
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_hash(payload_json: str) -> str:
    return sha256_hex(payload_json)


def derive_private_key(master_secret: str, key_id: str) -> Ed25519PrivateKey:
    seed = hmac.new(master_secret.encode("utf-8"), f"issuer-key|{key_id}".encode("utf-8"), hashlib.sha256).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key_b64(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


def derive_public_key_b64(master_secret: str, key_id: str) -> str:
    return public_key_b64(derive_private_key(master_secret, key_id))


def sign_hash(master_secret: str, key_id: str, hash_hex: str) -> str:
    key = derive_private_key(master_secret, key_id)
    return base64.b64encode(key.sign(hash_hex.encode("ascii"))).decode("ascii")


def verify_signature(public_key_b64_value: str, hash_hex: str, signature_b64: str) -> bool:
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64_value))
        public_key.verify(base64.b64decode(signature_b64), hash_hex.encode("ascii"))
        return True
    except (InvalidSignature, ValueError):
        return False


class SignerCache:
    """Caches derived private keys so bulk signing does not re-derive per credential."""

    def __init__(self, master_secret: str):
        self.master_secret = master_secret
        self._keys: dict[str, Ed25519PrivateKey] = {}

    def private_key(self, key_id: str) -> Ed25519PrivateKey:
        if key_id not in self._keys:
            self._keys[key_id] = derive_private_key(self.master_secret, key_id)
        return self._keys[key_id]

    def public_key_b64(self, key_id: str) -> str:
        return public_key_b64(self.private_key(key_id))

    def sign(self, key_id: str, hash_hex: str) -> str:
        return base64.b64encode(self.private_key(key_id).sign(hash_hex.encode("ascii"))).decode("ascii")
