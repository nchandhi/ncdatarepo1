import logging
import os
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from auth.auth_utils import get_authenticated_user_details
from services.history_sql_service import HistorySqlService
from common.logging.event_utils import track_event_if_configured
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

router = APIRouter()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Single instance of HistoryService (if applicable)
history_service = HistorySqlService()

@router.get("/list")
async def list_conversations(
    request: Request,
    offset: int = Query(0, alias="offset"),
    limit: int = Query(25, alias="limit")
):
    try:
        authenticated_user = get_authenticated_user_details(
            request_headers=request.headers)
        user_id = authenticated_user["user_principal_id"]

        logger.info(f"user_id: {user_id}, offset: {offset}, limit: {limit}")

        # Get conversations
        conversations = await history_service.get_conversations(user_id, offset=offset, limit=limit)
        
        if user_id is not None:
            if not isinstance(conversations, list):
                track_event_if_configured("ListConversationsNotFound", {
                    "user_id": user_id,
                    "offset": offset,
                    "limit": limit
                })
                return JSONResponse(
                    content={
                        "error": f"No conversations for {user_id} were found"},
                    status_code=404)
            track_event_if_configured("ConversationsListed", {
                "user_id": user_id,
                "offset": offset,
                "limit": limit,
                "conversation_count": len(conversations)
            })
        return JSONResponse(content=conversations, status_code=200)

    except Exception as e:
        logger.exception("Exception in /historyfab/list: %s", str(e))
        span = trace.get_current_span()
        if span is not None:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
        return JSONResponse(content={"error": "An internal error has occurred!"}, status_code=500)


@router.get("/read")
async def get_conversation_messages(request: Request, id: str = Query(...)):
    try:
        authenticated_user = get_authenticated_user_details(
            request_headers=request.headers)
        user_id = authenticated_user["user_principal_id"]
       
        conversation_id = id

        if not conversation_id:
            track_event_if_configured("ReadConversationValidationError", {
                "error": "conversation_id is required",
                "user_id": user_id
            })
            raise HTTPException(status_code=400, detail="conversation_id is required")

        # Get conversation details
        conversationMessages = await history_service.get_conversation_messages(user_id, conversation_id)
        if user_id is not None:
            if not conversationMessages:
                track_event_if_configured("ReadConversationNotFound", {
                    "user_id": user_id,
                    "conversation_id": conversation_id
                })
                raise HTTPException(
                    status_code=404,
                    detail=f"Conversation {conversation_id} was not found. It either does not exist or the user does not have access to it."
                )
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

    except Exception as e:
        logger.exception("Exception in /historyfab/read: %s", str(e))
        span = trace.get_current_span()
        if span is not None:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
        return JSONResponse(content={"error": "An internal error has occurred!"}, status_code=500)