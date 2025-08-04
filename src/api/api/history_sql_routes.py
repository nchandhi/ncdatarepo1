import logging
import os
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
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

        logger.info(f"Historyfab list-API: user_id: {user_id}, offset: {offset}, limit: {limit}")

        # Get conversations
        conversations = await history_service.get_conversations(user_id, offset=offset, limit=limit)
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
async def get_conversation_messages(request: Request, id: str = Query(...)):
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
        conversationMessages = await history_service.get_conversation_messages(user_id, conversation_id)
        logger.info(f"Historyfab read-API-conversationMessages: conversationMessages: {conversationMessages}")
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
async def delete_conversation(request: Request, id: str = Query(...)):
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
        deleted = await history_service.delete_conversation(user_id, conversation_id)
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
async def delete_all_conversations(request: Request):
    try:
        # Get the user ID from request headers
        authenticated_user = get_authenticated_user_details(
            request_headers=request.headers)
        user_id = authenticated_user["user_principal_id"]

        # Get all user conversations
        conversations = await history_service.get_conversations(user_id, offset=0, limit=None)
        if not conversations:
            track_event_if_configured("DeleteAllConversationsNotFound", {
                "user_id": user_id
            })
            raise HTTPException(status_code=404,
                                detail=f"No conversations for {user_id} were found")

        # Delete all conversations
        deleted = await history_service.delete_all_conversations(user_id)
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
async def rename_conversation(request: Request):
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

        rename_conversation = await history_service.rename_conversation(user_id, conversation_id, title)

        if rename_conversation:
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
async def update_conversation(request: Request):
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
        update_response = await history_service.update_conversation(user_id, request_json)

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
