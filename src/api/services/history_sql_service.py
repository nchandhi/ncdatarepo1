import logging
import uuid
from typing import Optional
from fastapi import HTTPException, status
from openai import AsyncAzureOpenAI
from common.config.config import Config
from common.database.cosmosdb_service import CosmosConversationClient
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from helpers.chat_helper import complete_chat_request
from common.database.fabric_sqldb_service import execute_fabric_sql_query

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HistorySqlService:
    def __init__(self):
        config = Config()

        self.use_chat_history_enabled = config.use_chat_history_enabled
       
    async def get_table_data(self, user_id: str, offset: int, limit: int):
        """
        Retrieves a list of claims from the database.

        Args:
            offset (int): The number of records to skip (for pagination).
            limit (int): The maximum number of records to return.
        Returns:
            list: A list of claim objects or an empty list if none exist.
        """
        try:
            sql_query = "SELECT * from SalesLT.ProductCategory"
            #sql_query = "SELECT * from km_mined_topics"
            result = await execute_fabric_sql_query(sql_query)
           
            return result or []
        except Exception:
            logger.exception("Error retrieving fabric data")
            return []