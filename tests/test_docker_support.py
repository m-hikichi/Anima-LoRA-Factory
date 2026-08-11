import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from docker.app import docker_support


class DockerSupportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.datasets = root / "datasets"
        self.models = root / "models"
        self.output = root / "output"
        for path in (self.datasets, self.models, self.output):
            path.mkdir()
        self.environment = mock.patch.dict(os.environ, {
            "DATASETS_ROOT": str(self.datasets),
            "MODELS_ROOT": str(self.models),
            "OUTPUT_ROOT": str(self.output),
            "MIXED_PRECISION": "auto",
        })
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_validate_path_accepts_path_inside_allowed_root(self):
        child = self.datasets / "set-a"
        child.mkdir()
        actual = docker_support.validate_path(str(child), ("datasets",), "directory")
        self.assertEqual(Path(actual), child.resolve())

    def test_validate_path_rejects_parent_traversal(self):
        with self.assertRaises(docker_support.PathAccessError):
            docker_support.validate_path(str(self.datasets / ".." / "models"), ("datasets",), "directory")

    def test_validate_path_rejects_symlink_escape(self):
        outside = Path(self.temp_dir.name) / "outside"
        outside.mkdir()
        link = self.datasets / "escape"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks is unavailable")
        with self.assertRaises(docker_support.PathAccessError):
            docker_support.validate_path(str(link), ("datasets",), "directory")

    def test_model_browser_filters_files_and_sorts_directories_first(self):
        (self.models / "nested").mkdir()
        (self.models / "model.safetensors").write_text("model", encoding="utf-8")
        (self.models / "notes.txt").write_text("notes", encoding="utf-8")
        result = docker_support.list_entries("models", str(self.models), "model")
        self.assertEqual([entry["name"] for entry in result["entries"]], ["nested", "model.safetensors"])

    def test_training_config_validates_all_mount_roles(self):
        dataset = self.datasets / "set-a"
        dataset.mkdir()
        model_files = []
        for name in ("base.safetensors", "vae.safetensors", "qwen.safetensors"):
            path = self.models / name
            path.write_text(name, encoding="utf-8")
            model_files.append(path)
        config = SimpleNamespace(path=str(dataset), model=str(model_files[0]), vae=str(model_files[1]),
                                 qwen3=str(model_files[2]), output_dir=str(self.output),
                                 name="character_v1", shutdown=False)
        docker_support.validate_training_config(config)
        self.assertEqual(config.output_dir, str(self.output.resolve()))

    def test_output_name_rejects_path_components(self):
        for name in ("../escape", "folder/name", "", "name with spaces"):
            with self.subTest(name=name), self.assertRaises(docker_support.PathAccessError):
                docker_support.validate_output_name(name)

    def test_explicit_precision_override(self):
        with mock.patch.dict(os.environ, {"MIXED_PRECISION": "bf16"}):
            self.assertEqual(docker_support.get_mixed_precision(), "bf16")

    def test_auto_precision_falls_back_to_fp16_without_torch(self):
        with mock.patch.dict("sys.modules", {"torch": None}):
            self.assertEqual(docker_support.get_mixed_precision(), "fp16")


if __name__ == "__main__":
    unittest.main()

