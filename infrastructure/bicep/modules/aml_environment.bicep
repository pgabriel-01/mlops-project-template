param workspaceName string
@minLength(1)
param environmentName string
@minLength(1)
param environmentVersion string
@minLength(1)
param imageUri string

var validatedImageUri = contains(imageUri, '@sha256:') && length(last(split(imageUri, '@sha256:'))) == 64
  ? imageUri
  : fail('The image-only online environment must use an immutable sha256 digest.')

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
    description: 'Custom online inference runtime pinned by image digest.'
    image: validatedImageUri
    isArchived: false
  }
}

output environmentId string = version.id
