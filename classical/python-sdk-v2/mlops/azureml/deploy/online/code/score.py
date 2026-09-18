import json
import os
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd

_model = None


def init() -> None:
    global _model

    model_mount = Path(os.environ["AZUREML_MODEL_DIR"]).resolve()
    model_metadata = sorted(model_mount.rglob("MLmodel"))
    if not model_metadata:
        raise RuntimeError(
            f"No MLflow MLmodel file found below AZUREML_MODEL_DIR={model_mount}"
        )
    _model = mlflow.pyfunc.load_model(str(model_metadata[0].parent))


def run(raw_data: str | bytes | dict[str, Any]) -> dict[str, Any]:
    if _model is None:
        raise RuntimeError("The MLflow model was not initialized")

    payload = json.loads(raw_data) if isinstance(raw_data, (str, bytes)) else raw_data
    input_data = payload.get("input_data")
    if not isinstance(input_data, list) or not input_data:
        raise ValueError("Request must contain a non-empty input_data array")

    predictions = _model.predict(pd.DataFrame(input_data))
    if isinstance(predictions, pd.DataFrame):
        values = predictions.to_dict(orient="records")
    elif isinstance(predictions, pd.Series):
        values = predictions.tolist()
    elif hasattr(predictions, "tolist"):
        values = predictions.tolist()
    else:
        values = list(predictions)
    return {"predictions": values}
