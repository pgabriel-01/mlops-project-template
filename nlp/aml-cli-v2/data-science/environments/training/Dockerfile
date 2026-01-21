# NLP Training Environment - Updated January 2026
# Check release notes https://docs.nvidia.com/deeplearning/frameworks/pytorch-release-notes/index.html
# Using 25.01 container with PyTorch 2.6.0, CUDA 12.8, Ubuntu 24.04
# NOTE: Volta (V100) support discontinued in 25.x - only Ampere (A100), Hopper (H100), Blackwell supported
FROM nvcr.io/nvidia/pytorch:25.01-py3

WORKDIR /workspace

# Install dependencies
COPY requirements.txt /workspace/
RUN pip install --no-cache-dir -r requirements.txt
