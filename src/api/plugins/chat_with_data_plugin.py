"""Plugin for handling chat interactions with data sources using Azure OpenAI and Azure AI Search.

This module provides functions for:
- Responding to greetings and general questions.
- Generating SQL queries and fetching results from a database.
- Answering questions using call transcript data from Azure AI Search.
"""

import logging
import re
from typing import Annotated, Dict, Any
import ast

from semantic_kernel.functions.kernel_function_decorator import kernel_function
from azure.ai.agents.models import (
    ListSortOrder,
    MessageRole,
    RunStepToolCallDetails)

from common.database.sqldb_service import execute_sql_query
from common.config.config import Config
from agents.search_agent_factory import SearchAgentFactory
from agents.sql_agent_factory import SQLAgentFactory

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import FabricTool, ListSortOrder

class ChatWithDataPlugin:
    """Plugin for handling chat interactions with data using various AI agents."""

    def __init__(self):
        config = Config()
        self.azure_openai_deployment_model = config.azure_openai_deployment_model
        self.ai_project_endpoint = config.ai_project_endpoint
        self.azure_ai_search_endpoint = config.azure_ai_search_endpoint
        self.azure_ai_search_api_key = config.azure_ai_search_api_key
        self.azure_ai_search_connection_name = config.azure_ai_search_connection_name
        self.azure_ai_search_index = config.azure_ai_search_index
        self.use_ai_project_client = config.use_ai_project_client

    @kernel_function(name="ChatWithSQLDatabase",
                     description="Provides quantified results from the database.")
    async def get_sql_response(
            self,
            input: Annotated[str, "the question"]
    ):
        """
        Executes a SQL generation agent to convert a natural language query into a T-SQL query,
        executes the SQL, and returns the result.

        Args:
            input (str): Natural language question to be converted into SQL.

        Returns:
            str: SQL query result or an error message if failed.
        """

        query = input
        try:
            agent_info = await SQLAgentFactory.get_agent()
            agent = agent_info["agent"]
            project_client = agent_info["client"]

            thread = project_client.agents.threads.create()

            project_client.agents.messages.create(
                thread_id=thread.id,
                role=MessageRole.USER,
                content=query,
            )

            run = project_client.agents.runs.create_and_process(
                thread_id=thread.id,
                agent_id=agent.id
            )

            if run.status == "failed":
                print(f"Run failed: {run.last_error}")
                return "Details could not be retrieved. Please try again later."

            sql_query = ""
            messages = project_client.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
            for msg in messages:
                if msg.role == MessageRole.AGENT and msg.text_messages:
                    sql_query = msg.text_messages[-1].text.value
                    break
            sql_query = sql_query.replace("```sql", '').replace("```", '').strip()
            answer = await execute_sql_query(sql_query)
            answer = answer[:20000] if len(answer) > 20000 else answer

            # Clean up
            project_client.agents.threads.delete(thread_id=thread.id)

        except Exception:
            answer = 'Details could not be retrieved. Please try again later.'

        return answer

    @kernel_function(name="ChatWithCallTranscripts", description="Provides summaries or detailed explanations from the search index.")
    async def get_answers_from_calltranscripts(
            self,
            question: Annotated[str, "the question"]
    ):
        """
        Uses Azure AI Search agent to answer a question based on indexed call transcripts.

        Args:
            question (str): The user's query.

        Returns:
            dict: A dictionary with the answer and citation metadata.
        """

        answer: Dict[str, Any] = {"answer": "", "citations": []}
        agent = None

        try:
            agent_info = await SearchAgentFactory.get_agent()
            agent = agent_info["agent"]
            project_client = agent_info["client"]

            thread = project_client.agents.threads.create()

            project_client.agents.messages.create(
                thread_id=thread.id,
                role=MessageRole.USER,
                content=question,
            )

            run = project_client.agents.runs.create_and_process(
                thread_id=thread.id,
                agent_id=agent.id,
                tool_choice={"type": "azure_ai_search"}
            )

            if run.status == "failed":
                print(f"Run failed: {run.last_error}")
            else:
                def convert_citation_markers(text):
                    def replace_marker(match):
                        parts = match.group(1).split(":")
                        if len(parts) == 2 and parts[1].isdigit():
                            new_index = int(parts[1]) + 1
                            return f"[{new_index}]"
                        return match.group(0)

                    return re.sub(r'【(\d+:\d+)†source】', replace_marker, text)

                for run_step in project_client.agents.run_steps.list(thread_id=thread.id, run_id=run.id):
                    if isinstance(run_step.step_details, RunStepToolCallDetails):
                        for tool_call in run_step.step_details.tool_calls:
                            output_data = tool_call['azure_ai_search']['output']
                            tool_output = ast.literal_eval(output_data) if isinstance(output_data, str) else output_data
                            urls = tool_output.get("metadata", {}).get("get_urls", [])
                            titles = tool_output.get("metadata", {}).get("titles", [])

                            for i, url in enumerate(urls):
                                title = titles[i] if i < len(titles) else ""
                                answer["citations"].append({"url": url, "title": title})

                messages = project_client.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
                for msg in messages:
                    if msg.role == MessageRole.AGENT and msg.text_messages:
                        answer["answer"] = msg.text_messages[-1].text.value
                        answer["answer"] = convert_citation_markers(answer["answer"])
                        break
                project_client.agents.threads.delete(thread_id=thread.id)
        except Exception:
            return "Details could not be retrieved. Please try again later."
        return answer

    @kernel_function(name="ChatWithCustomerSales", description="Provides summaries or detailed explanations of customer sales.")
    async def get_answers_from_customersales(
            self,
            question: Annotated[str, "the question"]
    ):
        """
        Uses Azure AI Search agent to answer a question based on indexed call transcripts.

        Args:
            question (str): The user's query.

        Returns:
            dict: A dictionary with the answer and citation metadata.
        """

        answer: Dict[str, Any] = {"answer": "", "citations": []}
        agent = None

        try:
            print("FABRIC-CustomerSalesKernel", flush=True)
            project_client = AIProjectClient(
            endpoint= "https://aisa-dagtruot2b3qsu.services.ai.azure.com/api/projects/aifp-dagtruot2b3qsu",
            credential=DefaultAzureCredential(),)

            for connection in project_client.connections.list():
                if (connection.metadata
                    and connection.metadata.get('type') == 'fabric_dataagent' 
                    and connection.name == "myFabricDataAgentConnection"
                    ):
                    # print(f"FABRIC-CustomerSalesKernel-connection-name: {connection.name}", flush=True)
                    conn_id = connection.id
                    break

            # Initialize agent Fabric tool and add the connection ID
            fabric = FabricTool(connection_id=conn_id)
            print("FABRIC-CustomerSalesKernel-fabrictool created", flush=True)
            instructions='''- Purpose: Analyze customer information.
                            - Use this to highlight customer details.
                            - ✅ Example queries the Fabric tool can answer:
                                - What is the total number of customers?
                                - how many sales orders?
                                - How many products?'''
            # with project_client:
            agents_client = project_client.agents
            agent = agents_client.create_agent(
                model='gpt-4o-mini',
                name="my-fabric-agent",
                instructions=instructions,
                tools=fabric.definitions,
            )
            # print("FABRIC-CustomerSalesKernel-Created Agent, ID: %s" % agent.id, flush=True)

            # Create a thread for communication
            thread = project_client.agents.threads.create()
            # print("FABRIC-CustomerSalesKernel-Created thread, ID: %s" % thread.id, flush=True)
            
            # Create a message in the thread
            message = project_client.agents.messages.create(
                thread_id=thread.id,
                role=MessageRole.USER,  # Role of the message sender
                content=question,  # Message content
            )
            # print("FABRIC-CustomerSalesKernel-Created message, ID: %s" % message['id'], flush=True)           

             # Create and process an Agent run in thread with tools
            run = agents_client.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
            print("FABRIC-CustomerSalesKernel-Run finished with status: %s" % run.status, flush=True)
            if run.status == "failed":
                print("FABRIC-CustomerSalesKernel-Run failed: %s" % run.last_error, flush=True)
            else:
                # def convert_citation_markers(text):
                #     def replace_marker(match):
                #         parts = match.group(1).split(":")
                #         if len(parts) == 2 and parts[1].isdigit():
                #             new_index = int(parts[1]) + 1
                #             return f"[{new_index}]"
                #         return match.group(0)

                #     return re.sub(r'【(\d+:\d+)†source】', replace_marker, text)

                # for run_step in project_client.agents.run_steps.list(thread_id=thread.id, run_id=run.id):
                #     if isinstance(run_step.step_details, RunStepToolCallDetails):
                #         for tool_call in run_step.step_details.tool_calls:
                #             output_data = tool_call['azure_ai_search']['output']
                #             tool_output = ast.literal_eval(output_data) if isinstance(output_data, str) else output_data
                #             urls = tool_output.get("metadata", {}).get("get_urls", [])
                #             titles = tool_output.get("metadata", {}).get("titles", [])

                #             for i, url in enumerate(urls):
                #                 title = titles[i] if i < len(titles) else ""
                #                 answer["citations"].append({"url": url, "title": title})

                messages = project_client.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
                for msg in messages:
                    if msg.role == MessageRole.AGENT and msg.text_messages:
                        answer["answer"] = msg.text_messages[-1].text.value
                        # answer["answer"] = convert_citation_markers(answer["answer"])
                        break
                project_client.agents.threads.delete(thread_id=thread.id)
        except Exception as e:
            print("FABRIC-CustomerSalesKernel-Error: %s" % e, flush=True)
            return "Details could not be retrieved. Please try again later."

        print("FABRIC-CustomerSalesKernel-Answer: %s" % answer, flush=True)
        return answer