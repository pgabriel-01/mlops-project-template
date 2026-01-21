# CV Training Environment - Updated January 2026
# Check release notes https://docs.nvidia.com/deeplearning/frameworks/pytorch-release-notes/index.html
# Using 25.01 container with PyTorch 2.6.0, CUDA 12.8, Ubuntu 24.04
# NOTE: Volta (V100) support discontinued in 25.x - only Ampere (A100), Hopper (H100), Blackwell supported
FROM nvcr.io/nvidia/pytorch:25.01-py3

##############################################################################
# NCCL TESTS
##############################################################################
ENV NCCL_TESTS_TAG=v2.13.9

# NOTE: gencodes for A100 (sm_80), H100 (sm_90), Blackwell (sm_100)
RUN mkdir /tmp/nccltests && \
    cd /tmp/nccltests && \
    git clone -b ${NCCL_TESTS_TAG} https://github.com/NVIDIA/nccl-tests.git && \
    cd nccl-tests && \
    make \
    MPI=1 MPI_HOME=/opt/hpcx/ompi \
    NVCC_GENCODE="-gencode=arch=compute_80,code=sm_80 -gencode=arch=compute_90,code=sm_90 -gencode=arch=compute_100,code=sm_100" \
    CUDA_HOME=/usr/local/cuda && \
    cp ./build/* /usr/local/bin && \
    rm -rf /tmp/nccltests

# Install dependencies missing in this container
COPY requirements.txt ./
RUN pip install -r requirements.txt

# add ndv4-topo.xml for Azure NDv4 (A100) topology
RUN mkdir -p /opt/microsoft/
ADD ./ndv4-topo.xml /opt/microsoft

# to use on A100, enable env var below in your job
# ENV NCCL_TOPO_FILE="/opt/microsoft/ndv4-topo.xml"

# adjusts the level of info from NCCL tests
ENV NCCL_DEBUG="INFO"
ENV NCCL_DEBUG_SUBSYS="GRAPH,INIT,ENV"

# Relaxed Ordering can greatly help the performance of Infiniband networks in virtualized environments.
ENV NCCL_IB_PCI_RELAXED_ORDERING="1"
ENV CUDA_DEVICE_ORDER="PCI_BUS_ID"
ENV NCCL_SOCKET_IFNAME="eth0"
