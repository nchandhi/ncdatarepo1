import json
import logging
import os
import struct
import uuid
from datetime import datetime, date
from typing import Tuple, Any

from openai import AsyncAzureOpenAI
import pyodbc
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential, get_bearer_token_provider
from azure.monitor.events.extension import track_event
from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from chat import adjust_processed_data_dates
from auth.auth_utils import get_authenticated_user_details

router = APIRouter()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Check if the Application Insights Instrumentation Key is set in the environment variables
instrumentation_key = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if instrumentation_key:
    # Configure Application Insights if the Instrumentation Key is found
    configure_azure_monitor(connection_string=instrumentation_key)
    logging.info("Historyfab API: Application Insights configured with the provided Instrumentation Key")
else:
    # Log a warning if the Instrumentation Key is not found
    logging.warning("Historyfab API: No Application Insights Instrumentation Key found. Skipping configuration")

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

# Configuration variables
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT_MODEL = os.getenv("AZURE_OPENAI_DEPLOYMENT_MODEL")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_RESOURCE = os.getenv("AZURE_OPENAI_RESOURCE")

def track_event_if_configured(event_name: str, event_data: dict):
    """
    Track an event with Application Insights if configured.
    
    Args:
        event_name (str): The name of the event to track.
        event_data (dict): The data to associate with the event.
    """
    instrumentation_key = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if instrumentation_key:
        track_event(event_name, event_data)
    else:
        logging.warning("Skipping track_event for %s as Application Insights is not configured", event_name)


async def get_fabric_db_connection():
    """
    Get a connection to the SQL database.
    
    Returns:
        Connection: Database connection object, or None if connection fails.
    """
    app_env = os.getenv("APP_ENV", "prod").lower()
    database = os.getenv("FABRIC_SQLDB_DATABASE")
    server = os.getenv("FABRIC_SQLDB_SERVER")
    driver = "{ODBC Driver 17 for SQL Server}"
    fabric_sqldb_connection_string = os.getenv("FABRIC_SQLDB_CONNECTION_STRING", "")

    try:
        # logging.info("FABRIC-SQL-app_env: %s" % app_env)
        # Set up the connection
        conn=None
        connection_string = ""
        if app_env == 'dev':
            async with AzureCliCredential() as credential:
                token = await credential.get_token("https://database.windows.net/.default")
                # logging.info("FABRIC-SQL-TOKEN: %s" % token.token)
                token_bytes = token.token.encode("utf-16-LE")
                token_struct = struct.pack(
                    f"<I{len(token_bytes)}s",
                    len(token_bytes),
                    token_bytes
                )
                # Format token for ODBC: interleave nulls and prefix length
                # exptoken = ''.join([c + '\x00' for c in token.token])  # little-endian UTF-16-like
                # token_struct = struct.pack("=I", len(exptoken)) + exptoken.encode("utf-8")

                SQL_COPT_SS_ACCESS_TOKEN = 1256
                connection_string = f"DRIVER={driver};SERVER={server};DATABASE={database};"  
                conn = pyodbc.connect( connection_string, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})              
        else:
            connection_string = fabric_sqldb_connection_string
            conn = pyodbc.connect(connection_string)

        # logging.info("FABRIC-SQL-connection_string: %s" % connection_string)        
        # logging.info("FABRIC-SQL-User: %s" % conn.getinfo(pyodbc.SQL_USER_NAME))
        # logging.info("FABRIC-SQL:Successfully Connected to Fabric SQL Database")
        return conn
    except pyodbc.Error as e:
        logging.info("FABRIC-SQL:Failed to connect Fabric SQL Database: %s", e)
        return None

async def run_query_and_return_json(sql_query: str):
    """
    Execute SQL query and return results as JSON string.
    
    Args:
        sql_query (str): The SQL query to execute.
        
    Returns:
        str: JSON string containing query results, or None if an error occurs.
    """
    # Connect to the database    
    conn = await get_fabric_db_connection()
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(sql_query)

        # Extract column names
        columns = [desc[0] for desc in cursor.description]

        # Fetch and convert rows to list of dicts
        result = []
        for row in cursor.fetchall():
            row_dict = {}
            for col_name, value in zip(columns, row):
                # Convert datetime/date to ISO format for JSON
                if isinstance(value, (datetime, date)):
                    row_dict[col_name] = value.isoformat()
                else:
                    row_dict[col_name] = value
            result.append(row_dict)

        # logging.info("FABRIC-SQL-JSON-QUERY: %s" % sql_query)
        # logging.info("FABRIC-SQL-JSONRESULT: %s" % result)

        # Return JSON string
        return json.dumps(result, indent=2)
    except Exception as e:
        logging.error("Error executing SQL query: %s", e)
        return None
    finally:
        if cursor:
            cursor.close()
        conn.close()

async def run_query_and_return_json_params(sql_query, params: Tuple[Any, ...] = ()):
    """
    Execute parameterized SQL query and return results as JSON string.
    
    Args:
        sql_query (str): The SQL query to execute with parameter placeholders.
        params (Tuple[Any, ...]): Parameters to bind to the query.
        
    Returns:
        str: JSON string containing query results, or None if an error occurs.
    """
    # Connect to the database
    conn = await get_fabric_db_connection()
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(sql_query, params)

        # Extract column names
        columns = [desc[0] for desc in cursor.description]

        # Fetch and convert rows to list of dicts
        result = []
        for row in cursor.fetchall():
            row_dict = {}
            for col_name, value in zip(columns, row):
                # Convert datetime/date to ISO format for JSON
                if isinstance(value, (datetime, date)):
                    row_dict[col_name] = value.isoformat()
                else:
                    row_dict[col_name] = value
            result.append(row_dict)

        # logging.info("FABRIC-SQLDBService-Param-JSON-QUERY: %s" % sql_query)
        # logging.info("FABRIC-SQLDBService-Param-JSON-RESULT: %s" % result)
           
        return json.dumps(result, indent=2)
    except Exception as e:
        logging.error("Error executing SQL query: %s", e)
        return None
    finally:
        if cursor:
            cursor.close()
        conn.close()

async def run_nonquery_params(sql_query, params: Tuple[Any, ...] = ()):
    """
    Execute a SQL non-query operation like DELETE, INSERT, or UPDATE.
    
    Args:
        sql_query (str): The SQL query to execute with parameter placeholders.
        params (Tuple[Any, ...]): Parameters to bind to the query.
        
    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    conn = await get_fabric_db_connection()
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(sql_query, params)
        conn.commit()

        # logging.info("FABRIC-SQL-QUERY: %s" % sql_query)

        return True
    except Exception as e:
        logging.error("Error executing SQL query: %s", e)
        return False
    finally:
        if cursor:
            cursor.close()
        conn.close()

async def run_query_params(sql_query, params: Tuple[Any, ...] = ()):
    """
    Execute parameterized SQL query and return results as list of dictionaries.
    
    Args:
        sql_query (str): The SQL query to execute with parameter placeholders.
        params (Tuple[Any, ...]): Parameters to bind to the query.
        
    Returns:
        list: List of dictionaries containing query results, or None if an error occurs.
    """
    # Connect to the database    
    conn = await get_fabric_db_connection()
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(sql_query, params)

        # Extract column names
        columns = [desc[0] for desc in cursor.description]

        # Fetch and convert rows to list of dicts
        result = []
        for row in cursor.fetchall():
            row_dict = {}
            for col_name, value in zip(columns, row):
                # Convert datetime/date to ISO format for JSON
                if isinstance(value, (datetime, date)):
                    row_dict[col_name] = value.isoformat()
                else:
                    row_dict[col_name] = value
            result.append(row_dict)

        # logging.info("FABRIC-SQLDBService-Param-QUERY: %s" % sql_query)
        # logging.info("FABRIC-SQLDBService-Param-RESULT: %s" % result)
            
        return result
    except Exception as e:
        logging.error("Error executing SQL query: %s", e)
        return None
    finally:
        if cursor:
            cursor.close()
        conn.close()

# Configuration variable
USE_CHAT_HISTORY_ENABLED = os.getenv("USE_CHAT_HISTORY_ENABLED", "true").lower() == "true"

async def get_conversations(user_id, limit, sort_order="DESC", offset=0):
    """
    Retrieve conversations for a specific user with pagination and sorting.
    
    Args:
        user_id (str): The ID of the user whose conversations to retrieve.
        limit (int): Maximum number of conversations to return.
        sort_order (str): Sort order for conversations ("DESC" or "ASC").
        offset (int): Number of conversations to skip for pagination.
        
    Returns:
        list: List of conversation dictionaries.
    
    Raises:
        Exception: If an error occurs during conversation retrieval.
    """
    try:
        query = ""
        params = ()
        if user_id:
            query = f"SELECT conversation_id, title FROM hst_conversations where userId = ? order by updatedAt {sort_order}"
            params = (user_id,)
        else: # If no user_id is provided, return all conversations -- This is for local testing purposes
            query = f"SELECT conversation_id, title FROM hst_conversations ORDER BY updatedAt {sort_order}"
            params = ()
        
        result = await run_query_params(query, params)
        return result 
    except Exception:
        logger.exception("Error in get_conversation")
        raise

async def get_conversation_messages(user_id: str, conversation_id: str):
    """
    Retrieve all messages for a specific conversation.
    
    Args:
        user_id (str): The ID of the user requesting the messages.
        conversation_id (str): The ID of the conversation to retrieve.
        
    Returns:
        list: List of message dictionaries with deserialized citations, or None if an error occurs.
    """
    try: 
        if not conversation_id:
            logger.warning("No conversation_id found, cannot retrieve conversation messages.")
            return None
        
        query = ""
        params = ()
        if user_id:
            query = "SELECT role, content, citations, feedback FROM hst_conversation_messages where userId = ? and conversation_id = ?"
            params = (user_id, conversation_id)
        else: # If no user_id is provided, return all conversation messages -- This is for local testing purposes
            query = "SELECT role, content, citations, feedback FROM hst_conversation_messages where conversation_id = ?"
            params = (conversation_id,)

        result = await run_query_params(query, params)
        # Process the result to deserialize citations
        processed_result = []
        for message in result:
            processed_message = dict(message)
            # Deserialize citations from JSON string back to list
            if processed_message.get("citations"):
                try:
                    processed_message["citations"] = json.loads(processed_message["citations"])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("Failed to deserialize citations: %s", e)
                    processed_message["citations"] = []
            else:
                processed_message["citations"] = []
            processed_result.append(processed_message)
        
        return processed_result
    except Exception:
        logger.exception(
            "Error retrieving conversation %s for user %s", conversation_id, user_id)
        return None
        
async def delete_conversation(user_id: str, conversation_id: str) -> bool:
    """
    Delete a specific conversation and all its messages for a user.
    
    Args:
        user_id (str): The ID of the user who owns the conversation.
        conversation_id (str): The ID of the conversation to delete.
        
    Returns:
        bool: True if the conversation was successfully deleted, False otherwise.
    """
    try:
        if not conversation_id:
            logger.warning("No conversation_id found, cannot delete conversation.")
            return False
                   
        if user_id is None:
            logger.warning("User ID is None, cannot delete conversation %s.", conversation_id)
            return False            

        query = "SELECT userId, conversation_id FROM hst_conversations where conversation_id = ?"
        conversation = await run_query_params(query, (conversation_id,)) 
        # logger.info(f"FABRIC-DELETED-Retrieved conversation: {conversation}")
        # Check if the conversation exists 
        if not conversation or len(conversation) == 0:
            logger.warning("Conversation %s not found.", conversation_id)
            return False    
       
        # If the userId in the conversation does not match the user_id, deny access
        if conversation and conversation[0]["userId"] != user_id:
            logger.warning(
                "User %s does not have permission to delete %s.", user_id, conversation_id)
            return False
        # Prepare parameters for deletion
        params = (user_id, conversation_id)
        # Delete associated messages first (if applicable)
        query_m = "DELETE FROM hst_conversation_messages where userId = ?  and conversation_id = ?"
        await run_nonquery_params(query_m, params)            

        # Delete the conversation itself
        query_m = "DELETE FROM hst_conversations where userId = ?  and conversation_id = ?"
        await run_nonquery_params(query_m, params) 

        logger.info("Successfully deleted conversation %s.", conversation_id)
        return True

    except Exception as e:
        logger.exception("Error deleting conversation %s: %s", conversation_id, e)
        return False

async def delete_all_conversations(user_id: str) -> bool:
    """
    Delete all conversations and messages for a specific user.
    
    Args:
        user_id (str): The ID of the user whose conversations should be deleted.
        
    Returns:
        bool: True if all conversations were successfully deleted, False otherwise.
    """
    try:
        if user_id is None:
            logger.warning("User ID is None, cannot delete conversations.")
            return False

        # Delete all associated messages
        query_m = "DELETE FROM hst_conversation_messages WHERE userId = ?"
        messages_result = await run_nonquery_params(query_m, (user_id,))

        # Delete all conversations
        query_c = "DELETE FROM hst_conversations WHERE userId = ?"
        conversations_result = await run_nonquery_params(query_c, (user_id,))

        # Verify deletion was successful
        if messages_result is False or conversations_result is False:
            logger.error("Failed to delete all conversations for user %s", user_id)
            return False

        logger.info("Successfully deleted all conversations for user %s.", user_id)
        return True

    except Exception as e:
        logger.exception("Error deleting all conversations for user %s: %s", user_id, e)
        return False
        
async def rename_conversation(user_id: str, conversation_id, title) -> bool:
    """
    Update the title of a specific conversation.
    
    Args:
        user_id (str): The ID of the user who owns the conversation.
        conversation_id (str): The ID of the conversation to rename.
        title (str): The new title for the conversation.
        
    Returns:
        bool: True if the conversation was successfully renamed, False otherwise.
    """
    try:
        logger.info("Renaming conversation %s for user %s to '%s'", conversation_id, user_id, title)
        if not conversation_id:
            raise ValueError("No conversation_id found")

        if user_id is None:
            logger.warning("User ID is None, cannot rename title of the conversation %s.", conversation_id)
            return False
    
        if title is None:
            logger.warning("Title is None, cannot rename title of the conversation %s.", conversation_id)
            return False
    
        query = "SELECT userId, conversation_id FROM hst_conversations where conversation_id = ?"
        conversation = await run_query_params(query, (conversation_id,)) 

         # Check if the conversation exists 
        if not conversation or len(conversation) == 0:
            logger.warning("Conversation %s not found.", conversation_id)
            return False    
       
        # Check if the user has permission to delete it
        if conversation and conversation[0]["userId"] != user_id:
            logger.warning(
                "User %s does not have permission to delete %s.", user_id, conversation_id)
            return False
        
        # Update the title of the conversation 
        query_t = "UPDATE hst_conversations SET title = ? WHERE userId = ?  and conversation_id = ?"
        await run_nonquery_params(query_t, (title, user_id, conversation_id))

        logger.info("Successfully updated title of conversation %s to '%s'.", conversation_id, title)
        return True  
    except Exception as e:
        logger.exception("Error updating title of conversation %s to '%s': %s", conversation_id, title, e)
        return False

def init_openai_client():
    """
    Initialize and return an Azure OpenAI client.
    
    Returns:
        AsyncAzureOpenAI: Configured Azure OpenAI client instance.
    """
    user_agent = "GitHubSampleWebApp/AsyncAzureOpenAI/1.0.0"

    try:
        if not AZURE_OPENAI_ENDPOINT and not AZURE_OPENAI_RESOURCE:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_RESOURCE is required")

        endpoint = AZURE_OPENAI_ENDPOINT or f"https://{AZURE_OPENAI_RESOURCE}.openai.azure.com/"
        ad_token_provider = None

        logger.debug("Using Azure AD authentication for OpenAI")
        ad_token_provider = get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")

        if not AZURE_OPENAI_DEPLOYMENT_MODEL:
            raise ValueError("AZURE_OPENAI_MODEL is required")

        return AsyncAzureOpenAI(
            api_version=AZURE_OPENAI_API_VERSION,
            azure_ad_token_provider=ad_token_provider,
            default_headers={"x-ms-useragent": user_agent},
            azure_endpoint=endpoint,
        )
    except Exception:
        logger.exception("Failed to initialize Azure OpenAI client")
        raise    

async def generate_title(conversation_messages):
    """
    Generate a concise title for a conversation using Azure OpenAI service.
    
    Args:
        conversation_messages (list): List of messages in the conversation.

    Returns:
        str: A 4-word or less title summarizing the conversation.
    """
    title_prompt = (
        "Summarize the conversation so far into a 4-word or less title. "
        "Do not use any quotation marks or punctuation. "
        "Do not include any other commentary or description."
    )

    messages = [{"role": msg["role"], "content": msg["content"]}
                for msg in conversation_messages if msg["role"] == "user"]
    messages.append({"role": "user", "content": title_prompt})

    try:
        azure_openai_client = init_openai_client()
        response = await azure_openai_client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_MODEL,
            messages=messages,
            temperature=1,
            max_tokens=64,
        )
        return response.choices[0].message.content
    except Exception:
        logger.error("Error generating title")
        return messages[-2]["content"]

async def create_conversation(user_id, title="", conversation_id=None):
    """
    Create a new conversation or return existing one if it already exists.
    
    Args:
        user_id (str): The ID of the user creating the conversation.
        title (str): The title for the conversation. Defaults to empty string.
        conversation_id (str): The ID for the conversation. Generated if None.
        
    Returns:
        bool: True if conversation was created successfully, existing conversation if it already exists.
    
    Raises:
        Exception: If an error occurs during conversation creation.
    """
    try:
        # logger.info(f"FABRIC-create_conversation: user {user_id} with title '{title}' and conversation_id '{conversation_id}'")

        if not user_id:
            logger.warning("No User ID found, cannot create conversation.")
            return None

        if not conversation_id:
            logger.warning("No conversation_id found, generating a new one.")
            conversation_id = str(uuid.uuid4())

        # Check if conversation already exists
        query = "SELECT * FROM hst_conversations where conversation_id = ?"
        existing_conversation = await run_query_params(query, (conversation_id,))
        if existing_conversation and len(existing_conversation) > 0:
            logger.info("Conversation with ID %s already exists.", conversation_id)
            return existing_conversation
        
        # utc_now = datetime.now(datetime.timezone.utc).isoformat()
        utc_now = datetime.utcnow().isoformat()
        query = "INSERT INTO hst_conversations (userId, conversation_id, title, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?)"
        params = (user_id, conversation_id, title, utc_now, utc_now)
        resp = await run_nonquery_params(query, params)
        # logger.info("Created conversation with ID: %s", conversation_id)
        return resp
    except Exception:
        logger.exception("Error in create_conversation")
        raise  
        
async def create_message(uuid, conversation_id, user_id, input_message: dict):
    """
    Create a new message in a conversation.
    
    Args:
        uuid (str): Unique identifier for the message.
        conversation_id (str): The ID of the conversation to add the message to.
        user_id (str): The ID of the user creating the message.
        input_message (dict): Dictionary containing message data including role, content, and citations.
        
    Returns:
        bool: True if the message was created successfully, False otherwise.
    
    Raises:
        Exception: If an error occurs during message creation.
    """
    try:
        # logger.info(f"FABRIC-create_message: user {user_id} with conversation_id '{conversation_id}' and input_message: {input_message}")
        if not user_id:
            logger.warning("No User ID found, cannot create message.")
            return None

        if not conversation_id:
            logger.warning("No conversation_id found, cannot create conversation message.")
            return None
        
        # Ensure the conversation exists
        query = "SELECT * FROM hst_conversations where conversation_id = ?"
        exist_conversation = await run_query_params(query, (conversation_id,))
        if not exist_conversation or len(exist_conversation) == 0:
            logger.error("Conversation not found for ID: %s", conversation_id)
            return None
        
        # query = f"SELECT * FROM hst_conversations where conversation_id = ?"
        # conversation = await run_query_and_return_json_params(query, (conversation_id,))
        # if not conversation:
        #     logger.error(f"Conversation not found for ID: {conversation_id}")
        #     return None
        
        # logger.info(f"FABRIC-UPDATED-create_message-conversation_id: {conversation_id}")
       
        utc_now = datetime.utcnow().isoformat()
        # if self.enable_message_feedback:
        #     message["feedback"] = "" 
        # todo
        feedback = ""
        
        # Extract citations from input_message
        citations_json = ""
        if "citations" in input_message and input_message["citations"]:
            # Convert citations list to JSON string for storage
            try:
                citations_json = json.dumps(input_message["citations"])
            except (TypeError, ValueError) as e:
                logger.warning("Failed to serialize citations: %s", e)
                citations_json = ""
        
        query = (
            "INSERT INTO hst_conversation_messages ("
            "userId, "
            "conversation_id, "
            "role, "
            "content_id, "
            "content, "
            "citations, "
            "feedback, "
            "createdAt, "
            "updatedAt"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = (user_id, conversation_id, input_message["role"], input_message["id"],
                  input_message["content"], citations_json, feedback, utc_now, utc_now)
        resp = await run_nonquery_params(query, params)
        # logger.info("FABRIC-Created conversation status: %s, conversation_id: %s, message ID: %s, Content: %s",
        #             resp, conversation_id, input_message["id"], input_message["content"])            
        if resp:
            # Update the conversation's updatedAt timestamp
            query_t = "UPDATE hst_conversations SET updatedAt = ? WHERE conversation_id = ?"
            resp = await run_nonquery_params(query_t, (utc_now, conversation_id))

            return resp
        else:
            return False
    except Exception:
        logger.exception("Error in create_message")
        raise  
   
async def update_conversation(user_id: str, request_json: dict):
    """
    Update conversation with new messages or create new conversation if it doesn't exist.
    
    Args:
        user_id (str): The ID of the user updating the conversation.
        request_json (dict): Dictionary containing conversation_id and messages to add.
        
    Returns:
        dict: Dictionary containing conversation id, title, and updatedAt timestamp, or None if update fails.
    
    Raises:
        HTTPException: If validation fails or required messages are not found.
        Exception: If an error occurs during conversation update.
    """
    try:
        conversation_id = request_json.get("conversation_id")
        messages = request_json.get("messages", [])

        if not user_id:
            logger.warning("No User ID found, cannot update conversation.")
            return None

        # conversation = None 
        query = "SELECT * FROM hst_conversations where conversation_id = ?"
        conversation = await run_query_params(query, (conversation_id,))

        # logger.info(f"FABRIC-UPDATED-Retrieved conversation: {conversation}")
        
        if not conversation or len(conversation) == 0:
            title = await generate_title(messages)
            conversationCreated = await create_conversation(user_id=user_id, conversation_id=conversation_id, title=title)
            # logger.info(f"FABRIC-UPDATED-created conversation: {conversationCreated}")
        
        # Format the incoming message object in the "chat/completions" messages format then write it to the
        # conversation history 
        # logger.info(f"FABRIC-UPDATED-conversation_id before creating message: {conversation_id}")
        messages = request_json["messages"]
        if len(messages) > 0 and messages[0]["role"] == "user":
            user_message = next(
                (
                    message
                    for message in reversed(messages)
                    if message["role"] == "user"
                ),
                None,
            )
            createdMessageValue = await create_message(
                uuid=str(uuid.uuid4()),
                conversation_id=conversation_id,
                user_id=user_id,
                input_message=user_message,
            )
           
            if not createdMessageValue:
                logger.warning("Conversation not found for ID: %s", conversation_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Conversation not found")
        else:
            logger.warning("No user message found in request")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User message not found")

        # Format the incoming message object in the "chat/completions" messages format
        # then write it to the conversation history
        messages = request_json["messages"]
        if len(messages) > 0 and messages[-1]["role"] == "assistant":
            if len(messages) > 1 and messages[-2].get("role", None) == "tool":
                # write the tool message first
                await create_message(
                    uuid=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    user_id=user_id,
                    input_message=messages[-2],
                )
            # write the assistant message
            await create_message(
                uuid=messages[-1]["id"],
                conversation_id=conversation_id,
                user_id=user_id,
                input_message=messages[-1],
            )
        else:
            logger.warning("No assistant message found in request")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assistant message not found")                
        
        queryReturn = "SELECT * FROM hst_conversations where conversation_id = ?"
        conversationUpdated = await run_query_params(queryReturn, (conversation_id,))

        logger.info("FABRIC-UPDATED-conversationUpdated: %s", conversationUpdated)
        if conversationUpdated and len(conversationUpdated) >0:
            return {
                "id":  conversationUpdated[0].get("conversation_id"),
                "title": conversationUpdated[0].get("title"),
                "updatedAt": conversationUpdated[0].get("updatedAt")}
        else:
            return None
        
    except Exception:
        logger.exception("Error in update_conversation")
        raise


@router.get("/list")
async def list_conversations(
    request: Request,
    offset: int = Query(0, alias="offset"),
    limit: int = Query(25, alias="limit")
):
    """
    List conversations for authenticated user with pagination.
    
    Args:
        request (Request): FastAPI request object containing authentication headers.
        offset (int): Number of conversations to skip for pagination.
        limit (int): Maximum number of conversations to return.
        
    Returns:
        JSONResponse: Response containing list of conversations or error message.
    
    Raises:
        HTTPException: If authentication fails or validation errors occur.
    """
    try:
        await adjust_processed_data_dates()
        
        authenticated_user = get_authenticated_user_details(
            request_headers=request.headers)
        user_id = authenticated_user["user_principal_id"]

        logger.info("Historyfab list-API: user_id: %s, offset: %s, limit: %s", user_id, offset, limit)

        # Get conversations
        conversations = await get_conversations(user_id, offset=offset, limit=limit)
        # logging.info("FABRIC-API-list-Conv: %s" % conversations)
        if user_id:            
            track_event_if_configured("ConversationsListed", {
                "user_id": user_id,
                "offset": offset,
                "limit": limit,
                "conversation_count": len(conversations)
            })

        return JSONResponse(content=conversations, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Exception in /historyfab/list: %s", str(e))
        span = trace.get_current_span()
        if span is not None:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
        return JSONResponse(content={"error": "An internal error has occurred!"}, status_code=500)

@router.get("/read")
async def get_conversation_messages_endpoint(request: Request, id: str = Query(...)):
    """
    Get messages for a specific conversation.
    
    Args:
        request (Request): FastAPI request object containing authentication headers.
        id (str): The conversation ID to retrieve messages for.
        
    Returns:
        JSONResponse: Response containing conversation messages or error message.
    
    Raises:
        HTTPException: If authentication fails, conversation not found, or validation errors occur.
    """
    try:
        authenticated_user = get_authenticated_user_details(
            request_headers=request.headers)
        user_id = authenticated_user["user_principal_id"]
       
        conversation_id = id

        if not conversation_id:
            if user_id:
                track_event_if_configured("ReadConversationValidationError", {
                    "error": "conversation_id is required",
                    "user_id": user_id
                })
            raise HTTPException(status_code=400, detail="conversation_id is required")

        # Get conversation message details
        conversationMessages = await get_conversation_messages(user_id, conversation_id)
        logger.info("Historyfab read-API-conversationMessages: conversationMessages: %s", conversationMessages)
        # if not conversationMessages:
        if not conversationMessages or len(conversationMessages) == 0:
            if user_id:
                track_event_if_configured("ReadConversationNotFound", {
                    "user_id": user_id,
                    "conversation_id": conversation_id
                })
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} was not found. It either does not exist or the user does not have access to it."
            )
        
        if user_id:
            track_event_if_configured("ConversationRead", {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "message_count": len(conversationMessages)
            })       
        return JSONResponse(
            content={
                "conversation_id": conversation_id,
                "messages": conversationMessages},
            status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Exception in /historyfab/read: %s", str(e))
        span = trace.get_current_span()
        if span is not None:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
        return JSONResponse(content={"error": "An internal error has occurred!"}, status_code=500)
    
@router.delete("/delete")
async def delete_conversation_endpoint(request: Request, id: str = Query(...)):
    """
    Delete a specific conversation and its messages.
    
    Args:
        request (Request): FastAPI request object containing authentication headers.
        id (str): The conversation ID to delete.
        
    Returns:
        JSONResponse: Response indicating success or failure.
    
    Raises:
        HTTPException: If authentication fails, conversation not found, or user lacks permission.
    """
    try:
        # Get the user ID from request headers
        authenticated_user = get_authenticated_user_details(
            request_headers=request.headers)
        user_id = authenticated_user["user_principal_id"]
        
        conversation_id = id
        if not conversation_id:
            track_event_if_configured("DeleteConversationValidationError", {
                "error": "conversation_id is missing",
                "user_id": user_id
            })
            raise HTTPException(status_code=400, detail="conversation_id is required")

        # Delete conversation using HistoryService
        deleted = await delete_conversation(user_id, conversation_id)
        if deleted:
            if user_id:
                track_event_if_configured("ConversationDeleted", {
                    "user_id": user_id,
                    "conversation_id": conversation_id
                })
            return JSONResponse(
                content={
                    "message": "Successfully deleted conversation and messages",
                    "conversation_id": conversation_id},
                status_code=200,
            )
        else:
            if user_id:
                track_event_if_configured("DeleteConversationNotFound", {
                    "user_id": user_id,
                    "conversation_id": conversation_id
                })
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found or user does not have permission to delete.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Exception in /historyfab/delete: %s", str(e))
        span = trace.get_current_span()
        if span is not None:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
        return JSONResponse(content={"error": "An internal error has occurred!"}, status_code=500)
    
@router.delete("/delete_all")
async def delete_all_conversations_endpoint(request: Request):
    """
    Delete all conversations for authenticated user.
    
    Args:
        request (Request): FastAPI request object containing authentication headers.
        
    Returns:
        JSONResponse: Response indicating success or failure.
    
    Raises:
        HTTPException: If authentication fails or no conversations found.
    """
    try:
        # Get the user ID from request headers
        authenticated_user = get_authenticated_user_details(
            request_headers=request.headers)
        user_id = authenticated_user["user_principal_id"]

        if not user_id:
            track_event_if_configured("DeleteAllConversationsValidationError", {
                "error": "user_id is missing",
                "user_id": user_id
            })
            raise HTTPException(status_code=400, detail="user_id is required")
        # Get all user conversations
        conversations = await get_conversations(user_id, offset=0, limit=None)
        if not conversations:
            track_event_if_configured("DeleteAllConversationsNotFound", {
                "user_id": user_id
            })
            raise HTTPException(status_code=404,
                                detail=f"No conversations for {user_id} were found")

        # Delete all conversations
        deleted = await delete_all_conversations(user_id)
        if deleted:
            if user_id:
                track_event_if_configured("AllConversationsDeleted", {
                    "user_id": user_id,
                    "deleted_count": len(conversations)
                }) 
            return JSONResponse(
                content={
                    "message": f"Successfully deleted all conversations for user {user_id}"},
                status_code=200,
            )
        else:
            if user_id:
                track_event_if_configured("DeleteAllConversationsNotFound", {
                    "user_id": user_id
                })
            raise HTTPException(
                status_code=404,
                detail=f"Conversation not found for user {user_id}")
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Exception in /historyfab/delete_all: %s", str(e))
        span = trace.get_current_span()
        if span is not None:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
        return JSONResponse(content={"error": "An internal error has occurred!"}, status_code=500)
    
@router.post("/rename")
async def rename_conversation_endpoint(request: Request):
    """
    Rename a conversation's title.
    
    Args:
        request (Request): FastAPI request object containing authentication headers and JSON body with conversation_id and title.
        
    Returns:
        JSONResponse: Response indicating success or failure.
    
    Raises:
        HTTPException: If authentication fails, validation errors occur, or conversation not found.
    """
    try:
        authenticated_user = get_authenticated_user_details(
            request_headers=request.headers)
        user_id = authenticated_user["user_principal_id"]

        # Parse request body
        request_json = await request.json()
        conversation_id = request_json.get("conversation_id")
        title = request_json.get("title")
        
        if not conversation_id:
            if user_id:
                track_event_if_configured("RenameConversationValidationError", {
                    "error": "conversation_id is required",
                    "user_id": user_id
                })
            raise HTTPException(status_code=400, detail="conversation_id is required")
        if not title:
            if user_id:
                track_event_if_configured("RenameConversationValidationError", {
                    "error": "title is required",
                    "user_id": user_id
                })
            raise HTTPException(status_code=400, detail="title is required")

        rename_result = await rename_conversation(user_id, conversation_id, title)

        if rename_result:
            if user_id:
                track_event_if_configured("ConversationRenamedTitle", {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "new_title": title
                }) 
            return JSONResponse(
                content={
                    "message": f"Successfully renamed title of conversation {conversation_id} to title '{title}'"},
                status_code=200,
            )
        else:
            if user_id:
                track_event_if_configured("ConversationRenamedTitleNotFound", {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "new_title": title
                })
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found or user does not have permission to rename.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Exception in /historyfab/rename: %s", str(e))
        span = trace.get_current_span()
        if span is not None:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
        return JSONResponse(content={"error": "An internal error has occurred!"}, status_code=500)
 
@router.post("/update")
async def update_conversation_endpoint(request: Request):
    """
    Update conversation with new messages.
    
    Args:
        request (Request): FastAPI request object containing authentication headers and JSON body with conversation data.
        
    Returns:
        JSONResponse: Response containing updated conversation details or error message.
    
    Raises:
        HTTPException: If authentication fails or validation errors occur.
    """
    try:
        authenticated_user = get_authenticated_user_details(
            request_headers=request.headers)
        user_id = authenticated_user["user_principal_id"]
        
        # Parse request body
        request_json = await request.json()
        conversation_id = request_json.get("conversation_id")
        # logging.info("FABRIC-fab-update_conversation-request_json: %s" % request_json)
        if not conversation_id:
            raise HTTPException(status_code=400, detail="No conversation_id found")

        # Call HistoryService to update conversation
        update_response = await update_conversation(user_id, request_json)

        if not update_response:
            if user_id:
                track_event_if_configured("ConversationUpdated", {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "title": update_response["title"]
            })
            raise HTTPException(status_code=500, detail="Failed to update conversation")            

        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "title": update_response["title"],
                    "date": update_response["updatedAt"],
                    "conversation_id": update_response["id"],
                },
            },
            status_code=200,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Exception in /historyfab/update: %s", str(e))
        span = trace.get_current_span()
        if span is not None:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
        return JSONResponse(content={"error": "An internal error has occurred!"}, status_code=500)