"""
Chat API module for handling chat interactions and responses.

This module provides enhanced debugging capabilities:

Environment Variables:
- DEBUG_MODE: Set to "true" to enable debug-level logging and debug endpoints
- APPLICATIONINSIGHTS_CONNECTION_STRING: Application Insights connection string
- AZURE_AI_AGENT_ENDPOINT: Azure AI agent endpoint
- AZURE_AI_AGENT_API_VERSION: Azure AI agent API version
- AGENT_ID_SQL: SQL agent ID for database queries
- AGENT_ID_CHART: Chart agent ID for data visualization

Debug Features:
- Structured logging with correlation IDs for request tracking
- Debug-level logging when DEBUG_MODE=true
- Enhanced exception handling with detailed error context
- Performance timing measurements
- Debug endpoints (only available when DEBUG_MODE=true):
  - GET /debug/status: Service status and configuration
  - GET /debug/cache: Thread cache inspection
- OpenTelemetry tracing with enhanced span context
- Comprehensive error tracking and correlation

Usage:
- Set DEBUG_MODE=true environment variable to enable detailed debugging
- Check logs for correlation IDs to trace specific requests
- Use debug endpoints for troubleshooting when needed
"""

import asyncio
import json
import logging
import os
import random
import re
import time
import uuid
from types import SimpleNamespace
from typing import Annotated, AsyncGenerator

from cachetools import TTLCache
from dotenv import load_dotenv
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

# Azure SDK
from azure.ai.agents.models import TruncationObject, MessageRole, ListSortOrder
from azure.monitor.events.extension import track_event
from azure.monitor.opentelemetry import configure_azure_monitor
from azure.ai.projects import AIProjectClient

# Semantic Kernel
from semantic_kernel.agents import AzureAIAgentThread
from semantic_kernel.exceptions.agent_exceptions import AgentException
from semantic_kernel.functions.kernel_function_decorator import kernel_function

# Azure Auth
from auth.azure_credential_utils import get_azure_credential

load_dotenv()

# Constants
HOST_NAME = "CKM"
HOST_INSTRUCTIONS = "Answer questions about call center operations"

router = APIRouter()

# Configure logging
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
log_level = logging.DEBUG if DEBUG_MODE else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

# Set explicit level for chat module logger
logger.setLevel(log_level)

# Set debug mode logging for chat module
if DEBUG_MODE:
    logger.debug("Chat module initialized in DEBUG mode")
else:
    logger.info("Chat module initialized")

# Check if the Application Insights Instrumentation Key is set in the environment variables
instrumentation_key = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if instrumentation_key:
    # Configure Application Insights if the Instrumentation Key is found
    configure_azure_monitor(connection_string=instrumentation_key)
    logging.info("Application Insights configured with the provided Instrumentation Key")
else:
    # Log a warning if the Instrumentation Key is not found
    logging.warning("No Application Insights Instrumentation Key found. Skipping configuration")

# Configure logging
logging.basicConfig(level=logging.INFO)

# Suppress INFO logs from 'azure.core.pipeline.policies.http_logging_policy'
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(
    logging.WARNING
)
logging.getLogger("azure.identity.aio._internal").setLevel(logging.WARNING)

# Suppress info logs from OpenTelemetry exporter
logging.getLogger("azure.monitor.opentelemetry.exporter.export._base").setLevel(
    logging.WARNING
)

# Enable debug logging for Azure services in DEBUG mode if needed
if DEBUG_MODE:
    logging.getLogger("azure").setLevel(logging.INFO)
    logging.getLogger("opentelemetry").setLevel(logging.INFO)


def log_debug_info(func_name: str, data: dict = None, extra_msg: str = ""):
    """Utility function to log debug information consistently."""
    if logger.isEnabledFor(logging.DEBUG):
        log_msg = f"[{func_name}] {extra_msg}"
        if data:
            log_msg += f" - Data: {data}"
        logger.debug(log_msg)


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for request tracking."""
    return str(uuid.uuid4())[:8]


class ChatWithDataPlugin:
    """Plugin for handling chat interactions with data using various AI agents."""

    def __init__(self):
        self.ai_project_endpoint = os.getenv("AZURE_AI_AGENT_ENDPOINT")
        self.ai_project_api_version = os.getenv("AZURE_AI_AGENT_API_VERSION", "2025-05-01")
        self.foundry_sql_agent_id = os.getenv("AGENT_ID_SQL")
        self.foundry_chart_agent_id = os.getenv("AGENT_ID_CHART")

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
        correlation_id = generate_correlation_id()
        query = input
        
        logger.debug(f"[{correlation_id}] Starting SQL response generation for query: {query}")
        log_debug_info("get_sql_response", {
            "correlation_id": correlation_id,
            "input_length": len(query),
            "agent_endpoint": self.ai_project_endpoint,
            "agent_id": self.foundry_sql_agent_id
        }, "SQL agent request initiated")

        try:
            from history_sql import execute_sql_query
            
            logger.debug(f"[{correlation_id}] Creating AI project client")
            project_client = AIProjectClient(
                endpoint=self.ai_project_endpoint,
                credential=get_azure_credential(),
                api_version=self.ai_project_api_version,
            )

            logger.debug(f"[{correlation_id}] Creating agent thread")
            thread = project_client.agents.threads.create()
            logger.debug(f"[{correlation_id}] Thread created with ID: {thread.id}")

            logger.debug(f"[{correlation_id}] Creating user message in thread")
            project_client.agents.messages.create(
                thread_id=thread.id,
                role=MessageRole.USER,
                content=query,
            )

            logger.debug(f"[{correlation_id}] Starting agent run")
            run = project_client.agents.runs.create_and_process(
                thread_id=thread.id,
                agent_id=self.foundry_sql_agent_id,
            )
            logger.debug(f"[{correlation_id}] Agent run completed with status: {run.status}")

            if run.status == "failed":
                error_msg = f"[{correlation_id}] Run failed: {run.last_error}"
                logger.error(error_msg)
                return "Details could not be retrieved. Please try again later."

            logger.debug(f"[{correlation_id}] Retrieving messages from thread")
            sql_query = ""
            messages = project_client.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
            for msg in messages:
                if msg.role == MessageRole.AGENT and msg.text_messages:
                    sql_query = msg.text_messages[-1].text.value
                    break
            
            sql_query = sql_query.replace("```sql", '').replace("```", '').strip()
            logger.info(f"[{correlation_id}] Generated SQL Query: {sql_query}")
            
            logger.debug(f"[{correlation_id}] Executing SQL query")
            answer_raw = await execute_sql_query(sql_query)
            
            if isinstance(answer_raw, str):
                answer = answer_raw[:20000] if len(answer_raw) > 20000 else answer_raw
                if len(answer_raw) > 20000:
                    logger.debug(f"[{correlation_id}] SQL result truncated from {len(answer_raw)} to 20000 characters")
            else:
                answer = answer_raw or ""

            logger.debug(f"[{correlation_id}] Cleaning up thread: {thread.id}")
            # Clean up
            project_client.agents.threads.delete(thread_id=thread.id)
            
            logger.info(f"[{correlation_id}] SQL response completed successfully")
            log_debug_info("get_sql_response", {
                "correlation_id": correlation_id,
                "sql_query_length": len(sql_query),
                "result_length": len(str(answer)),
                "thread_id": thread.id
            }, "SQL response generation completed")

        except Exception as e:
            error_msg = f"[{correlation_id}] Fabric-SQL-Kernel-error: {e}"
            logger.error(error_msg, exc_info=True)
            log_debug_info("get_sql_response", {
                "correlation_id": correlation_id,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }, "SQL response generation failed")
            answer = 'Details could not be retrieved. Please try again later.'

        logger.debug(f"[{correlation_id}] Returning SQL response: {answer[:100]}..." if len(str(answer)) > 100 else f"[{correlation_id}] Returning SQL response: {answer}")
        return answer

    @kernel_function(name="GenerateChartData", description="Generates Chart.js v4.4.4 compatible JSON data for data visualization requests using current and immediate previous context.")
    async def get_chart_data(
            self,
            input: Annotated[str, "The user's data visualization request along with relevant conversation history and context needed to generate appropriate chart data"],
    ):
        correlation_id = generate_correlation_id()
        query = input.strip()
        
        logger.debug(f"[{correlation_id}] Starting chart data generation for query: {query}")
        log_debug_info("get_chart_data", {
            "correlation_id": correlation_id,
            "input_length": len(query),
            "agent_endpoint": self.ai_project_endpoint,
            "chart_agent_id": self.foundry_chart_agent_id
        }, "Chart data generation request initiated")

        try:
            logger.debug(f"[{correlation_id}] Creating AI project client for chart generation")
            project_client = AIProjectClient(
                endpoint=self.ai_project_endpoint,
                credential=get_azure_credential(),
                api_version=self.ai_project_api_version,
            )

            logger.debug(f"[{correlation_id}] Creating agent thread for chart data")
            thread = project_client.agents.threads.create()
            logger.debug(f"[{correlation_id}] Chart thread created with ID: {thread.id}")

            logger.debug(f"[{correlation_id}] Creating user message in chart thread")
            project_client.agents.messages.create(
                thread_id=thread.id,
                role=MessageRole.USER,
                content=query,
            )

            logger.debug(f"[{correlation_id}] Starting chart agent run")
            run = project_client.agents.runs.create_and_process(
                thread_id=thread.id,
                agent_id=self.foundry_chart_agent_id,
            )
            logger.debug(f"[{correlation_id}] Chart agent run completed with status: {run.status}")

            if run.status == "failed":
                error_msg = f"[{correlation_id}] Chart run failed: {run.last_error}"
                logger.error(error_msg)
                return "Details could not be retrieved. Please try again later."

            logger.debug(f"[{correlation_id}] Retrieving chart messages from thread")
            chartdata = ""
            messages = project_client.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
            for msg in messages:
                if msg.role == MessageRole.AGENT and msg.text_messages:
                    chartdata = msg.text_messages[-1].text.value
                    break
            
            logger.debug(f"[{correlation_id}] Cleaning up chart thread: {thread.id}")
            # Clean up
            project_client.agents.threads.delete(thread_id=thread.id)
            
            logger.info(f"[{correlation_id}] Chart data generation completed successfully")
            log_debug_info("get_chart_data", {
                "correlation_id": correlation_id,
                "chart_data_length": len(str(chartdata)),
                "thread_id": thread.id
            }, "Chart data generation completed")

        except Exception as e:
            error_msg = f"[{correlation_id}] fabric-Chat-Kernel-error: {e}"
            logger.error(error_msg, exc_info=True)
            log_debug_info("get_chart_data", {
                "correlation_id": correlation_id,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }, "Chart data generation failed")
            chartdata = 'Details could not be retrieved. Please try again later.'

        logger.debug(f"[{correlation_id}] Returning chart data: {chartdata[:100]}..." if len(str(chartdata)) > 100 else f"[{correlation_id}] Returning chart data: {chartdata}")
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


class ExpCache(TTLCache):
    """Extended TTLCache that deletes Azure AI agent threads when items expire."""

    def __init__(self, *args, agent=None, **kwargs):
        """Initialize cache with optional agent for thread cleanup."""
        super().__init__(*args, **kwargs)
        self.agent = agent
        logger.debug(f"ExpCache initialized - maxsize: {kwargs.get('maxsize', 'unknown')}, ttl: {kwargs.get('ttl', 'unknown')}")

    def expire(self, time=None):
        """Remove expired items and delete associated Azure AI threads."""
        items = super().expire(time)
        for key, thread_id in items:
            try:
                if self.agent:
                    thread = AzureAIAgentThread(client=self.agent.client, thread_id=thread_id)
                    asyncio.create_task(thread.delete())
                    logger.info("Thread deleted (expired): %s for key: %s", thread_id, key)
                else:
                    logger.debug("Thread cleanup skipped (no agent): %s for key: %s", thread_id, key)
            except Exception as e:
                logger.error("Failed to delete expired thread for key %s (thread_id: %s): %s", key, thread_id, e)
        
        if items:
            logger.debug(f"ExpCache expired {len(items)} items")
        return items

    def popitem(self):
        """Remove item using LRU eviction and delete associated Azure AI thread."""
        key, thread_id = super().popitem()
        try:
            if self.agent:
                thread = AzureAIAgentThread(client=self.agent.client, thread_id=thread_id)
                asyncio.create_task(thread.delete())
                logger.info("Thread deleted (LRU evict): %s for key: %s", thread_id, key)
            else:
                logger.debug("Thread cleanup skipped (no agent) for LRU eviction: %s for key: %s", thread_id, key)
        except Exception as e:
            logger.error("Failed to delete LRU evicted thread for key %s (thread_id: %s): %s", key, thread_id, e)
        return key, thread_id


# async def get_db_connection():
#     """Get a connection to the SQL database"""
#     database = os.getenv("SQLDB_DATABASE")
#     server = os.getenv("SQLDB_SERVER")
#     driver = "{ODBC Driver 17 for SQL Server}"
#     mid_id = os.getenv("SQLDB_USER_MID")

#     async with AsyncDefaultAzureCredential(managed_identity_client_id=mid_id) as credential:
#         token = await credential.get_token("https://database.windows.net/.default")
#         token_bytes = token.token.encode("utf-16-LE")
#         token_struct = struct.pack(
#             f"<I{len(token_bytes)}s",
#             len(token_bytes),
#             token_bytes
#         )
#         SQL_COPT_SS_ACCESS_TOKEN = 1256

#         # Set up the connection
#         connection_string = f"DRIVER={driver};SERVER={server};DATABASE={database};"
#         conn = pyodbc.connect(
#             connection_string, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct}
#         )

#         logging.info("Connected using Default Azure Credential")
#         return conn


# async def adjust_processed_data_dates():
#     """
#     Adjusts the dates in the processed_data, km_processed_data, and processed_data_key_phrases tables
#     to align with the current date.
#     """
#     conn = await get_db_connection()
#     cursor = None
#     try:
#         cursor = conn.cursor()
#         # Adjust the dates to the current date
#         today = datetime.today()
#         cursor.execute(
#             "SELECT MAX(CAST(StartTime AS DATETIME)) FROM [dbo].[processed_data]"
#         )
#         max_start_time = (cursor.fetchone())[0]

#         if max_start_time:
#             days_difference = (today - max_start_time).days - 1
#             if days_difference != 0:
#                 # Update processed_data table
#                 cursor.execute(
#                     "UPDATE [dbo].[processed_data] SET StartTime = FORMAT(DATEADD(DAY, ?, StartTime), 'yyyy-MM-dd "
#                     "HH:mm:ss'), EndTime = FORMAT(DATEADD(DAY, ?, EndTime), 'yyyy-MM-dd HH:mm:ss')",
#                     (days_difference, days_difference)
#                 )
#                 # Update km_processed_data table
#                 cursor.execute(
#                     "UPDATE [dbo].[km_processed_data] SET StartTime = FORMAT(DATEADD(DAY, ?, StartTime), 'yyyy-MM-dd "
#                     "HH:mm:ss'), EndTime = FORMAT(DATEADD(DAY, ?, EndTime), 'yyyy-MM-dd HH:mm:ss')",
#                     (days_difference, days_difference)
#                 )
#                 # Update processed_data_key_phrases table
#                 cursor.execute(
#                     "UPDATE [dbo].[processed_data_key_phrases] SET StartTime = FORMAT(DATEADD(DAY, ?, StartTime), "
#                     "'yyyy-MM-dd HH:mm:ss')", (days_difference,)
#                 )
#                 # Commit the changes
#                 conn.commit()
#     finally:
#         if cursor:
#             cursor.close()
#         conn.close()


def track_event_if_configured(event_name: str, event_data: dict):
    """Track event to Application Insights if configured."""
    instrumentation_key = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if instrumentation_key:
        try:
            track_event(event_name, event_data)
            logger.debug(f"Event tracked: {event_name} with data keys: {list(event_data.keys())}")
        except Exception as e:
            logger.error(f"Failed to track event {event_name}: {e}")
    else:
        logger.debug(f"Skipping track_event for {event_name} as Application Insights is not configured")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Event data for {event_name}: {event_data}")


def format_stream_response(chat_completion_chunk, history_metadata, apim_request_id):
    """Format chat completion chunk into standardized response object."""
    response_obj = {
        "id": chat_completion_chunk.id,
        "model": chat_completion_chunk.model,
        "created": chat_completion_chunk.created,
        "object": chat_completion_chunk.object,
        "choices": [{"messages": []}],
        "history_metadata": history_metadata,
        "apim-request-id": apim_request_id,
    }

    if len(chat_completion_chunk.choices) > 0:
        delta = chat_completion_chunk.choices[0].delta
        if delta:
            if hasattr(delta, "context"):
                message_obj = {"role": "tool", "content": json.dumps(delta.context)}
                response_obj["choices"][0]["messages"].append(message_obj)
                return response_obj
            if delta.role == "assistant" and hasattr(delta, "context"):
                message_obj = {
                    "role": "assistant",
                    "context": delta.context,
                }
                response_obj["choices"][0]["messages"].append(message_obj)
                return response_obj
            else:
                if delta.content:
                    message_obj = {
                        "role": "assistant",
                        "content": delta.content,
                    }
                    response_obj["choices"][0]["messages"].append(message_obj)
                    return response_obj

    return {}


# Global thread cache
thread_cache = None


def get_thread_cache(agent):
    """Get or create the global thread cache."""
    global thread_cache
    if thread_cache is None:
        thread_cache = ExpCache(maxsize=1000, ttl=3600.0, agent=agent)
        logger.debug("Global thread cache created with maxsize=1000, ttl=3600.0")
    return thread_cache


async def stream_openai_text(conversation_id: str, query: str, agent) -> AsyncGenerator[str, None]:
    """
    Get a streaming text response from OpenAI.
    """
    correlation_id = generate_correlation_id()
    thread = None
    complete_response = ""
    
    logger.debug(f"[{correlation_id}] Starting stream_openai_text for conversation_id: {conversation_id}")
    log_debug_info("stream_openai_text", {
        "correlation_id": correlation_id,
        "conversation_id": conversation_id,
        "query_length": len(query) if query else 0
    }, "Stream request initiated")
    
    try:
        if not query:
            query = "Please provide a query."
            logger.debug(f"[{correlation_id}] Empty query provided, using default")

        cache = get_thread_cache(agent)
        thread_id = cache.get(conversation_id, None)
        
        logger.debug(f"[{correlation_id}] Thread cache lookup - Found: {thread_id is not None}")

        if thread_id:
            thread = AzureAIAgentThread(client=agent.client, thread_id=thread_id)
            logger.debug(f"[{correlation_id}] Using existing thread: {thread_id}")
        else:
            logger.debug(f"[{correlation_id}] No existing thread found, will create new one")

        truncation_strategy = TruncationObject(type="last_messages", last_messages=4)
        logger.debug(f"[{correlation_id}] Starting agent.invoke_stream with truncation strategy")

        response_count = 0
        async for response in agent.invoke_stream(messages=query, thread=thread, truncation_strategy=truncation_strategy):
            response_count += 1
            cache[conversation_id] = response.thread.id
            complete_response += str(response.content)
            
            if logger.isEnabledFor(logging.DEBUG) and response_count <= 5:  # Log first 5 responses
                logger.debug(f"[{correlation_id}] Stream response #{response_count}: {str(response.content)[:100]}...")
            
            yield response.content
            
        logger.debug(f"[{correlation_id}] Stream completed with {response_count} responses, total length: {len(complete_response)}")

    except RuntimeError as e:
        complete_response = str(e)
        error_msg = f"[{correlation_id}] RuntimeError in stream_openai_text: {e}"
        
        if "Rate limit is exceeded" in str(e):
            logger.error(f"{error_msg} - Rate limit exceeded")
            raise AgentException(f"Rate limit is exceeded. {str(e)}") from e
        else:
            logger.error(f"{error_msg} - Unexpected runtime error", exc_info=True)
            raise AgentException(f"An unexpected runtime error occurred: {str(e)}") from e

    except Exception as e:
        complete_response = str(e)
        error_msg = f"[{correlation_id}] Unexpected error in stream_openai_text: {e}"
        logger.error(error_msg, exc_info=True)
        log_debug_info("stream_openai_text", {
            "correlation_id": correlation_id,
            "error_type": type(e).__name__,
            "error_message": str(e),
            "conversation_id": conversation_id
        }, "Stream request failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error streaming OpenAI text") from e

    finally:
        # Provide a fallback response when no data is received from OpenAI.
        if complete_response == "":
            logger.warning(f"[{correlation_id}] No response received from OpenAI, providing fallback")
            cache = get_thread_cache(agent)
            thread_id = cache.pop(conversation_id, None)
            if thread_id is not None:
                corrupt_key = f"{conversation_id}_corrupt_{random.randint(1000, 9999)}"
                cache[corrupt_key] = thread_id
                logger.debug(f"[{correlation_id}] Moved corrupted thread to key: {corrupt_key}")
            yield "I cannot answer this question with the current data. Please rephrase or add more details."


async def stream_chat_request(request_body, conversation_id, query, agent):
    """
    Handles streaming chat requests.
    """
    correlation_id = generate_correlation_id()
    history_metadata = request_body.get("history_metadata", {})
    
    logger.debug(f"[{correlation_id}] Starting stream_chat_request for conversation: {conversation_id}")
    log_debug_info("stream_chat_request", {
        "correlation_id": correlation_id,
        "conversation_id": conversation_id,
        "query_length": len(query),
        "has_history_metadata": bool(history_metadata)
    }, "Stream chat request initiated")

    async def generate():
        chunk_count = 0
        try:
            assistant_content = ""
            logger.debug(f"[{correlation_id}] Starting text streaming")
            
            async for chunk in stream_openai_text(conversation_id, query, agent):
                chunk_count += 1
                if isinstance(chunk, dict):
                    chunk = json.dumps(chunk)  # Convert dict to JSON string
                assistant_content += str(chunk)

                if assistant_content:
                    chat_completion_chunk = {
                        "id": "",
                        "model": "",
                        "created": 0,
                        "object": "",
                        "choices": [
                            {
                                "messages": [],
                                "delta": {},
                            }
                        ],
                        "history_metadata": history_metadata,
                        "apim-request-id": "",
                    }

                    chat_completion_chunk["id"] = str(uuid.uuid4())
                    chat_completion_chunk["model"] = "rag-model"
                    chat_completion_chunk["created"] = int(time.time())
                    chat_completion_chunk["object"] = "extensions.chat.completion.chunk"
                    chat_completion_chunk["choices"][0]["messages"].append(
                        {"role": "assistant", "content": assistant_content}
                    )
                    chat_completion_chunk["choices"][0]["delta"] = {
                        "role": "assistant",
                        "content": assistant_content,
                    }

                    completion_chunk_obj = json.loads(
                        json.dumps(chat_completion_chunk),
                        object_hook=lambda d: SimpleNamespace(**d),
                    )
                    
                    if logger.isEnabledFor(logging.DEBUG) and chunk_count <= 3:  # Log first 3 chunks
                        logger.debug(f"[{correlation_id}] Yielding chunk #{chunk_count}, content length: {len(assistant_content)}")
                    
                    yield json.dumps(format_stream_response(completion_chunk_obj, history_metadata, "")) + "\n\n"
            
            logger.debug(f"[{correlation_id}] Stream completed with {chunk_count} chunks")

        except AgentException as e:
            error_message = str(e)
            retry_after = "sometime"
            if "Rate limit is exceeded" in error_message:
                match = re.search(r"Try again in (\d+) seconds", error_message)
                if match:
                    retry_after = f"{match.group(1)} seconds"
                logger.error(f"[{correlation_id}] Rate limit error: {error_message}")
                error_response = {
                    "error": f"Rate limit exceeded. Please try again after {retry_after}.",
                    "correlation_id": correlation_id
                }
                yield json.dumps(error_response) + "\n\n"
            else:
                logger.error(f"[{correlation_id}] Agent exception: {error_message}", exc_info=True)
                error_response = {
                    "error": "An error occurred. Please try again later.",
                    "correlation_id": correlation_id
                }
                yield json.dumps(error_response) + "\n\n"

        except Exception as e:
            logger.error(f"[{correlation_id}] Unexpected error in stream generation: {e}", exc_info=True)
            log_debug_info("stream_chat_request", {
                "correlation_id": correlation_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "chunks_processed": chunk_count
            }, "Stream generation failed")
            error_response = {
                "error": "An error occurred while processing the request.",
                "correlation_id": correlation_id
            }
            yield json.dumps(error_response) + "\n\n"

    return generate()


@router.get("/debug/status")
async def debug_status():
    """Debug endpoint to check the status of the chat service and its dependencies."""
    if not DEBUG_MODE:
        raise HTTPException(status_code=404, detail="Debug endpoints are only available in DEBUG mode")
    
    correlation_id = generate_correlation_id()
    logger.debug(f"[{correlation_id}] Debug status endpoint accessed")
    
    status_info = {
        "correlation_id": correlation_id,
        "timestamp": time.time(),
        "debug_mode": DEBUG_MODE,
        "environment": {
            "ai_project_endpoint": os.getenv("AZURE_AI_AGENT_ENDPOINT", "Not set"),
            "ai_project_api_version": os.getenv("AZURE_AI_AGENT_API_VERSION", "Not set"),
            "sql_agent_id": os.getenv("AGENT_ID_SQL", "Not set"),
            "chart_agent_id": os.getenv("AGENT_ID_CHART", "Not set"),
            "app_insights_configured": bool(os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"))
        },
        "cache_stats": {
            "cache_exists": thread_cache is not None,
            "cache_size": len(thread_cache) if thread_cache else 0,
            "cache_maxsize": thread_cache.maxsize if thread_cache else None,
            "cache_ttl": thread_cache.ttl if thread_cache else None
        },
        "logging": {
            "logger_level": logger.level,
            "logger_name": logger.name,
            "handlers_count": len(logger.handlers)
        }
    }
    
    logger.debug(f"[{correlation_id}] Debug status compiled successfully")
    return status_info


@router.get("/debug/cache")
async def debug_cache():
    """Debug endpoint to inspect the thread cache."""
    if not DEBUG_MODE:
        raise HTTPException(status_code=404, detail="Debug endpoints are only available in DEBUG mode")
    
    correlation_id = generate_correlation_id()
    logger.debug(f"[{correlation_id}] Debug cache endpoint accessed")
    
    if not thread_cache:
        return {
            "correlation_id": correlation_id,
            "cache_status": "not_initialized",
            "message": "Thread cache has not been initialized yet"
        }
    
    cache_info = {
        "correlation_id": correlation_id,
        "timestamp": time.time(),
        "cache_size": len(thread_cache),
        "cache_maxsize": thread_cache.maxsize,
        "cache_ttl": thread_cache.ttl,
        "cache_keys": list(thread_cache.keys()) if logger.isEnabledFor(logging.DEBUG) else "Debug level required",
        "cache_agent_type": type(thread_cache.agent).__name__ if thread_cache.agent else "No agent"
    }
    
    logger.debug(f"[{correlation_id}] Cache debug info compiled successfully")
    return cache_info
async def conversation(request: Request):
    """Handle chat requests - streaming text or chart generation based on query keywords."""
    correlation_id = generate_correlation_id()
    request_start_time = time.time()
    
    logger.debug(f"[{correlation_id}] Starting conversation endpoint")
    
    try:
        # Get the request JSON and last RAG response from the client
        request_json = await request.json()
        last_rag_response = request_json.get("last_rag_response")
        conversation_id = request_json.get("conversation_id")
        query = request_json.get("messages")[-1].get("content") if request_json.get("messages") else ""
        
        logger.info(f"[{correlation_id}] Conversation request - ID: {conversation_id}, Query length: {len(query)}")
        logger.debug(f"[{correlation_id}] Last RAG response: {last_rag_response}")
        
        log_debug_info("conversation", {
            "correlation_id": correlation_id,
            "conversation_id": conversation_id,
            "query_length": len(query),
            "has_last_rag_response": last_rag_response is not None,
            "messages_count": len(request_json.get("messages", []))
        }, "Processing conversation request")

        agent = request.app.state.orchestrator_agent
        logger.debug(f"[{correlation_id}] Retrieved orchestrator agent: {type(agent).__name__}")

        logger.debug(f"[{correlation_id}] Starting stream_chat_request")
        result = await stream_chat_request(request_json, conversation_id, query, agent)
        
        # Calculate processing time
        processing_time = time.time() - request_start_time
        logger.info(f"[{correlation_id}] Conversation completed successfully in {processing_time:.2f}s")
        
        track_event_if_configured(
            "ChatStreamSuccess",
            {
                "conversation_id": conversation_id, 
                "query": query,
                "correlation_id": correlation_id,
                "processing_time": processing_time
            }
        )
        
        return StreamingResponse(result, media_type="application/json-lines")

    except Exception as ex:
        processing_time = time.time() - request_start_time
        error_msg = f"[{correlation_id}] Error in conversation endpoint after {processing_time:.2f}s: {str(ex)}"
        logger.exception(error_msg)
        
        log_debug_info("conversation", {
            "correlation_id": correlation_id,
            "error_type": type(ex).__name__,
            "error_message": str(ex),
            "processing_time": processing_time
        }, "Conversation request failed")
        
        # Enhance OpenTelemetry span with debug info
        span = trace.get_current_span()
        if span is not None:
            span.record_exception(ex)
            span.set_status(Status(StatusCode.ERROR, str(ex)))
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("processing_time", processing_time)
            
        track_event_if_configured(
            "ChatStreamError",
            {
                "error": str(ex),
                "correlation_id": correlation_id,
                "processing_time": processing_time
            }
        )
        
        return JSONResponse(
            content={
                "error": "An internal error occurred while processing the conversation.",
                "correlation_id": correlation_id
            }, 
            status_code=500
        )
