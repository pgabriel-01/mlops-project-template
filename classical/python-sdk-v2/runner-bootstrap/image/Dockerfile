FROM gcr.io/kaniko-project/executor@sha256:c3109d5926a997b100c4343944e06c6b30a6804b2f9abe0994d3de6ef92b028e AS kaniko

FROM ghcr.io/actions/actions-runner:2.337.0

USER root

ARG AZURE_CLI_VERSION=2.90.0-1~noble
ARG SOURCE_REPOSITORY_URL=https://github.com/example/example

COPY --from=kaniko /kaniko/executor /kaniko/executor
COPY --from=kaniko /kaniko/ssl/certs/ca-certificates.crt /kaniko/ssl/certs/ca-certificates.crt

LABEL org.opencontainers.image.source="${SOURCE_REPOSITORY_URL}" \
      org.opencontainers.image.description="Tool-complete ephemeral ARC runner for private MLOps workflows" \
      org.opencontainers.image.licenses="MIT"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      gnupg \
      python3 \
      python3-pip \
      python3-venv \
    && mkdir -p /etc/apt/keyrings \
    && curl --fail --silent --show-error \
      https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg \
    && chmod 0644 /etc/apt/keyrings/microsoft.gpg \
    && printf '%s\n' \
      'Types: deb' \
      'URIs: https://packages.microsoft.com/repos/azure-cli/' \
      'Suites: noble' \
      'Components: main' \
      'Architectures: amd64' \
      'Signed-by: /etc/apt/keyrings/microsoft.gpg' \
      > /etc/apt/sources.list.d/azure-cli.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends "azure-cli=${AZURE_CLI_VERSION}" \
    && chmod 0755 /kaniko/executor \
    && chown -R runner:runner /kaniko \
    && /kaniko/executor version \
    && az version \
    && python3 --version \
    && rm -rf /var/lib/apt/lists/*

USER runner
