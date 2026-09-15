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


class FakeDataFrame:
    def __init__(self, columns):
        self.columns = columns
        self.selected_columns = None

    def __getitem__(self, columns):
        self.selected_columns = columns
        return self


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

    def test_selects_sklearn_model_features_and_ignores_extra_columns(self):
        expected_features = ["distance", "passengers"]
        loaded_model = SimpleNamespace(
            metadata=None,
            _model_impl=SimpleNamespace(
                sklearn_model=SimpleNamespace(
                    feature_names_in_=expected_features,
                )
            ),
        )
        data = FakeDataFrame(["Unnamed: 0", "distance", "passengers", "cost"])

        selected = self.batch_driver._select_model_features(data, loaded_model)

        self.assertIs(selected, data)
        self.assertEqual(data.selected_columns, expected_features)

    def test_rejects_missing_model_features(self):
        loaded_model = SimpleNamespace(
            metadata=None,
            _model_impl=SimpleNamespace(
                sklearn_model=SimpleNamespace(
                    feature_names_in_=["distance", "passengers"],
                )
            ),
        )
        data = FakeDataFrame(["distance", "cost"])

        with self.assertRaisesRegex(
            ValueError,
            "Batch input is missing model features: passengers",
        ):
            self.batch_driver._select_model_features(data, loaded_model)


if __name__ == "__main__":
    unittest.main()
