import json
import py_compile
import tempfile
import unittest
from pathlib import Path

from docker import materialize


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class MaterializeTests(unittest.TestCase):
    def test_locked_archive_materializes_and_compiles(self):
        lock_path = REPOSITORY_ROOT / "docker" / "upstream.lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        archive = REPOSITORY_ROOT / lock["archive"]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "app"
            materialize.materialize(archive, lock_path, output)
            main_path = output / "backend" / "main.py"
            py_compile.compile(main_path, doraise=True)
            content = main_path.read_text(encoding="utf-8")
            self.assertIn("register_routes(app)", content)
            self.assertIn("get_mixed_precision()", content)
            self.assertNotIn("tk.Tk()", content)
            html = (output / "frontend" / "index.html").read_text(encoding="utf-8")
            self.assertIn("file_browser.js", html)

    def test_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            archive = temp / "bad.zip"
            archive.write_bytes(b"not a zip")
            lock = temp / "lock.json"
            lock.write_text(json.dumps({"archive": "bad.zip", "sha256": "0" * 64, "version": "test"}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                materialize.materialize(archive, lock, temp / "output")


if __name__ == "__main__":
    unittest.main()
