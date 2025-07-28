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


@router.get("/list_table_data")
async def list_table_data(
    request: Request,
    offset: int = Query(0, alias="offset"),
    limit: int = Query(25, alias="limit")
):
    try:
        authenticated_user = get_authenticated_user_details(
            request_headers=request.headers)
        user_id = authenticated_user["user_principal_id"]

        logger.info(f"user_id: {user_id}, offset: {offset}, limit: {limit}")

        # Get table data
        table_data = await history_service.get_table_data(user_id=user_id, offset=offset, limit=limit)

        if user_id is not None:
            if not isinstance(table_data, list):
                track_event_if_configured("ListTableDataNotFound", {
                    "user_id": user_id,
                    "offset": offset,
                    "limit": limit
                })
                return JSONResponse(
                    content={
                        "error": f"No table data for {user_id} were found"},
                    status_code=404)
            track_event_if_configured("TableDataListed", {
                "user_id": user_id,
                "offset": offset,
                "limit": limit,
                "table_data_count": len(table_data)
            })
        logging.info("AVJ-FABRIC-API-RESULT: %s" % table_data)
        return JSONResponse(content=table_data, status_code=200)

    except Exception as e:
        logger.exception("Exception in /historysql/list_table_data: %s", str(e))
        span = trace.get_current_span()
        if span is not None:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
        return JSONResponse(content={"error": "An internal error has occurred!"}, status_code=500)

@router.get("/history/ensure")
async def ensure_cosmos():
    try:
        success, err = await history_service.ensure_cosmos()
        if not success:
            track_event_if_configured("CosmosDBEnsureFailed", {
                "error": err or "Unknown error occurred"
            })
            return JSONResponse(
                content={
                    "error": err or "Unknown error occurred"},
                status_code=422)
        track_event_if_configured("CosmosDBEnsureSuccess", {
            "status": "CosmosDB is configured and working"
        })

        return JSONResponse(
            content={
                "message": "CosmosDB is configured and working"},
            status_code=200)
    except Exception as e:
        logger.exception("Exception in /history/ensure: %s", str(e))
        span = trace.get_current_span()
        if span is not None:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
        cosmos_exception = str(e)

        if "Invalid credentials" in cosmos_exception:
            return JSONResponse(content={"error": "Invalid credentials"}, status_code=401)
        elif "Invalid CosmosDB database name" in cosmos_exception or "Invalid CosmosDB container name" in cosmos_exception:
            return JSONResponse(content={"error": "Invalid CosmosDB configuration"}, status_code=422)
        else:
            return JSONResponse(
                content={
                    "error": "CosmosDB is not configured or not working"},
                status_code=500)
