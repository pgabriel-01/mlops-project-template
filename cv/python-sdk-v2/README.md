# Computer Vision with Python SDK v2

This folder contains the Azure ML Python SDK v2 implementation of the Computer Vision MLOps pipeline for image classification.

## Structure

```
cv/python-sdk-v2/
├── data/                           # Sample data or data references
├── data-science/
│   ├── environments/
│   │   └── training/
│   │       ├── Dockerfile          # NVIDIA PyTorch container with CV dependencies
│   │       ├── requirements.txt    # Python dependencies
│   │       └── ndv4-topo.xml      # Azure NDv4 (A100) GPU topology file
│   ├── src/
│   │   ├── train.py               # Distributed PyTorch training script
│   │   ├── image_io.py            # Image dataset loading utilities
│   │   ├── profiling.py           # PyTorch profiler utilities
│   │   └── model/                 # Model architectures (ResNet, Swin, etc.)
│   └── tests/                     # Unit tests
└── mlops/
    └── azureml/
        ├── train/
        │   └── pipeline-train.py  # Azure ML SDK v2 training pipeline
        └── deploy/                # Deployment scripts (future)
```

## Prerequisites

1. Azure subscription with Azure ML workspace
2. Python 3.10+ with Azure ML SDK v2:
   ```bash
   pip install azure-ai-ml azure-identity
   ```
3. GPU compute cluster configured in Azure ML (for training)
4. Training and validation image datasets in Azure ML data assets

## Usage

### Training Pipeline

Submit a training job to Azure ML:

```bash
cd cv/python-sdk-v2/mlops/azureml/train

python pipeline-train.py \
    -n cv_training_experiment \
    --train_data azureml://datastores/workspaceblobstore/paths/cv/train \
    --valid_data azureml://datastores/workspaceblobstore/paths/cv/valid \
    --model_arch resnet18 \
    --num_epochs 10 \
    --batch_size 64 \
    --learning_rate 0.001 \
    --gpu_compute gpu-cluster \
    --training_nodes 1 \
    --gpus_per_node 1 \
    --wait
```

### Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--model_arch` | resnet18 | Model architecture (resnet18, resnet50, swin_t, etc.) |
| `--model_arch_pretrained` | True | Use pretrained ImageNet weights |
| `--num_epochs` | 10 | Number of training epochs |
| `--batch_size` | 64 | Training batch size |
| `--learning_rate` | 0.001 | Optimizer learning rate |
| `--momentum` | 0.9 | SGD momentum |
| `--training_nodes` | 1 | Number of nodes for distributed training |
| `--gpus_per_node` | 1 | GPUs per node |

### Supported Model Architectures

From torchvision:
- ResNet: `resnet18`, `resnet34`, `resnet50`, `resnet101`, `resnet152`
- EfficientNet: `efficientnet_b0` through `efficientnet_b7`
- MobileNet: `mobilenet_v2`, `mobilenet_v3_small`, `mobilenet_v3_large`

From Hugging Face Transformers:
- Swin Transformer: `swin_t`, `swin_s`, `swin_b`

## Environment

The training environment uses the NVIDIA PyTorch container (`nvcr.io/nvidia/pytorch:25.01-py3`) with:
- PyTorch 2.6.0 with CUDA 12.8
- Python 3.12
- Optimized for Azure NDv4 (A100) and NCv3 (V100) GPU VMs

**Note:** The 25.x container series drops support for Volta (V100) GPUs. For V100 support, use the 24.x series container.

## Differences from aml-cli-v2

This Python SDK v2 implementation provides:
1. **Programmatic pipeline definition**: Define pipelines in Python code instead of YAML
2. **Type-safe inputs/outputs**: Use Python types for pipeline parameters
3. **Better IDE support**: Full IntelliSense and type checking
4. **Easier debugging**: Step through pipeline construction in debugger
5. **Dynamic pipeline construction**: Build pipelines conditionally based on parameters

## Related Documentation

- [Azure ML Python SDK v2 Documentation](https://learn.microsoft.com/azure/machine-learning/how-to-use-azure-ml-sdk-v2)
- [MLOps v2 Architecture](../../documentation/architecture/vision.md)
- [CV aml-cli-v2 Implementation](../aml-cli-v2/README.md)
