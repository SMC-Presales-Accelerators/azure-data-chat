@description('Specifies the location in which the Azure Storage resources should be deployed.')
param location string = resourceGroup().location

@description('Name for the app service, this will be the beginning of the FQDN.')
param website_name string

@secure()
@description('ODBC Connection string for the database you would like to chat with')
param database_connection_string string

@description('Does your connection string use a Managed Identity?')
param database_connection_string_use_managed_identity bool = false

@description('Account name for the OpenAI deployment')
param openai_account_name string = uniqueString(website_name, 'openai')

@description('OpenAI Deployment name for the model deployment.')
param openai_deployment_name string = 'gpt35'

var app_service_plan_name = uniqueString(website_name)

resource openai_account 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' = {
  kind: 'OpenAI'
  location: location
  name: openai_account_name
  properties: {
    customSubDomainName: openai_account_name
    networkAcls: {
      defaultAction: 'Allow'
      ipRules: []
      virtualNetworkRules: []
    }
    publicNetworkAccess: 'Enabled'
  }
  sku: {
    name: 'S0'
  }
}

resource openai_deployment 'Microsoft.CognitiveServices/accounts/deployments@2023-10-01-preview' = {
  parent: openai_account
  name: openai_deployment_name
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-35-turbo'
      version: '0301'
    }
  }
  sku: {
    capacity: 30
    name: 'Standard'
  }
}

resource app_service_plan 'Microsoft.Web/serverfarms@2022-09-01' = {
  kind: 'linux'
  location: location
  name: app_service_plan_name
  properties: {
    elasticScaleEnabled: false
    hyperV: false
    isSpot: false
    isXenon: false
    maximumElasticWorkerCount: 1
    perSiteScaling: false
    reserved: true
    targetWorkerCount: 0
    targetWorkerSizeId: 0
    zoneRedundant: false
  }
  sku: {
    capacity: 1
    family: 'Pv3'
    name: 'P0v3'
    size: 'P0v3'
    tier: 'Premium0V3'
  }
}

resource app_service 'Microsoft.Web/sites@2020-06-01' = {
  name: website_name
  location: location
  identity: {
    type: database_connection_string_use_managed_identity ? 'SystemAssigned' : 'None'
  }
  properties: {
    serverFarmId: app_service_plan.id
    siteConfig: {
      linuxFxVersion: 'DOCKER|ghcr.io/cbattlegear/azure-data-chat:latest'
    }
  }
}

resource app_service_config 'Microsoft.Web/sites/config@2020-06-01' = {
  parent: app_service
  name: 'appsettings'
  properties: {
    AZURE_OPENAI_API_KEY: openai_account.listKeys().key1
    AZURE_OPENAI_CHATGPT_DEPLOYMENT: openai_deployment.name
    AZURE_OPENAI_ENDPOINT: openai_account.properties.endpoint
    AZURE_OPENAI_CHATGPT_MODEL: 'gpt-35-turbo'
    DOCKER_REGISTRY_SERVER_URL: 'https://ghcr.io'
    DATABASE_CONNECTION_STRING: database_connection_string
  }
}
