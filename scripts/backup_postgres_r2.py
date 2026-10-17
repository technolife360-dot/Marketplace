#!/usr/bin/env python3
"""Encrypt pg_dump archives client-side and store them in private Cloudflare R2.

Requires a 32-byte base64 BACKUP_ENCRYPTION_KEY_B64 kept outside the repository.
The archive is authenticated with AES-256-GCM before upload; the key must be
backed up separately because neither GitHub nor R2 can recover it.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import secrets
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAGIC = b'SENTRYLOOT-PG-BACKUP-1\n'
PREFIX = 'db-backups/v1/'
CHUNK = 1024 * 1024


def encryption_key() -> bytes:
    try:
        key = base64.b64decode(os.environ['BACKUP_ENCRYPTION_KEY_B64'], validate=True)
    except (KeyError, ValueError) as exc:
        raise RuntimeError('A valid backup encryption key is required') from exc
    if len(key) != 32:
        raise RuntimeError('The backup encryption key must be 32 bytes')
    return key


def r2_client():
    import boto3
    from botocore.config import Config

    account = os.environ.get('R2_ACCOUNT_ID', '').strip()
    access = os.environ.get('R2_ACCESS_KEY_ID', '').strip()
    secret = os.environ.get('R2_SECRET_ACCESS_KEY', '').strip()
    bucket = os.environ.get('R2_EVIDENCE_BUCKET', '').strip()
    if not (account and access and secret and bucket):
        raise RuntimeError('Private R2 bucket credentials are required')
    client = boto3.client(
        's3', endpoint_url=f'https://{account}.r2.cloudflarestorage.com',
        aws_access_key_id=access, aws_secret_access_key=secret,
        region_name='auto', config=Config(signature_version='s3v4'),
    )
    return client, bucket


def seal(source: Path, target: Path, key: bytes) -> None:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    nonce = secrets.token_bytes(12)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    with source.open('rb') as src, target.open('wb') as out:
        out.write(MAGIC + nonce)
        while block := src.read(CHUNK):
            out.write(encryptor.update(block))
        out.write(encryptor.finalize())
        out.write(encryptor.tag)


def open_sealed(source: Path, target: Path, key: bytes) -> None:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    size = source.stat().st_size
    minimum = len(MAGIC) + 12 + 16
    if size < minimum:
        raise RuntimeError('Backup archive is truncated')
    with source.open('rb') as src:
        if src.read(len(MAGIC)) != MAGIC:
            raise RuntimeError('Backup archive format is invalid')
        nonce = src.read(12)
        src.seek(-16, os.SEEK_END)
        tag = src.read(16)
        src.seek(len(MAGIC) + 12)
        remaining = size - minimum
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        try:
            with target.open('wb') as out:
                while remaining:
                    block = src.read(min(CHUNK, remaining))
                    if not block:
                        raise RuntimeError('Backup archive is truncated')
                    out.write(decryptor.update(block))
                    remaining -= len(block)
                out.write(decryptor.finalize())
        except Exception:
            target.unlink(missing_ok=True)
            raise


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(CHUNK):
            result.update(block)
    return result.hexdigest()


def backup(source: Path, github_output: str | None) -> None:
    if not source.is_file() or not source.stat().st_size:
        raise RuntimeError('A non-empty pg_dump archive is required')
    key = encryption_key()
    client, bucket = r2_client()
    now = datetime.now(timezone.utc)
    object_key = f'{PREFIX}{now:%Y/%m/%d}/{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(8)}.dump.gcm'
    with tempfile.TemporaryDirectory(prefix='sentryloot-backup-') as directory:
        encrypted = Path(directory) / 'backup.dump.gcm'
        seal(source, encrypted, key)
        checksum = digest(encrypted)
        client.upload_file(str(encrypted), bucket, object_key, ExtraArgs={
            'ContentType': 'application/octet-stream',
            'Metadata': {'sha256': checksum, 'format': 'sentryloot-pg-backup-1'},
        })
        head = client.head_object(Bucket=bucket, Key=object_key)
        if head.get('ContentLength') != encrypted.stat().st_size or head.get('Metadata', {}).get('sha256') != checksum:
            raise RuntimeError('R2 backup upload verification failed')
    if github_output:
        with open(github_output, 'a', encoding='utf-8') as output:
            output.write(f'backup_key={object_key}\n')
    print(f'Encrypted backup uploaded and verified: {object_key}')


def restore_check(object_key: str, output: Path) -> None:
    if not object_key.startswith(PREFIX) or not object_key.endswith('.dump.gcm') or '..' in object_key:
        raise RuntimeError('Invalid backup object key')
    key = encryption_key()
    client, bucket = r2_client()
    with tempfile.TemporaryDirectory(prefix='sentryloot-restore-') as directory:
        encrypted = Path(directory) / 'backup.dump.gcm'
        client.download_file(bucket, object_key, str(encrypted))
        head = client.head_object(Bucket=bucket, Key=object_key)
        if head.get('ContentLength') != encrypted.stat().st_size or head.get('Metadata', {}).get('sha256') != digest(encrypted):
            raise RuntimeError('Downloaded backup checksum did not match R2 metadata')
        open_sealed(encrypted, output, key)
    print('R2 archive downloaded and authenticated.')


def prune(days: int) -> None:
    if days < 30:
        raise RuntimeError('Retention must be at least 30 days')
    client, bucket = r2_client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    for page in client.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=PREFIX):
        for item in page.get('Contents', []):
            object_key = item['Key']
            if object_key.endswith('.dump.gcm') and item['LastModified'] < cutoff:
                client.delete_object(Bucket=bucket, Key=object_key)
                removed += 1
    print(f'Expired encrypted backups removed: {removed}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('backup')
    create.add_argument('--input', required=True, type=Path)
    create.add_argument('--github-output')
    restore = sub.add_parser('restore-check')
    restore.add_argument('--key', required=True)
    restore.add_argument('--output', required=True, type=Path)
    cleanup = sub.add_parser('prune')
    cleanup.add_argument('--days', type=int, default=35)
    args = parser.parse_args()
    try:
        if args.command == 'backup':
            backup(args.input, args.github_output)
        elif args.command == 'restore-check':
            restore_check(args.key, args.output)
        else:
            prune(args.days)
    except Exception as exc:
        # Provider exceptions may contain connection strings or hostnames.
        print(f'Backup operation failed: {type(exc).__name__}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
