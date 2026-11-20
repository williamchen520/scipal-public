import tempfile
import unittest
from pathlib import Path

from scripts.code_git_sync import backup_shards, restore_shards


class GitSyncTest(unittest.TestCase):
    def test_backup_and_restore_shards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_dir = root / "index"
            index_dir.mkdir()
            (index_dir / "scanpy-1_v16.00000.zoekt").write_bytes(b"old")
            (index_dir / "other_v16.00000.zoekt").write_bytes(b"keep")
            backup = backup_shards(index_dir, "scanpy-1", "token")
            self.assertTrue((backup / "scanpy-1_v16.00000.zoekt").exists())
            (index_dir / "scanpy-1_v16.00000.zoekt").write_bytes(b"new")
            restore_shards(index_dir, "scanpy-1", backup)
            self.assertEqual((index_dir / "scanpy-1_v16.00000.zoekt").read_bytes(), b"old")
            self.assertEqual((index_dir / "other_v16.00000.zoekt").read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
