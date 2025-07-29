import logging
import uuid
from typing import Optional
from fastapi import HTTPException, status
from openai import AsyncAzureOpenAI
from common.config.config import Config
from common.database.cosmosdb_service import CosmosConversationClient
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from helpers.chat_helper import complete_chat_request
import json
from common.database.fabric_sqldb_service import run_query_and_return_json_params

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HistorySqlService:
    def __init__(self):
        config = Config()

        self.use_chat_history_enabled = config.use_chat_history_enabled
       
    async def get_conversations(self, user_id, limit, sort_order="DESC", offset=0):
        query = ""
        params = ()
        if user_id is not None:
            query = f"SELECT conversation_id, title FROM hst_conversations where userId = ? order by updatedAt {sort_order}"
            params = (user_id,)
        else:
            query = f"SELECT conversation_id, title FROM hst_conversations ORDER BY updatedAt {sort_order}"
            params = ()
        
        result = await run_query_and_return_json_params(query, params)    

        return result 
   
    async def get_conversation_messages(self, user_id: str, conversation_id: str):
        """
        Retrieves a single conversation and its messages for a given user.

        Args:
            user_id (str): The ID of the authenticated user.
            conversation_id (str): The ID of the conversation to retrieve.

        Returns:
            JSON: The conversation object with messages or None if not found.
        """
        try: 
            query = ""
            params = ()
            if user_id is not None:
                query = f"SELECT role, content_role, content_text, content_citations, feedback FROM hst_conversation_messages where userId = ? and conversation_id = ?"
                params = (user_id, conversation_id)
            else:
                query = f"SELECT role, content_role, content_text, content_citations, feedback FROM hst_conversation_messages where conversation_id = ?"
                params = (conversation_id,)

            result = await run_query_and_return_json_params(query, params)   

            return result               
            
        except Exception:
            logger.exception(
                f"Error retrieving conversation {conversation_id} for user {user_id}")
            return None