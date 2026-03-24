// API Management — AI Gateway for rate limiting, caching, and load balancing AI model endpoints.
// Deploys a Consumption-tier APIM instance with a GenAI product and policies.

param baseName string
param location string
param tags object
param publisherEmail string = 'mlops@contoso.com'
param publisherName string = 'MLOps Team'
param skuName string = 'Consumption'
param skuCapacity int = 0

// API Management instance
resource apim 'Microsoft.ApiManagement/service@2024-06-01-preview' = {
  name: 'apim-${baseName}'
  location: location
  sku: {
    name: skuName
    capacity: skuCapacity
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
  tags: tags
}

// GenAI product — groups AI model APIs under rate-limited product
resource genaiProduct 'Microsoft.ApiManagement/service/products@2024-06-01-preview' = {
  parent: apim
  name: 'genai'
  properties: {
    displayName: 'GenAI Models'
    description: 'AI model endpoints with rate limiting and content safety'
    subscriptionRequired: true
    approvalRequired: false
    state: 'published'
  }
}

// Rate limiting policy — applied at product level
resource genaiPolicy 'Microsoft.ApiManagement/service/products/policies@2024-06-01-preview' = {
  parent: genaiProduct
  name: 'policy'
  properties: {
    format: 'xml'
    value: '''
<policies>
  <inbound>
    <base />
    <rate-limit calls="60" renewal-period="60" />
    <set-header name="x-ms-gateway" exists-action="override">
      <value>apim-ai-gateway</value>
    </set-header>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>'''
  }
}

output apimId string = apim.id
output apimName string = apim.name
output apimGatewayUrl string = apim.properties.gatewayUrl
output apimIdentityPrincipalId string = apim.identity.principalId
