// Microsoft Defender for Storage — enables threat protection on the ML storage account.
// Uses the per-resource Defender for Storage settings (replaces deprecated advancedThreatProtection).

param workspaceId string
param storageAccountId string
param location string

// Extract resource names from IDs
var storageName = last(split(storageAccountId, '/'))

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageName
}

// Enable Defender for Storage on the Storage Account
resource defenderForStorage 'Microsoft.Security/defenderForStorageSettings@2025-01-01' = {
  name: 'current'
  scope: storageAccount
  properties: {
    isEnabled: true
    malwareScanning: {
      onUpload: {
        isEnabled: true
        capGBPerMonth: 5000
      }
    }
    sensitiveDataDiscovery: {
      isEnabled: true
    }
    overrideSubscriptionLevelSettings: true
  }
}

output defenderEnabled bool = true
output protectedStorageId string = storageAccountId
output protectedWorkspaceId string = workspaceId
output defenderLocation string = location
