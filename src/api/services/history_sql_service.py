import logging
import uuid
from typing import Optional
from fastapi import HTTPException, status
from openai import AsyncAzureOpenAI
from common.config.config import Config
from common.database.cosmosdb_service import CosmosConversationClient
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from helpers.chat_helper import complete_chat_request
from datetime import datetime
from common.database.fabric_sqldb_service import run_query_and_return_json_params, run_nonquery_params, run_query_params

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
                query = f"SELECT role, content, citations, feedback FROM hst_conversation_messages where userId = ? and conversation_id = ?"
                params = (user_id, conversation_id)
            else:
                query = f"SELECT role, content, citations, feedback FROM hst_conversation_messages where conversation_id = ?"
                params = (conversation_id,)

            result = await run_query_params(query, params)   

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

    async def create_conversation( self, user_id, title="", conversation_id=None):
        try:
            logger.info(f"FABRIC-create_conversation: user {user_id} with title '{title}' and conversation_id '{conversation_id}'")

            if not user_id:
                logger.warning(f"No User ID found, cannot create conversation.")
                return None

            if not conversation_id:
                logger.warning(f"No conversation_id found, generating a new one.")
                conversation_id = str(uuid.uuid4())

            # Check if conversation already exists
            query = f"SELECT * FROM hst_conversations where conversation_id = ?"
            existing_conversation = await run_query_params(query, (conversation_id,))
            if existing_conversation and len(existing_conversation) > 0:
                logger.info(f"Conversation with ID {conversation_id} already exists.")
                return existing_conversation
            
            # utcNow = datetime.now(datetime.timezone.utc).isoformat()
            utcNow = datetime.utcnow().isoformat()
            query = f"INSERT INTO hst_conversations (userId, conversation_id, title, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?)"
            params = (user_id, conversation_id, title, utcNow, utcNow)
            resp = await run_nonquery_params(query, params)
            logger.info("Created conversation with ID: %s", conversation_id)
            return resp
        except Exception:
            logger.exception("Error in create_conversation")
            raise  
            
    async def create_message(self, uuid, conversation_id, user_id, input_message: dict):
        try:
            logger.info(f"FABRIC-create_message: user {user_id} with conversation_id '{conversation_id}' and input_message: {input_message}")
            if not user_id:
                logger.warning(f"No User ID found, cannot create message.")
                return None

            if not conversation_id:
                logger.warning(f"No conversation_id found, cannot create message.")
                return None
            
            # Ensure the conversation exists
            query = f"SELECT * FROM hst_conversations where conversation_id = ?"
            conversation = await run_query_and_return_json_params(query, (conversation_id,))
            if not conversation:
                logger.error(f"Conversation not found for ID: {conversation_id}")
                return None
            
            logger.info(f"FABRIC-UPDATED-create_message-conversation_id: {conversation_id}")
           
            utcNow = datetime.utcnow().isoformat()
            # if self.enable_message_feedback:
            #     message["feedback"] = "" 
            # todo
            feedback = ""
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
                      input_message["content"], "", feedback, utcNow, utcNow)
            resp = await run_nonquery_params(query, params)
            logger.info("FABRIC-Created conversation status: %s, conversation_id: %s, message ID: %s, Content: %s",
                        resp, conversation_id, input_message["id"], input_message["content"])
            # resp = await self.container_client.upsert_item(message)
            if resp:
                # Update the conversation's updatedAt timestamp
                query_t = f"UPDATE hst_conversations SET updatedAt = ? WHERE conversation_id = ?"
                resp =await run_nonquery_params(query_t, (utcNow, conversation_id))

                return resp
            else:
                return False
        except Exception:
            logger.exception("Error in create_message")
            raise  
            
    # async def add_conversation(self, user_id: str, request_json: dict):
    #     try:
    #         conversation_id = request_json.get("conversation_id")
    #         messages = request_json.get("messages", [])

    #         history_metadata = {}

    #         if not conversation_id:
    #             title = await self.generate_title(messages)
    #             conversation_dict = await self.create_conversation(user_id, title)
    #             conversation_id = conversation_dict["id"]
    #             history_metadata["title"] = title
    #             history_metadata["date"] = conversation_dict["createdAt"]

    #         if messages and messages[-1]["role"] == "user":
    #             created_message = await self.create_message(conversation_id=conversation_id, user_id=user_id, input_message=messages[-1])
    #             if not created_message:
    #                 raise ValueError(
    #                     f"Conversation not found for ID: {conversation_id}")
    #         else:
    #             raise ValueError("No user message found")

    #         request_body = {
    #             "messages": messages, "history_metadata": {
    #                 "conversation_id": conversation_id}}
    #         return await complete_chat_request(request_body)
    #     except Exception:
    #         logger.exception("Error in add_conversation")
    #         raise  

    async def update_conversation(self, user_id: str, request_json: dict):
        try:
            conversation_id = request_json.get("conversation_id")
            messages = request_json.get("messages", [])

            if not user_id:
                logger.warning(f"No User ID found, cannot update conversation.")
                return None

            # conversation = None 
            query = f"SELECT * FROM hst_conversations where conversation_id = ?"
            conversation = await run_query_params(query, (conversation_id,))

            # logger.info(f"FABRIC-UPDATED-Retrieved conversation: {conversation}")
            
            if not conversation or len(conversation) == 0:
                title = await self.generate_title(messages)
                conversation = await self.create_conversation(user_id=user_id, conversation_id=conversation_id, title=title)
                # logger.info(f"FABRIC-UPDATED-created conversation: {conversation}")
            
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
                createdMessageValue = await self.create_message(
                    uuid=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    user_id=user_id,
                    input_message=user_message,
                )
                # if createdMessageValue == "Conversation not found":
                if not createdMessageValue:
                    logger.error(f"Conversation not found for ID: {conversation_id}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Conversation not found")
            else:
                logger.error("No user message found in request")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User message not found")

            # Format the incoming message object in the "chat/completions" messages format
            # then write it to the conversation history
            messages = request_json["messages"]
            if len(messages) > 0 and messages[-1]["role"] == "assistant":
                if len(messages) > 1 and messages[-2].get("role", None) == "tool":
                    # write the tool message first
                    await self.create_message(
                        uuid=str(uuid.uuid4()),
                        conversation_id=conversation_id,
                        user_id=user_id,
                        input_message=messages[-2],
                    )
                # write the assistant message
                await self.create_message(
                    uuid=messages[-1]["id"],
                    conversation_id=conversation_id,
                    user_id=user_id,
                    input_message=messages[-1],
                )
            else:
                logger.error("No assistant message found in request")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Assistant message not found")                
            
            queryReturn = f"SELECT * FROM hst_conversations where conversation_id = ?"
            conversationUpdated = await run_query_params(queryReturn, (conversation_id,))

            logger.info(f"FABRIC-UPDATED-conversationUpdated: {conversationUpdated}")
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