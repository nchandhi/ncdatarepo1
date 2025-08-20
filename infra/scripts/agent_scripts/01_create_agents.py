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

instructions = '''You are an assistant that helps generate valid T-SQL queries.
        Generate a valid T-SQL query for the user's request using these tables:
        1. Table: km_processed_data
            Columns: ConversationId, EndTime, StartTime, Content, summary, satisfied, sentiment, topic, keyphrases, complaint
        2. Table: processed_data_key_phrases
            Columns: ConversationId, key_phrase, sentiment
        Use accurate and semantically appropriate SQL expressions, data types, functions, aliases, and conversions based strictly on the column definitions and the explicit or implicit intent of the user query.
        Avoid assumptions or defaults not grounded in schema or context.
        Ensure all aggregations, filters, grouping logic, and time-based calculations are precise, logically consistent, and reflect the user's intent without ambiguity.
        **Always** return a valid T-SQL query. Only return the SQL query text—no explanations.'''

with project_client:
    agents_client = project_client.agents
    agent = agents_client.create_agent(
        model='gpt-4o-mini',
        name="my-DA-ChatWithSQLDbAgent-",
        instructions=instructions
    )
    print(agent.id)
# print('12345678')