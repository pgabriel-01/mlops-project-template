// Azure Bastion + Jump Box VM for accessing VNet-isolated AML workspace.
// Deploys: Public IP, Bastion Host (Basic SKU), NSG, NIC, and Ubuntu jump box VM.

param baseName string
param location string
param tags object
param bastionSubnetId string
param defaultSubnetId string
param adminUsername string = 'azureuser'

@secure()
param adminPassword string

param vmSize string = 'Standard_B2s'

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

// NSG for the jump box
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

// Jump box VM (Ubuntu 22.04 LTS)
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
      adminPassword: adminPassword
      linuxConfiguration: {
        disablePasswordAuthentication: false
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: '0001-com-ubuntu-server-jammy'
        sku: '22_04-lts-gen2'
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

output bastionName string = bastion.name
output bastionId string = bastion.id
output jumpBoxVmName string = jumpBoxVm.name
output jumpBoxPrivateIp string = jumpBoxNic.properties.ipConfigurations[0].properties.privateIPAddress
