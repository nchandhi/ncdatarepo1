"""
Plugin for chat interactions with data using AI agents.
"""

import logging
import os
import struct
from typing import Dict, Any, Annotated

import pyodbc
from azure.ai.agents.models import MessageRole, ListSortOrder
from dotenv import load_dotenv
from semantic_kernel.functions.kernel_function_decorator import kernel_function
from agent_factory import AgentFactory, AgentType
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from history_sql import execute_sql_query

load_dotenv()

class ChatWithDataPlugin:
    """Plugin for handling chat interactions with data using various AI agents."""

    def __init__(self):
        self.ai_project_endpoint = os.getenv("AZURE_AI_AGENT_ENDPOINT")
        self.ai_project_api_version = os.getenv("AZURE_AI_AGENT_API_VERSION", "2025-05-01")
        self.foundry_sql_agent_id = os.getenv("AGENT_ID_SQL")

    @kernel_function(name="ChatWithSQLDatabase",
                     description="Provides quantified results, metrics, or structured data from the SQL database.")
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
            project_client = AIProjectClient(
                endpoint=self.ai_project_endpoint,
                credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),
                api_version=self.ai_project_api_version,
            )
           
            thread = project_client.agents.threads.create()

            project_client.agents.messages.create(
                thread_id=thread.id,
                role=MessageRole.USER,
                content=query,
            )

            run = project_client.agents.runs.create_and_process(
                thread_id=thread.id,
                agent_id=self.foundry_sql_agent_id, 
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

        except Exception as e:
            print(f"Fabric-SQL-Kernel-error: {e}", flush=True)
            answer = 'Details could not be retrieved. Please try again later.'

        print(f"fabric-SQL-Kernel-response: {answer}", flush=True)
        return answer

    @kernel_function(name="GenerateChartData", description="Generates Chart.js v4.4.4 compatible JSON data for data visualization requests using current and immediate previous context.")
    async def get_chart_data(
            self,
            input: Annotated[str, "The user's data visualization request along with relevant conversation history and context needed to generate appropriate chart data"],
    ):
        query = input
        query = query.strip()
        try:
            agent_info = await AgentFactory.get_agent(AgentType.CHART)
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

            chartdata = ""
            messages = project_client.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
            for msg in messages:
                if msg.role == MessageRole.AGENT and msg.text_messages:
                    chartdata = msg.text_messages[-1].text.value
                    break
            # Clean up
            project_client.agents.threads.delete(thread_id=thread.id)

        except Exception:
            chartdata = 'Details could not be retrieved. Please try again later.'
        return chartdata

    # @kernel_function(name="ChatWithCustomerSales", description="Provides summaries or detailed explanations of customer sales.")
    # async def get_answers_from_customersales(
    #         self,
    #         question: Annotated[str, "the question"]
    # ):
    #     """
    #     Uses Microsoft Fabric agent to answer a question based on customer data.

    #     Args:
    #         question (str): The user's query.

    #     Returns:
    #         dict: A dictionary with the answer and citation metadata.
    #     """
    #     answer: Dict[str, Any] = {"answer": "", "citations": []}
    #     agent = None

    #     try:            
    #         # Get the fabric agent
    #         print("FABRIC-CustomerSalesKernel", flush=True)
    #         agent_info = await AgentFactory.get_agent(AgentType.FABRIC)
    #         agent = agent_info["agent"]
    #         project_client = agent_info["client"]
    #         print("FABRIC-CustomerSalesKernel: Fabric agent retrieved successfully", flush=True)
    #         print(f"FABRIC-CustomerSalesKernel: Agent ID: {agent_info['agent'].id}", flush=True)

    #         # Create thread
    #         thread = project_client.agents.threads.create()
    #         print(f"FABRIC-CustomerSalesKernel: Thread created successfully: {thread.id}", flush=True)

    #         # Create message with the actual question
    #         project_client.agents.messages.create(
    #             thread_id=thread.id,
    #             role=MessageRole.USER,
    #             content=question,
    #         )
    #         print(f"FABRIC-CustomerSalesKernel: Message created in thread {thread.id} with question: {question}", flush=True)

    #         run = project_client.agents.runs.create_and_process(
    #             thread_id=thread.id,
    #             agent_id=agent.id
    #         )
    #         print(f"FABRIC-CustomerSalesKernel: Agent run completed with status: {run.status}")

    #         if run.status == "failed":
    #             logging.error(f"FABRIC-CustomerSalesKernel: Run failed: {run.last_error}")
    #         else:
    #             # ADD CITATION PROCESSING HERE
    #             # def convert_citation_markers(text):
    #             #     def replace_marker(match):
    #             #         content = match.group(1).strip()
    #             #         parts = content.split(":")
    #             #         if len(parts) == 2 and parts[1].isdigit():
    #             #             new_index = int(parts[1]) + 1
    #             #             return f"[{new_index}]"
    #             #         return match.group(0)
                    
    #             #     return re.sub(r'【\s*(\d+:\d+)\s*†source】', replace_marker, text)

    #             # Check the response structure
    #             # try:
    #             #     for run_step in project_client.agents.run_steps.list(thread_id=thread.id, run_id=run.id):
    #             #         print(f"FABRIC-CustomerSalesKernel: Processing run step: {run_step.id}, type: {type(run_step.step_details)}")
    #             #         if isinstance(run_step.step_details, RunStepToolCallDetails):
    #             #             for tool_call in run_step.step_details.tool_calls:
    #             #                 print(f"FABRIC-CustomerSalesKernel: Processing tool call: {tool_call}")

    #             # except Exception as run_step_error:
    #             #     logging.error(f"FABRIC-CustomerSalesKernel: Failed to process run steps: {type(run_step_error).__name__}: {run_step_error}")
    #             #     raise

    #             try:
    #                 messages = project_client.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)                    
    #                 for msg in messages:
    #                     if msg.role == MessageRole.AGENT and msg.text_messages:
    #                         raw_answer = msg.text_messages[-1].text.value
    #                         # print(f"Raw answer from agent: {raw_answer}")
    #                         # converted_answer = convert_citation_markers(raw_answer)
    #                         # print(f"Converted answer: {converted_answer}")
    #                         answer["answer"] = raw_answer
    #                         break
    #             except Exception as messages_error:
    #                 # logging.error(f"Failed to retrieve messages: {type(messages_error).__name__}: {messages_error}")
    #                 raise

    #             logging.info(f"FABRIC-CustomerSalesKernel-Thread ID: {thread.id}, Run ID: {run.id}")
    #             # project_client.agents.threads.delete(thread_id=thread.id)
                
    #         if not answer["answer"]:
    #             answer["answer"] = "I couldn't find specific information about customer sales. Please try rephrasing your question."
                
    #     except Exception as e:
    #         logging.error(f"Full error details: {repr(e)}")
    #         import traceback
    #         return {"answer": "Details could not be retrieved. Please try again later.", "citations": []}
        
    #     print(f"FABRIC-CustomerSalesKernel-Answer: %s" % answer, flush=True)
    #     return answer
