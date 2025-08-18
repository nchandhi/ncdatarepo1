from azure.identity import DefaultAzureCredential, OnBehalfOfCredential
from azure.ai.agents.models import FabricTool
from azure.ai.projects import AIProjectClient
from agents.agent_factory_base import BaseAgentFactory
import logging
from common.config.config import Config

logging.basicConfig(level=logging.INFO)

class FabricAgentFactory(BaseAgentFactory):
    """Factory class for creating fabric agents with Microsoft Fabric integration."""

    @classmethod
    async def create_agent(cls, config):
        """
        Asynchronously creates a fabric agent using Microsoft Fabric and registers it
        with the provided project configuration.

        Args:
            config: Configuration object containing Azure project and fabric connection settings.

        Returns:
            dict: A dictionary containing the created agent and the project client.
        """
        try:
            print("FABRIC-AGENT-FACTORY: Starting agent creation process...")
            credential = None
            app_env = config.app_env
            # print("FABRIC-AGENT-FACTORY-ENV: %s" % app_env, flush=True)
            # print("FABRIC-AGENT-FACTORY-client_id: %s" % config.api_client_id, flush=True)
            # print("FABRIC-AGENT-FACTORY-tenant_id: %s" % config.api_tenant_id, flush=True)
            # print("FABRIC-AGENT-FACTORY-user_assertion: %s" % Config.api_access_token, flush=True)
            print("FABRIC-AGENT-FACTORY-user_assertion: %s" % Config.api_access_token[:15], flush=True)
            if app_env == 'dev':
                credential = DefaultAzureCredential()
            else:
                credential = OnBehalfOfCredential(
                    client_id=config.api_client_id,
                    tenant_id=config.api_tenant_id,
                    client_secret=config.api_client_secret,
                    user_assertion=Config.api_access_token
                )

            project_client = AIProjectClient(
                endpoint=config.ai_project_endpoint,
                credential=credential,
            )

            # Find fabric connection by looking for fabric_dataagent type
            fabric_connection_id = None
            for connection in project_client.connections.list():
                # print(f"FABRIC-AGENT-FACTORY: Connection: {connection.name}, metadata: {connection.metadata}")
                if connection.metadata and connection.metadata.get('type') == 'fabric_dataagent' and connection.name == config.fabric_connection_name:
                    fabric_connection_id = connection.id
                    break
            
            if not fabric_connection_id:
                raise ValueError("No Fabric connection found with type 'fabric_dataagent'")

            # Initialize the Fabric tool with the connection ID
            fabric = FabricTool(connection_id=fabric_connection_id)
            # print("FABRIC-CustomerSalesKernel-fabrictool created", flush=True)
            
            instructions = '''- Purpose: Analyze customer information.
                    - Highlight key customer details.
                    - Summarize customer interactions.
                    - Provide a brief overview of policy information.
                    - Highlight claims-related information.
                    - ✅ Example queries the Fabric tool can answer:
                        - What is the total number of customers?
                        - What is the maximum premium paid by any customer?'''

            # Create agent WITHOUT the 'with' statement to keep the client open
            agents_client = project_client.agents
            agent = agents_client.create_agent(
                model='gpt-4o-mini',
                name=f"DA-ChatWithFabricAgent-{config.solution_name}",
                instructions=instructions,
                tools=fabric.definitions,
            )

            print(f"FABRIC-CustomerSalesKernel-Created Agent, ID: %s" % agent.id, flush=True)

            return {
                "agent": agent,
                "client": project_client  # Return the open client for later use
            }
            
        except Exception as e:
            logging.error(f"FABRIC-AGENT-FACTORY-ERROR: Error creating FabricAgentFactory agent: {type(e).__name__}: {str(e)}")
            raise

    @classmethod
    async def _delete_agent_instance(cls, agent_wrapper: dict):
        """
        Asynchronously deletes the specified agent instance from the Azure AI project.

        Args:
            agent_wrapper (dict): A dictionary containing the 'agent' and the corresponding 'client'.
        """
        try:
            # print(f"FABRIC-AGENT-FACTORY: Deleting FabricAgentFactory agent with ID: {agent_wrapper['agent'].id}")
            # Close the client properly when deleting
            try:
                agent_wrapper["client"].agents.delete_agent(agent_wrapper["agent"].id)
            finally:
                # Close the client to clean up resources
                if hasattr(agent_wrapper["client"], 'close'):
                    agent_wrapper["client"].close()
        except Exception as e:
            logging.error(f"FABRIC-AGENT-FACTORY: Error deleting agent: {e}")