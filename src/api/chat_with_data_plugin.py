"""
Plugin for chat interactions with data using AI agents.
"""

import logging
import os
import struct
from typing import Annotated

import pyodbc
from azure.ai.agents.models import MessageRole, ListSortOrder
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv
from semantic_kernel.functions.kernel_function_decorator import kernel_function

from agent_factory import AgentFactory, AgentType

load_dotenv()


async def get_db_connection():
    """Get a connection to the SQL database"""
    database = os.getenv("SQLDB_DATABASE")
    server = os.getenv("SQLDB_SERVER")
    driver = "{ODBC Driver 17 for SQL Server}"
    mid_id = os.getenv("SQLDB_USER_MID")

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
