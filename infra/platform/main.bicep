// Platform layer for the Foundry browser automation demo.
//
// Runs after the `foundry` layer (infra/foundry, microsoft.foundry provider) and adds
// everything the Foundry layer does not own:
//   * Log Analytics + Application Insights (tracing for prompt and hosted agents)
//   * Azure Playwright Workspace (cloud browsers for the Browser Automation tool)
//   * Foundry project connections: PlaywrightWorkspace (keyless, project managed identity) + App Insights
//   * RBAC: Playwright Workspace Contributor for the project identity, Foundry roles for the developer
//   * Demo target website on Azure Container Apps (scale to zero) + Azure Container Registry
//   * A monthly budget with alerts that covers both resource groups
//
// Policy notes (MCAPS / governed subscriptions): no API keys are used anywhere. The Foundry
// account keeps disableLocalAuth=true and the Playwright workspace defaults to localAuth=Disabled.
targetScope = 'subscription'

@minLength(1)
@maxLength(40)
@description('Name of the azd environment. Used for resource names and tags.')
param environmentName string

@description('Region for the platform resources (monitoring, demo site). Defaults to the Foundry region.')
param location string

@description('Region for the Playwright workspace (Playwright Workspaces is available in a subset of regions).')
@allowed([
  'eastus'
  'westus3'
  'westeurope'
  'eastasia'
  'japaneast'
  'australiaeast'
  'switzerlandnorth'
])
param playwrightLocation string = 'westeurope'

@description('Allow Playwright access tokens (needed only for raw Playwright clients such as the optional remote browser for Computer Use). Keyless Entra ID is used otherwise.')
@allowed([
  'Enabled'
  'Disabled'
])
param playwrightLocalAuth string = 'Disabled'

@description('Object ID of the developer running azd. Receives Foundry data-plane roles on the project.')
param principalId string = ''

@description('Principal type of principalId.')
@allowed([
  'User'
  'ServicePrincipal'
  'Group'
])
param principalType string = 'User'

@description('Resource group that holds the Foundry account and project (output of the foundry layer).')
param foundryResourceGroupName string

@description('Foundry (AI Services) account name (output of the foundry layer).')
param foundryAccountName string

@description('Foundry project name (output of the foundry layer).')
param foundryProjectName string

@description('Name of the Browser Automation project connection.')
param browserAutomationConnectionName string = 'browserautomation'

@description('Minimum replicas for the demo site. 0 = scale to zero (cheapest); 1 = no cold start during live demos.')
@minValue(0)
@maxValue(2)
param demoSiteMinReplicas int = 0

@description('Set by azd (SERVICE_DEMO_SITE_RESOURCE_EXISTS) after the first deploy so re-provisioning keeps the image.')
param demoSiteExists bool = false

@description('Daily ingestion cap for Log Analytics in GB (cost guardrail). -1 disables the cap.')
param logAnalyticsDailyCapGb int = 1

@description('Create a monthly cost budget with alerts for the demo resource groups.')
param enableBudget bool = true

@description('Monthly budget amount in the billing currency of the subscription.')
@minValue(10)
param budgetAmount int = 100

@description('Optional e-mail addresses for budget alerts. Subscription Owners are always notified.')
param budgetContactEmails array = []

@description('First day of the budget period (must be the first day of a month).')
param budgetStartDate string = utcNow('yyyy-MM-01')

var tags = {
  'azd-env-name': environmentName
  workload: 'foundry-browser-automation-demo'
  'cost-center': 'demo'
}
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var platformResourceGroupName = 'rg-${environmentName}'

resource platformResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: platformResourceGroupName
  location: location
  tags: tags
}

resource foundryResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' existing = {
  name: foundryResourceGroupName
}

module foundryLookup 'modules/foundry-lookup.bicep' = {
  name: 'foundry-lookup'
  scope: foundryResourceGroup
  params: {
    foundryAccountName: foundryAccountName
    foundryProjectName: foundryProjectName
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  scope: platformResourceGroup
  params: {
    location: location
    tags: tags
    logAnalyticsName: 'log-${resourceToken}'
    applicationInsightsName: 'appi-${resourceToken}'
    dailyCapGb: logAnalyticsDailyCapGb
  }
}

module playwright 'modules/playwright.bicep' = {
  name: 'playwright'
  scope: platformResourceGroup
  params: {
    location: playwrightLocation
    tags: tags
    workspaceName: 'pww${resourceToken}'
    localAuth: playwrightLocalAuth
    foundryProjectPrincipalId: foundryLookup.outputs.projectPrincipalId
    developerPrincipalId: principalId
    developerPrincipalType: principalType
  }
}

module foundryWiring 'modules/foundry-wiring.bicep' = {
  name: 'foundry-wiring'
  scope: foundryResourceGroup
  params: {
    foundryAccountName: foundryAccountName
    foundryProjectName: foundryProjectName
    browserAutomationConnectionName: browserAutomationConnectionName
    playwrightWorkspaceId: playwright.outputs.workspaceId
    playwrightDataplaneUri: playwright.outputs.dataplaneUri
    applicationInsightsId: monitoring.outputs.applicationInsightsId
    applicationInsightsConnectionString: monitoring.outputs.applicationInsightsConnectionString
    developerPrincipalId: principalId
    developerPrincipalType: principalType
  }
}

module demoSite 'modules/demo-site.bicep' = {
  name: 'demo-site'
  scope: platformResourceGroup
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    logAnalyticsWorkspaceName: monitoring.outputs.logAnalyticsName
    minReplicas: demoSiteMinReplicas
    exists: demoSiteExists
  }
}

// One budget per start month (budget start dates cannot be moved, so a new month gets a new budget).
#disable-next-line use-stable-resource-identifiers
resource budget 'Microsoft.Consumption/budgets@2023-11-01' = if (enableBudget) {
  name: 'budget-${environmentName}-${replace(substring(budgetStartDate, 0, 7), '-', '')}'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
    }
    filter: {
      dimensions: {
        name: 'ResourceGroupName'
        operator: 'In'
        values: [
          platformResourceGroupName
          foundryResourceGroupName
        ]
      }
    }
    notifications: {
      actual50: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactRoles: [ 'Owner' ]
        contactEmails: budgetContactEmails
      }
      actual90: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 90
        thresholdType: 'Actual'
        contactRoles: [ 'Owner' ]
        contactEmails: budgetContactEmails
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Forecasted'
        contactRoles: [ 'Owner' ]
        contactEmails: budgetContactEmails
      }
    }
  }
  dependsOn: [
    platformResourceGroup
  ]
}

// Outputs are written to the azd environment (.azure/<env>/.env).
output AZURE_PLATFORM_RESOURCE_GROUP string = platformResourceGroup.name
output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.applicationInsightsConnectionString
output AZURE_APPLICATION_INSIGHTS_NAME string = monitoring.outputs.applicationInsightsName
output AZURE_LOG_ANALYTICS_WORKSPACE_NAME string = monitoring.outputs.logAnalyticsName
output PLAYWRIGHT_WORKSPACE_ID string = playwright.outputs.workspaceId
output PLAYWRIGHT_WORKSPACE_NAME string = playwright.outputs.workspaceName
output PLAYWRIGHT_DATAPLANE_URI string = playwright.outputs.dataplaneUri
output PLAYWRIGHT_BROWSER_ENDPOINT string = playwright.outputs.browserEndpoint
output BROWSER_AUTOMATION_CONNECTION_NAME string = browserAutomationConnectionName
output BROWSER_AUTOMATION_PROJECT_CONNECTION_ID string = foundryWiring.outputs.browserAutomationConnectionId
output DEMO_SITE_REGISTRY_ENDPOINT string = demoSite.outputs.registryLoginServer
output DEMO_SITE_URL string = demoSite.outputs.url
output DEMO_SITE_HOST string = demoSite.outputs.host
output BUDGET_NAME string = enableBudget ? budget.name : ''
