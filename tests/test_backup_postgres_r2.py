import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import backup_postgres_r2 as backup


class EncryptedBackupTests(unittest.TestCase):
    def test_archive_round_trip_and_tamper_detection(self):
        key = os.urandom(32)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.dump'
            encrypted = Path(directory) / 'backup.dump.gcm'
            restored = Path(directory) / 'restored.dump'
            source.write_bytes(os.urandom(2_500_000))
            backup.seal(source, encrypted, key)
            self.assertNotIn(source.read_bytes()[:64], encrypted.read_bytes())
            backup.open_sealed(encrypted, restored, key)
            self.assertEqual(source.read_bytes(), restored.read_bytes())

            damaged = bytearray(encrypted.read_bytes())
            damaged[len(backup.MAGIC) + 20] ^= 1
            encrypted.write_bytes(damaged)
            restored.unlink()
            with self.assertRaises(Exception):
                backup.open_sealed(encrypted, restored, key)
            self.assertFalse(restored.exists())

    def test_key_must_be_exactly_32_bytes(self):
        with patch.dict(os.environ, {'BACKUP_ENCRYPTION_KEY_B64': base64.b64encode(b'short').decode()}):
            with self.assertRaises(RuntimeError):
                backup.encryption_key()


if __name__ == '__main__':
    unittest.main()
