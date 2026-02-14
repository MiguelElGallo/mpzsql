param location string
param containerAppsEnvironmentName string
param containerAppName string
param containerAppIdentityId string
param containerAppIdentityName string
param containerAppIdentityClientId string
param containerAppImage string
param containerCpu string
param containerMemory string
param storageAccountName string
param postgresFqdn string
param postgresDatabaseName string
param ducklakeDataPath string
param acrLoginServer string

@description('Key Vault secret URI for the Flight SQL password.')
param lakehousePasswordSecretUri string

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'law-${containerAppsEnvironmentName}'
  location: location
  properties: {
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppsEnvironmentName
  location: location
  properties: {
    peerAuthentication: {
      mtls: {
        enabled: true
      }
    }
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: {
    'azd-service-name': 'lakehouse'
  }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${containerAppIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      secrets: [
        {
          name: 'lakehouse-password'
          keyVaultUrl: lakehousePasswordSecretUri
          identity: containerAppIdentityId
        }
      ]
      registries: [
        {
          server: acrLoginServer
          identity: containerAppIdentityId
        }
      ]
      ingress: {
        external: true
        targetPort: 31337
        transport: 'http2'
      }
    }
    template: {
      containers: [
        {
          name: 'app'
          image: containerAppImage
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: [
            {
              name: 'LAKEHOUSE_AZURE_STORAGE_ACCOUNT'
              value: storageAccountName
            }
            {
              name: 'LAKEHOUSE_PG_HOST'
              value: postgresFqdn
            }
            {
              name: 'LAKEHOUSE_PG_DATABASE'
              value: postgresDatabaseName
            }
            {
              name: 'LAKEHOUSE_PG_USER'
              value: containerAppIdentityName
            }
            {
              name: 'LAKEHOUSE_DUCKLAKE_DATA_PATH'
              value: ducklakeDataPath
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: containerAppIdentityClientId
            }
            {
              name: 'LAKEHOUSE_PASSWORD'
              secretRef: 'lakehouse-password'
            }
          ]
          probes: [
            {
              type: 'liveness'
              tcpSocket: {
                port: 8081
              }
              periodSeconds: 10
              initialDelaySeconds: 15
              failureThreshold: 3
            }
            {
              type: 'readiness'
              tcpSocket: {
                port: 8081
              }
              periodSeconds: 5
              initialDelaySeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output containerAppName string = containerApp.name
