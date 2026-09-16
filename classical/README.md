# Classical Machine Learning

The supported workload is under `classical/python-sdk-v2`.

- `data-science/` contains the preparation, training, and evaluation source.
- `mlops/azureml/train/job.yml` defines the pipeline loaded and submitted by the
  reusable Python SDK v2 workflow.

Authentication is supplied by GitHub Environment OIDC through the reusable
workflows. The Python entrypoints use `DefaultAzureCredential` and never accept a
client secret.
