"""Authenticated encryption for buyer-only order delivery secrets."""
from __future__ import annotations

import base64
import os

PREFIX = 'enc:v1:'


class DeliveryCryptoError(ValueError):
    """The payload cannot safely be encrypted or decrypted."""


def _key() -> bytes:
    encoded = os.environ.get('DELIVERY_ENCRYPTION_KEY', '').strip()
    if not encoded:
        raise DeliveryCryptoError('DELIVERY_ENCRYPTION_KEY is not configured.')
    try:
        key = base64.b64decode(encoded, altchars=b'-_', validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise DeliveryCryptoError('DELIVERY_ENCRYPTION_KEY must be URL-safe base64.') from exc
    if len(key) != 32:
        raise DeliveryCryptoError('DELIVERY_ENCRYPTION_KEY must decode to exactly 32 bytes.')
    return key


def key_is_configured() -> bool:
    try:
        _key()
    except DeliveryCryptoError:
        return False
    return True


def crypto_is_available() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    except ImportError:
        return False
    return True


def is_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt_payload(payload: str, order_item_id: str) -> str:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise DeliveryCryptoError('Install project dependencies before sending protected delivery data.') from exc
    nonce = os.urandom(12)
    aad = ('sentryloot:delivery:v1:' + order_item_id).encode('utf-8')
    ciphertext = AESGCM(_key()).encrypt(nonce, payload.encode('utf-8'), aad)
    return PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode('ascii')


def decrypt_payload(value: str, order_item_id: str) -> str:
    if not is_encrypted(value):
        raise DeliveryCryptoError('Legacy delivery data is not encrypted; run the delivery encryption migration.')
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        raw = base64.b64decode(value[len(PREFIX):], altchars=b'-_', validate=True)
        if len(raw) < 12 + 16:
            raise ValueError('Ciphertext is truncated.')
        nonce, ciphertext = raw[:12], raw[12:]
        aad = ('sentryloot:delivery:v1:' + order_item_id).encode('utf-8')
        plaintext = AESGCM(_key()).decrypt(nonce, ciphertext, aad)
        return plaintext.decode('utf-8')
    except ImportError as exc:
        raise DeliveryCryptoError('Install project dependencies before reading protected delivery data.') from exc
    except Exception as exc:
        raise DeliveryCryptoError('Delivery data failed its integrity check or the encryption key is incorrect.') from exc
