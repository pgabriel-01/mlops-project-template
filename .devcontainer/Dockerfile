FROM mcr.microsoft.com/devcontainers/miniconda:latest

# Update the conda environment according to the environment.yml file in the project.
COPY environment.yml /tmp/conda-tmp/
RUN /opt/conda/bin/conda env update -n base -f /tmp/conda-tmp/environment.yml && rm -rf /tmp/conda-tmp