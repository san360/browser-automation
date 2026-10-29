// Project-level wiring inside the Foundry resource group:
//   * PlaywrightWorkspace connection used by the Browser Automation tool (keyless: project managed identity)
//   * Application Insights connection (enables tracing in the Foundry portal and for hosted agents)
//   * Foundry data-plane roles for the developer running the demo
targetScope = 'resourceGroup'

param foundryAccountName string
param foundryProjectName string
param browserAutomationConnectionName string
param playwrightWorkspaceId string
param playwrightDataplaneUri string
param applicationInsightsId string

@secure()
param applicationInsightsConnectionString string

param developerPrincipalId string = ''
param developerPrincipalType string = 'User'

// Built-in roles
var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d' // Foundry User (formerly Azure AI User)
var foundryProjectManagerRoleId = 'eadc314b-1a2d-4efa-be10-5d325db5065e' // Foundry Project Manager
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName

  resource project 'projects' existing = {
    name: foundryProjectName
  }
}

resource browserAutomationConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: account::project
  name: browserAutomationConnectionName
  properties: {
    category: 'PlaywrightWorkspace'
    // The Browser Automation tool talks to the workspace through its managed MCP endpoint.
    target: '${replace(playwrightDataplaneUri, '.api.playwright.microsoft.com', '.mcp.playwright.microsoft.com')}/mcp'
    #disable-next-line BCP036 // ProjectManagedIdentity is valid for PlaywrightWorkspace connections; the type definition lags.
    authType: 'ProjectManagedIdentity'
    audience: 'https://mcp.playwright.microsoft.com'
    isSharedToAll: true
    credentials: null
    metadata: {
      resourceId: playwrightWorkspaceId
    }
  }
}

resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: account::project
  name: 'appinsights'
  properties: {
    category: 'AppInsights'
    target: applicationInsightsId
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: applicationInsightsConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: applicationInsightsId
    }
  }
}

resource developerFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(account::project.id, developerPrincipalId, foundryUserRoleId)
  scope: account::project
  properties: {
    principalId: developerPrincipalId
    principalType: developerPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
  }
}

resource developerProjectManager 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(account::project.id, developerPrincipalId, foundryProjectManagerRoleId)
  scope: account::project
  properties: {
    principalId: developerPrincipalId
    principalType: developerPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryProjectManagerRoleId)
  }
}

// The Computer Use runner calls the model directly on the account-level endpoint (<account>.openai.azure.com/openai/v1),
// which project-scoped roles do not cover.
resource developerOpenAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(account.id, developerPrincipalId, openAiUserRoleId)
  scope: account
  properties: {
    principalId: developerPrincipalId
    principalType: developerPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
  }
}

output browserAutomationConnectionId string = browserAutomationConnection.id
output appInsightsConnectionId string = appInsightsConnection.id
