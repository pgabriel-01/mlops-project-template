param workspaceName string
param environmentName string
param environmentVersion string
param imageUri string

resource workspace 'Microsoft.MachineLearningServices/workspaces@2025-06-01' existing = {
  name: workspaceName
}

resource environment 'Microsoft.MachineLearningServices/workspaces/environments@2025-06-01' = {
  name: environmentName
  parent: workspace
  properties: {
    description: 'Immutable image-only environment for private AKS online inference.'
  }
}

resource version 'Microsoft.MachineLearningServices/workspaces/environments/versions@2025-06-01' = {
  name: environmentVersion
  parent: environment
  properties: {
    description: 'Python 3.10 MLflow no-code inference runtime pinned by image digest.'
    image: imageUri
    isArchived: false
  }
}

output environmentId string = version.id
