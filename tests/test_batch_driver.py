import importlib.util
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BATCH_DRIVER = (
    ROOT
    / "classical/aml-cli-v2/mlops/azureml/deploy/batch/code/batch_driver.py"
)


def load_batch_driver():
    spec = importlib.util.spec_from_file_location("batch_driver", BATCH_DRIVER)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "mlflow": SimpleNamespace(pyfunc=SimpleNamespace()),
            "pandas": SimpleNamespace(),
        },
    ):
        spec.loader.exec_module(module)
    return module


class BatchDriverModelPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch_driver = load_batch_driver()

    def test_resolves_model_from_direct_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "MLmodel").touch()
            (root / "nested").mkdir()
            (root / "nested" / "MLmodel").touch()

            self.assertEqual(
                self.batch_driver._resolve_mlflow_model_path(root),
                root,
            )

    def test_resolves_one_nested_registered_model_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "registered-model"
            nested.mkdir()
            (nested / "MLmodel").touch()

            self.assertEqual(
                self.batch_driver._resolve_mlflow_model_path(root),
                nested,
            )

    def test_rejects_missing_mlflow_model_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            with self.assertRaisesRegex(
                FileNotFoundError,
                "No MLflow model root containing MLmodel",
            ):
                self.batch_driver._resolve_mlflow_model_path(root)

    def test_rejects_ambiguous_nested_model_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("model-a", "model-b"):
                candidate = root / name
                candidate.mkdir()
                (candidate / "MLmodel").touch()

            with self.assertRaisesRegex(
                RuntimeError,
                "Multiple MLflow model roots",
            ):
                self.batch_driver._resolve_mlflow_model_path(root)


if __name__ == "__main__":
    unittest.main()
