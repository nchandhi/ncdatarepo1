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
from datetime import datetime
from common.database.fabric_sqldb_service import run_query_and_return_json_params, run_nonquery_params

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
        if user_id:
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
            if user_id:
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
        
    async def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        """
        Deletes a conversation and its messages from the database if the user has access.

        Args:
            user_id (str): The ID of the authenticated user.
            conversation_id (str): The ID of the conversation to delete.

        Returns:
            bool: True if the conversation was deleted successfully, False otherwise.
        """
        try:
            # cosmos_conversation_client = self.init_cosmosdb_client()

            # Fetch conversation to ensure it exists and belongs to the user
            # conversation = await cosmos_conversation_client.get_conversation(user_id, conversation_id)
            
            if user_id is None:
                logger.warning(f"User ID is None, cannot delete conversation {conversation_id}.")
                return False
            
            params = (user_id, conversation_id)

            query = f"SELECT userId, conversation_id FROM hst_conversations where userId = ?  and conversation_id = ?"
            conversation = await run_query_and_return_json_params(query, params) 
            if not conversation:
                logger.warning(f"Conversation {conversation_id} not found.")
                return False
            if conversation["userId"] != user_id:
                logger.warning(
                    f"User {user_id} does not have permission to delete {conversation_id}.")
                return False

            # Delete associated messages first (if applicable)
            query_m = f"DELETE FROM hst_conversation_messages where userId = ?  and conversation_id = ?"
            await run_nonquery_params(query_m, params)            

            # await cosmos_conversation_client.delete_messages(conversation_id, user_id)

            # Delete the conversation itself
            query_m = f"DELETE FROM hst_conversations where userId = ?  and conversation_id = ?"
            await run_nonquery_params(query_m, params) 

            # await cosmos_conversation_client.delete_conversation(user_id, conversation_id)

            logger.info(f"Successfully deleted conversation {conversation_id}.")
            return True

        except Exception as e:
            logger.exception(f"Error deleting conversation {conversation_id}: {e}")
            return False

    async def delete_all_conversations(self, user_id: str) -> bool:
        """
        Deletes all conversations and its messages from the database if the user has access.

        Args:
            user_id (str): The ID of the authenticated user.

        Returns:
            bool: True if the conversations were deleted successfully, False otherwise.
        """
        try:
            if user_id is None:
                logger.warning(f"User ID is None, cannot delete conversations.")
                return False

            # Delete all associated messages
            query_m = f"DELETE FROM hst_conversation_messages where userId = ?"
            await run_nonquery_params(query_m, (user_id,))

            # Delete all conversations
            query_c = f"DELETE FROM hst_conversations where userId = ?"
            await run_nonquery_params(query_c, (user_id,))

            logger.info(f"Successfully deleted all conversations for user {user_id}.")
            return True

        except Exception as e:
            logger.exception(f"Error deleting all conversations for user {user_id}: {e}")
            return False
        
    async def rename_conversation(self, user_id: str, conversation_id, title) -> bool:
        """
        Renames the title of a conversation for a given user.

        Args:
            user_id (str): The ID of the authenticated user.    
            conversation_id (str): The ID of the conversation to rename.
            title (str): The new title for the conversation.

        Returns:
            bool: True if the title was updated successfully, False otherwise.
        """
        try:
            if not conversation_id:
                raise ValueError("No conversation_id found")

            if user_id is None:
                logger.warning(f"User ID is None, cannot rename title of the conversation {conversation_id}.")
                return False
        
            if title is None:
                logger.warning(f"Title is None, cannot rename title of the conversation {conversation_id}.")
                return False
        
            query = f"SELECT userId, conversation_id FROM hst_conversations where userId = ?  and conversation_id = ?"
            conversation = await run_query_and_return_json_params(query, (user_id, conversation_id)) 
            if not conversation:
                logger.warning(f"Conversation {conversation_id} not found.")
                return False
            if conversation["userId"] != user_id:
                logger.warning(
                    f"User {user_id} does not have permission to update title of conversation {conversation_id}.")
                return False
            
            # Update the title of the conversation 
            query_t = f"UPDATE hst_conversations SET title = ? WHERE userId = ?  and conversation_id = ?"
            await run_nonquery_params(query_t, (title, user_id, conversation_id))

            logger.info(f"Successfully updated title of conversation {conversation_id} to '{title}'.")
            return True  
        except Exception as e:
            logger.exception(f"Error updating title of conversation {conversation_id} to '{title}': {e}")
            return False    

    async def generate_title(self, conversation_messages):
        title_prompt = (
            "Summarize the conversation so far into a 4-word or less title. "
            "Do not use any quotation marks or punctuation. "
            "Do not include any other commentary or description."
        )

        messages = [{"role": msg["role"], "content": msg["content"]}
                    for msg in conversation_messages if msg["role"] == "user"]
        messages.append({"role": "user", "content": title_prompt})

        try:
            azure_openai_client = self.init_openai_client()
            response = await azure_openai_client.chat.completions.create(
                model=self.azure_openai_deployment_name,
                messages=messages,
                temperature=1,
                max_tokens=64,
            )
            return response.choices[0].message.content
        except Exception:
            logger.error("Error generating title")
            return messages[-2]["content"]

    async def create_conversation( self, user_id, title="", conversation_id=str(uuid.uuid4())):
        # utcNow = datetime.now(datetime.timezone.utc).isoformat()
        utcNow = datetime.utcnow().isoformat()
        query = f"INSERT INTO hst_conversations (userId, conversation_id, title, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?)"
        params = (user_id, conversation_id, title, utcNow, utcNow)
        resp = await run_nonquery_params(query, params)
        return resp
            
    async def create_message(self, uuid, conversation_id, user_id, input_message: dict):
        message = {
            "id": uuid,
            "type": "message",
            "userId": user_id,
            "createdAt": datetime.utcnow().isoformat(),
            "updatedAt": datetime.utcnow().isoformat(),
            "conversationId": conversation_id,
            "role": input_message["role"],
            "content": input_message,
        }

        if self.enable_message_feedback:
            message["feedback"] = ""

        query = (
            "INSERT INTO hst_conversation_messages ("
            "userId, "
            "conversation_id, "
            "role, "
            "content_id, "
            "content_date, "
            "content_role, "
            "content_text, "
            "content_citations, "
            "feedback, "
            "createdAt, "
            "updatedAt"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = (user_id, conversation_id, role, content_id, content_date, content_role, content_text, content_citations, feedback, createdAt, updatedAt)
        resp = await run_nonquery_params(query, params)

        # resp = await self.container_client.upsert_item(message)
        if resp:
            # update the parent conversations's updatedAt field with the current message's createdAt datetime value
            conversation = await self.get_conversation(user_id, conversation_id)
            if not conversation:
                return "Conversation not found"
            conversation["updatedAt"] = message["createdAt"]
            await self.upsert_conversation(conversation)
            return resp
        else:
            return False
            
    async def add_conversation(self, user_id: str, request_json: dict):
        try:
            conversation_id = request_json.get("conversation_id")
            messages = request_json.get("messages", [])

            history_metadata = {}

            #AVJ if not conversation_id:
            #     title = await self.generate_title(messages)
            #     conversation_dict = await create_conversation(user_id, title)
            #     conversation_id = conversation_dict["id"]
            #     history_metadata["title"] = title
            #     history_metadata["date"] = conversation_dict["createdAt"]

            # if messages and messages[-1]["role"] == "user":
            #     created_message = await create_message(conversation_id, user_id, messages[-1])
            #     if created_message == "Conversation not found":
            #         raise ValueError(
            #             f"Conversation not found for ID: {conversation_id}")
            # else:
            #     raise ValueError("No user message found")

            request_body = {
                "messages": messages, "history_metadata": {
                    "conversation_id": conversation_id}}
            return await complete_chat_request(request_body)
        except Exception:
            logger.exception("Error in add_conversation")
            raise  