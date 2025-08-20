import os
from azure.ai.projects import AIProjectClient
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential

KEY_VAULT_NAME = 'kv_to-be-replaced'
MANAGED_IDENTITY_CLIENT_ID = 'mici_to-be-replaced'
ai_project_endpoint = 'project_endpoint_to-be-replaced'


# Initialize the AI project client
# project_client = AIProjectClient(
#     endpoint= ai_project_endpoint,
#     credential=DefaultAzureCredential(),
# )

project_client = AIProjectClient(
    endpoint= ai_project_endpoint,
    credential=ManagedIdentityCredential(client_id=MANAGED_IDENTITY_CLIENT_ID),
)

instructions='''You are a helpful assistant'''
with project_client:
    agents_client = project_client.agents
    agent = agents_client.create_agent(
        model='gpt-4o-mini',
        name="my-agent2",
        instructions=instructions
    )
    print(agent.id)
# print('12345678')