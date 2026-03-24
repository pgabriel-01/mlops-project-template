param baseName string
param location string
param tags object

resource cr 'Microsoft.ContainerRegistry/registries@2025-11-01' = {
  name: 'cr${baseName}'
  location: location
  sku: {
    name: 'Standard'
  }

  properties: {
    adminUserEnabled: false
  }

  tags: tags
}

output crOut string = cr.id
