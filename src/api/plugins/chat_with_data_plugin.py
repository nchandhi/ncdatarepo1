"""Plugin for handling chat interactions with data sources using Azure OpenAI and Azure AI Search.

This module provides functions for:
- Responding to greetings and general questions.
- Generating SQL queries and fetching results from a database.
- Answering questions using call transcript data from Azure AI Search.
"""

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
