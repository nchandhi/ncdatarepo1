@description('Specifies the location for resources.')
param solutionLocation string 

param baseUrl string
param keyVaultName string
param managedIdentityResourceId string
param managedIdentityClientId string
param projectEndpoint string
param solutionName string
param gptModelName string

resource create_agent 'Microsoft.Resources/deploymentScripts@2023-08-01' = {
  kind:'AzureCLI'
  name: 'run_agent_scripts'
  location: solutionLocation
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityResourceId}' : {}
    }
  }
  properties: {
    azCliVersion: '2.52.0'
    primaryScriptUri: '${baseUrl}infra/scripts/run_create_agent_scripts.sh' 
    arguments: '${baseUrl} ${keyVaultName} ${managedIdentityClientId} ${projectEndpoint} ${solutionName} ${gptModelName}'
    timeout: 'PT1H'
    retentionInterval: 'PT1H'
    cleanupPreference:'OnSuccess'
  }
}

output conversationAgentId string = create_agent.properties.outputs.conversationAgentId
output sqlAgentId string = create_agent.properties.outputs.sqlAgentId
output chartAgentId string = create_agent.properties.outputs.chartAgentId
