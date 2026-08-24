"""YOLOv8 training script for Azure ML."""
import os
import sys
import yaml
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

import mlflow
from ultralytics import YOLO
from azure.storage.blob import BlobServiceClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_task_config(task_type: str) -> Dict[str, Any]:
    """Get YOLO model and config for task type."""
    configs = {
        "object_detection": {
            "model": "yolov8n.pt",
            "mode": "detect"
        },
        "classification": {
            "model": "yolov8n-cls.pt", 
            "mode": "classify"
        },
        "segmentation": {
            "model": "yolov8n-seg.pt",
            "mode": "segment"
        }
    }
    return configs.get(task_type, configs["object_detection"])


def download_dataset(dataset_url: str, local_path: str = "/tmp/dataset") -> str:
    """Download dataset from blob storage."""
    logger.info(f"Downloading dataset from {dataset_url}")
    
    # Parse blob URL
    if dataset_url.startswith("https://") and "blob.core.windows.net" in dataset_url:
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION")
        if connection_string:
            blob_service = BlobServiceClient.from_connection_string(connection_string)
            # Parse container and blob path
            parts = dataset_url.split("/")
            container = parts[3] if len(parts) > 3 else "datasets"
            blob_path = "/".join(parts[4:]) if len(parts) > 4 else "data"
            
            # Download
            container_client = blob_service.get_container_client(container)
            local_path = Path(local_path)
            local_path.mkdir(parents=True, exist_ok=True)
            
            for blob in container_client.list_blobs(name_starts_with=blob_path):
                local_file = local_path / Path(blob.name).name
                with open(local_file, "wb") as f:
                    f.write(container_client.download_blob(blob.name).readall())
            
            return str(local_path)
    
    # If local path or HTTP URL
    if os.path.exists(dataset_url):
        return dataset_url
    
    return dataset_url


def create_data_yaml(data_dir: str, task_type: str) -> str:
    """Create YOLO data.yaml configuration."""
    yaml_path = Path(data_dir) / "data.yaml"
    
    # Auto-detect classes from directory structure
    if task_type == "classification":
        classes = [d.name for d in Path(data_dir).iterdir() if d.is_dir()]
        data_config = {
            "path": data_dir,
            "train": "train",
            "val": "val",
            "nc": len(classes),
            "names": {i: name for i, name in enumerate(classes)}
        }
    else:
        # Detection/Segmentation - use existing yaml or create default
        existing_yaml = Path(data_dir) / "data.yaml"
        if existing_yaml.exists():
            return str(existing_yaml)
        
        data_config = {
            "path": data_dir,
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "names": {0: "object"},  # Default single class
            "nc": 1
        }
    
    with open(yaml_path, "w") as f:
        yaml.dump(data_config, f)
    
    return str(yaml_path)


def train_model(config: Dict[str, Any]) -> str:
    """Train YOLO model and return model path."""
    # Get parameters
    dataset_url = os.getenv("DATASET_URL", config.get("dataset_url"))
    task_type = os.getenv("TASK_TYPE", config.get("task_type", "object_detection"))
    project_id = os.getenv("PROJECT_ID", config.get("project_id", "default"))
    
    epochs = config.get("epochs", 100)
    imgsz = config.get("imgsz", 640)
    batch = config.get("batch", 16)
    lr = config.get("learning_rate", 0.01)
    
    # Download dataset
    data_dir = download_dataset(dataset_url)
    data_yaml = create_data_yaml(data_dir, task_type)
    
    # Get task config
    task_config = get_task_config(task_type)
    
    # Start MLflow tracking
    mlflow.set_experiment(f"visiondock-{project_id}")
    with mlflow.start_run():
        mlflow.log_params({
            "task_type": task_type,
            "epochs": epochs,
            "imgsz": imgsz,
            "batch": batch,
            "lr": lr,
            "model": task_config["model"]
        })
        
        logger.info(f"Loading model: {task_config['model']}")
        model = YOLO(task_config["model"])
        
        # Train
        logger.info("Starting training...")
        results = model.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            lr0=lr,
            device=0,  # Use GPU
            project="/tmp/runs",
            name=f"train_{project_id}",
            exist_ok=True
        )
        
        # Log metrics
        metrics = {
            "mAP50": results.results_dict.get("metrics/mAP50(B)", 0),
            "mAP50-95": results.results_dict.get("metrics/mAP50-95(B)", 0),
            "precision": results.results_dict.get("metrics/precision(B)", 0),
            "recall": results.results_dict.get("metrics/recall(B)", 0)
        }
        mlflow.log_metrics(metrics)
        
        # Save model
        model_dir = f"/tmp/models/{project_id}"
        Path(model_dir).mkdir(parents=True, exist_ok=True)
        
        # Export to ONNX
        logger.info("Exporting to ONNX...")
        onnx_path = model.export(format="onnx", dynamic=True, simplify=True)
        
        # Copy best model
        best_model = f"/tmp/runs/train_{project_id}/weights/best.pt"
        if os.path.exists(best_model):
            import shutil
            shutil.copy(best_model, f"{model_dir}/best.pt")
            mlflow.log_artifact(f"{model_dir}/best.pt")
        
        # Upload to blob storage if connection available
        if os.getenv("AZURE_STORAGE_CONNECTION"):
            upload_to_blob(model_dir, project_id)
        
        logger.info(f"Training complete. Model saved to {model_dir}")
        return model_dir


def upload_to_blob(local_dir: str, project_id: str):
    """Upload trained model to Azure Blob Storage."""
    try:
        connection = os.getenv("AZURE_STORAGE_CONNECTION")
        if not connection:
            return
        
        blob_service = BlobServiceClient.from_connection_string(connection)
        container_name = "models"
        
        # Create container if not exists
        try:
            blob_service.create_container(container_name)
        except Exception:
            pass
        
        container_client = blob_service.get_container_client(container_name)
        
        for file_path in Path(local_dir).rglob("*"):
            if file_path.is_file():
                blob_name = f"{project_id}/{file_path.name}"
                with open(file_path, "rb") as f:
                    container_client.upload_blob(blob_name, f.read(), overwrite=True)
        
        logger.info(f"Uploaded model to blob storage: {project_id}")
    except Exception as e:
        logger.error(f"Failed to upload to blob: {e}")


def main():
    """Main entry point."""
    # Load config from file if provided
    config_file = os.getenv("TRAINING_CONFIG", "/workspace/config.json")
    if os.path.exists(config_file):
        with open(config_file) as f:
            config = json.load(f)
    else:
        config = {}
    
    # Train
    model_path = train_model(config)
    
    # Output result
    result = {
        "model_path": model_path,
        "project_id": os.getenv("PROJECT_ID"),
        "status": "completed"
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
