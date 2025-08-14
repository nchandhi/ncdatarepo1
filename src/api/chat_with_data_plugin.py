"""
Plugin for chat interactions with data using AI agents.
"""

import ast
import logging
import os
import re
import struct
from typing import Annotated, Any, Dict

import pyodbc
from azure.ai.agents.models import MessageRole, ListSortOrder, RunStepToolCallDetails
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv
from semantic_kernel.functions.kernel_function_decorator import kernel_function

from agent_factory import AgentFactory, AgentType

load_dotenv()

async def get_db_connection():
    """Get a connection to the SQL database"""
    database = os.getenv("SQLDB_DATABASE")
    server = os.getenv("SQLDB_SERVER")
    username = os.getenv("SQLDB_USERNAME")
    password = os.getenv("SQLDB_PASSWORD")
    driver = "{ODBC Driver 17 for SQL Server}"
    mid_id = os.getenv("SQLDB_USER_MID")

    try:
        async with DefaultAzureCredential(managed_identity_client_id=mid_id) as credential:
            token = await credential.get_token("https://database.windows.net/.default")
            token_bytes = token.token.encode("utf-16-LE")
            token_struct = struct.pack(
                f"<I{len(token_bytes)}s",
                len(token_bytes),
                token_bytes
            )
            SQL_COPT_SS_ACCESS_TOKEN = 1256

            # Set up the connection
            connection_string = f"DRIVER={driver};SERVER={server};DATABASE={database};"
            conn = pyodbc.connect(
                connection_string, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct}
            )

            logging.info("Connected using Default Azure Credential")
            return conn
    except pyodbc.Error as e:
        logging.error("Failed with Default Credential: %s", str(e))
        conn = pyodbc.connect(
            f"DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}",
            timeout=5)

        logging.info("Connected using Username & Password")
        return conn

async def execute_sql_query(sql_query):
    """
    Executes a given SQL query and returns the result as a concatenated string.
    """
    conn = await get_db_connection()
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(sql_query)
        result = ''.join(str(row) for row in cursor.fetchall())
        return result
    except Exception as e:
        logging.error("Error executing SQL query: %s", e)
        return None
    finally:
        if cursor:
            cursor.close()
        conn.close()


class ChatWithDataPlugin:
    """Plugin for handling chat interactions with data using various AI agents."""

    def __init__(self):
        self.azure_openai_deployment_model = os.getenv("AZURE_OPENAI_DEPLOYMENT_MODEL")
        self.ai_project_endpoint = os.getenv("AI_PROJECT_ENDPOINT")
        self.azure_ai_search_endpoint = os.getenv("AZURE_AI_SEARCH_ENDPOINT")
        self.azure_ai_search_api_key = os.getenv("AZURE_AI_SEARCH_API_KEY")
        self.azure_ai_search_index = os.getenv("AZURE_AI_SEARCH_INDEX")
        self.azure_ai_search_connection_name = os.getenv("AZURE_AI_SEARCH_CONNECTION_NAME")
        self.use_ai_project_client = os.getenv("USE_AI_PROJECT_CLIENT", "False").lower() == "true"

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
            agent_info = await AgentFactory.get_agent(AgentType.SQL)
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
            agent_info = await AgentFactory.get_agent(AgentType.SEARCH)
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
        except Exception as e:
            print(f"Error in get_answers_from_calltranscripts: {e}", flush=)
            return "Details could not be retrieved. Please try again later."
        return answer