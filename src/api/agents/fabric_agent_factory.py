# from azure.identity import DefaultAzureCredential
# from azure.ai.agents.models import FabricTool
# from azure.ai.projects import AIProjectClient
# from agents.agent_factory_base import BaseAgentFactory
# import logging

# logging.basicConfig(level=logging.INFO)

# class FabricAgentFactory(BaseAgentFactory):
#     """Factory class for creating fabric agents with Microsoft Fabric integration."""

#     @classmethod
#     async def create_agent(cls, config):
#         """
#         Asynchronously creates a fabric agent using Microsoft Fabric and registers it
#         with the provided project configuration.

#         Args:
#             config: Configuration object containing Azure project and fabric connection settings.

#         Returns:
#             dict: A dictionary containing the created agent and the project client.
#         """
#         try:
#             print("FABRIC-AGENT-FACTORY: Starting agent creation process...")
            
#             project_client = AIProjectClient(
#                 endpoint=config.ai_project_endpoint,
#                 credential=DefaultAzureCredential(),
#             )

#             # Find fabric connection by looking for fabric_dataagent type
#             fabric_connection_id = None
#             for connection in project_client.connections.list():
#                 # print(f"FABRIC-AGENT-FACTORY: Connection: {connection.name}, metadata: {connection.metadata}")
#                 if connection.metadata and connection.metadata.get('type') == 'fabric_dataagent' and connection.name == config.fabric_connection_name:
#                     fabric_connection_id = connection.id
#                     break
            
#             if not fabric_connection_id:
#                 raise ValueError("No Fabric connection found with type 'fabric_dataagent'")

#             # Initialize the Fabric tool with the connection ID
#             fabric = FabricTool(connection_id=fabric_connection_id)
#             # print("FABRIC-CustomerSalesKernel-fabrictool created", flush=True)
            
#             instructions = '''- Purpose: Analyze customer information.
#                     - Use this to highlight customer details.
#                     - ✅ Example queries the Fabric tool can answer:
#                         - What is the total number of customers?
#                         - how many sales orders?
#                         - How many products?'''

#             # Create agent WITHOUT the 'with' statement to keep the client open
#             agents_client = project_client.agents
#             agent = agents_client.create_agent(
#                 model='gpt-4o-mini',
#                 name=f"DA-ChatWithFabricAgent-{config.solution_name}",
#                 instructions=instructions,
#                 tools=fabric.definitions,
#             )

#             print(f"FABRIC-CustomerSalesKernel-Created Agent, ID: %s" % agent.id, flush=True)

#             return {
#                 "agent": agent,
#                 "client": project_client  # Return the open client for later use
#             }
            
#         except Exception as e:
#             logging.error(f"FABRIC-AGENT-FACTORY: Error creating FabricAgentFactory agent: {type(e).__name__}: {str(e)}")
#             raise

#     @classmethod
#     async def _delete_agent_instance(cls, agent_wrapper: dict):
#         """
#         Asynchronously deletes the specified agent instance from the Azure AI project.

#         Args:
#             agent_wrapper (dict): A dictionary containing the 'agent' and the corresponding 'client'.
#         """
#         try:
#             # print(f"FABRIC-AGENT-FACTORY: Deleting FabricAgentFactory agent with ID: {agent_wrapper['agent'].id}")
#             # Close the client properly when deleting
#             try:
#                 agent_wrapper["client"].agents.delete_agent(agent_wrapper["agent"].id)
#             finally:
#                 # Close the client to clean up resources
#                 if hasattr(agent_wrapper["client"], 'close'):
#                     agent_wrapper["client"].close()
#         except Exception as e:
#             logging.error(f"FABRIC-AGENT-FACTORY: Error deleting agent: {e}")