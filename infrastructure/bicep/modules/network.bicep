param name string
param location string
param tags object
param addressPrefix string = '10.40.0.0/16'
param aksSubnetPrefix string = '10.40.0.0/20'
param postgresSubnetPrefix string = '10.40.16.0/24'

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [addressPrefix] }
    subnets: [
      {
        name: 'aks'
        properties: { addressPrefix: aksSubnetPrefix }
      }
      {
        name: 'postgres'
        properties: {
          addressPrefix: postgresSubnetPrefix
          delegations: [
            { name: 'pg', properties: { serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers' } }
          ]
        }
      }
    ]
  }
}

resource dnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: '${name}.private.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource dnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: dnsZone
  name: '${name}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}

output aksSubnetId string = '${vnet.id}/subnets/aks'
output postgresSubnetId string = '${vnet.id}/subnets/postgres'
output postgresDnsZoneId string = dnsZone.id
