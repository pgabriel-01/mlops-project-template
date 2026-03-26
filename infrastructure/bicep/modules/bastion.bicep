// Azure Bastion + Windows Jump Box VM for accessing VNet-isolated AML workspace.
// Deploys: Public IP, Bastion Host (Basic SKU), NSG, NIC, Windows Server 2022 jump box.
// Password is auto-generated and stored in Key Vault — never exposed in pipelines.

param baseName string
param location string
param tags object
param bastionSubnetId string
param defaultSubnetId string
param keyVaultName string
param adminUsername string = 'azureuser'
param vmSize string = 'Standard_D2s_v3'

// Generate a deterministic password that meets Azure complexity requirements
// uniqueString produces 13 lowercase alphanum chars — we append fixed complexity chars
var generatedPassword = '${uniqueString(resourceGroup().id, baseName, 'bastion')}P@1x'

// Public IP for Bastion
resource bastionPip 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-bastion-${baseName}'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

// Azure Bastion Host
resource bastion 'Microsoft.Network/bastionHosts@2024-05-01' = {
  name: 'bastion-${baseName}'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    ipConfigurations: [
      {
        name: 'bastionIpConfig'
        properties: {
          subnet: {
            id: bastionSubnetId
          }
          publicIPAddress: {
            id: bastionPip.id
          }
        }
      }
    ]
  }
}

// NSG for the jump box — RDP from VNet only (Bastion initiates RDP)
resource jumpBoxNsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-jumpbox-${baseName}'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

// NIC for the jump box (no public IP — access via Bastion only)
resource jumpBoxNic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: 'nic-jumpbox-${baseName}'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: defaultSubnetId
          }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
    ]
    networkSecurityGroup: {
      id: jumpBoxNsg.id
    }
  }
}

// Jump box VM — Windows Server 2022 Datacenter (Desktop Experience)
resource jumpBoxVm 'Microsoft.Compute/virtualMachines@2024-03-01' = {
  name: 'vm-jumpbox-${baseName}'
  location: location
  tags: tags
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    osProfile: {
      computerName: 'jumpbox'
      adminUsername: adminUsername
      adminPassword: generatedPassword
    }
    storageProfile: {
      imageReference: {
        publisher: 'MicrosoftWindowsServer'
        offer: 'WindowsServer'
        sku: '2022-datacenter-g2'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'StandardSSD_LRS'
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: jumpBoxNic.id
        }
      ]
    }
  }
}

// Reference existing Key Vault to store the generated password
resource kv 'Microsoft.KeyVault/vaults@2025-05-01' existing = {
  name: keyVaultName
}

// Store the admin password as a Key Vault secret
resource bastionSecret 'Microsoft.KeyVault/vaults/secrets@2025-05-01' = {
  parent: kv
  name: 'bastion-admin-password'
  properties: {
    value: generatedPassword
    contentType: 'text/plain'
  }
}

output bastionName string = bastion.name
output bastionId string = bastion.id
output jumpBoxVmName string = jumpBoxVm.name
output jumpBoxPrivateIp string = jumpBoxNic.properties.ipConfigurations[0].properties.privateIPAddress
