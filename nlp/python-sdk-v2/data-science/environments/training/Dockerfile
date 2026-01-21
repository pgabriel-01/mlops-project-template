# NLP Training Environment - Updated January 2026
# Check release notes https://docs.nvidia.com/deeplearning/frameworks/pytorch-release-notes/index.html
# Using 24.01 container with PyTorch 2.2.0, CUDA 12.3, cuDNN 8.9
FROM nvcr.io/nvidia/pytorch:24.01-py3

# Install dependencies
COPY requirements.txt ./
RUN pip install -r requirements.txt
