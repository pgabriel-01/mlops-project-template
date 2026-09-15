import logging
import os
from pathlib import Path

import mlflow
import pandas as pd

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _resolve_mlflow_model_path(model_dir):
    model_root = Path(model_dir)
    if (model_root / "MLmodel").is_file():
        return model_root

    if not model_root.is_dir():
        raise FileNotFoundError(f"Model directory does not exist: {model_root}")

    candidates = sorted(
        child
        for child in model_root.iterdir()
        if child.is_dir() and (child / "MLmodel").is_file()
    )
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(
            f"No MLflow model root containing MLmodel was found in "
            f"{model_root} or its immediate child directories"
        )

    candidate_paths = ", ".join(str(candidate) for candidate in candidates)
    raise RuntimeError(
        f"Multiple MLflow model roots were found under {model_root}: "
        f"{candidate_paths}"
    )


def _get_expected_feature_names(loaded_model):
    metadata = getattr(loaded_model, "metadata", None)
    if metadata is not None:
        input_schema = metadata.get_input_schema()
        if input_schema is not None:
            input_names = input_schema.input_names()
            if input_names and all(input_names):
                return list(input_names)

    model_impl = getattr(loaded_model, "_model_impl", None)
    sklearn_model = getattr(model_impl, "sklearn_model", None)
    feature_names = getattr(sklearn_model, "feature_names_in_", None)
    if feature_names is not None:
        return list(feature_names)

    return None


def _select_model_features(data, loaded_model):
    expected_features = _get_expected_feature_names(loaded_model)
    if expected_features is None:
        return data

    missing_features = [
        feature for feature in expected_features if feature not in data.columns
    ]
    if missing_features:
        raise ValueError(
            "Batch input is missing model features: "
            + ", ".join(missing_features)
        )

    ignored_columns = [
        column for column in data.columns if column not in expected_features
    ]
    if ignored_columns:
        logger.info(
            "Ignoring batch input columns not used by the model: %s",
            ", ".join(ignored_columns),
        )

    return data[expected_features]


def init():
    """
    Initialize the model for batch scoring.
    This function is called once when the batch deployment starts.
    """
    global model
    
    # The model path is provided by Azure ML
    # For batch deployments, the model is in AZUREML_MODEL_DIR
    model_dir = os.environ.get("AZUREML_MODEL_DIR")
    logger.info(f"AZUREML_MODEL_DIR: {model_dir}")
    
    if model_dir:
        logger.info(f"Contents of model directory: {os.listdir(model_dir)}")
    else:
        model_dir = "./model"

    model_path = _resolve_mlflow_model_path(model_dir)
    
    # Load the MLflow model
    try:
        model = mlflow.pyfunc.load_model(str(model_path))
        logger.info(f"Model loaded successfully from {model_path}")
    except Exception as e:
        logger.error(f"Failed to load model from {model_path}: {str(e)}")
        raise


def run(mini_batch):
    """
    Process a mini-batch of data.
    
    Args:
        mini_batch: List of file paths to process
        
    Returns:
        DataFrame with predictions (for append_row output action)
    """
    logger.info(f"Processing mini-batch with {len(mini_batch)} files")
    
    results = []
    
    for file_path in mini_batch:
        try:
            logger.info(f"Processing file: {file_path}")
            
            # Read the CSV file
            data = pd.read_csv(file_path)
            logger.info(f"Read {len(data)} rows from {file_path}")
            
            # Make predictions
            predictions = model.predict(_select_model_features(data, model))
            logger.info(f"Generated {len(predictions)} predictions")
            
            # Append predictions as rows (for append_row output action)
            for pred in predictions:
                results.append([pred])
                
        except Exception as e:
            logger.error(f"Error processing {file_path}: {str(e)}")
            raise
    
    # Return as DataFrame for append_row output action
    return pd.DataFrame(results)
