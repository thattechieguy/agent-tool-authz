@description('API Management service name')
param apimName string

@description('Location for resources')
param location string = resourceGroup().location

@description('Publisher name')
param publisherName string = 'agent-authz-bench'

@description('Publisher email')
param publisherEmail string

resource apim 'Microsoft.ApiManagement/service@2022-08-01' = {
  name: apimName
  location: location
  sku: {
    name: 'Consumption'
    capacity: 0
  }
  properties: {
    publisherName: publisherName
    publisherEmail: publisherEmail
  }
}

output gatewayUrl string = apim.properties.gatewayUrl
