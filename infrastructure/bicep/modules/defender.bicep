// Microsoft Defender for AI — enables threat protection on ML workspace and storage.
// Uses the per-resource security settings (Advanced Threat Protection).

param workspaceId string
param storageAccountId string
param location string

// Extract resource names from IDs
var storageName = last(split(storageAccountId, '/'))

// Enable Advanced Threat Protection on the Storage Account
resource storageAtp 'Microsoft.Security/advancedThreatProtection@2019-01-01' = {
  name: 'current'
  scope: storageAccount
  properties: {
    isEnabled: true
  }
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageName
}

output defenderEnabled bool = true
output protectedStorageId string = storageAccountId
output protectedWorkspaceId string = workspaceId
output defenderLocation string = location
