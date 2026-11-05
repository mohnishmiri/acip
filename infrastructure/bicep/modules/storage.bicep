param name string
param location string
param tags object
param containerName string
@description('Object id of the collection service principal (Storage Blob Data Reader)')
param readerPrincipalObjectId string

var blobReaderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1')

resource sa 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_ZRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    accessTier: 'Hot'
  }
}

resource blob 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: sa
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 14 }
  }
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blob
  name: containerName
  properties: { publicAccess: 'None' }
}

// Read-only data access for the existing collection service principal
resource reader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sa.id, readerPrincipalObjectId, 'StorageBlobDataReader')
  scope: sa
  properties: {
    roleDefinitionId: blobReaderRoleId
    principalId: readerPrincipalObjectId
    principalType: 'ServicePrincipal'
  }
}

output id string = sa.id
output name string = sa.name
output blobEndpoint string = sa.properties.primaryEndpoints.blob
