from datetime import datetime, date
import struct
import json

# import pandas as pd
# from api.models.input_models import ChartFilters
from common.config.config import Config
import logging
from azure.identity.aio import DefaultAzureCredential
import pyodbc
from typing import Tuple, Any


async def get_fabric_db_connection():
    """Get a connection to the SQL database"""
    config = Config()

    server = config.fabric_sqldb_server
    database = config.fabric_sqldb_database
    username = config.fabric_sqldb_username
    password = config.fabric_sqldb_database # Assuming this is a mistake in the original code, it should be `fabric_sqldb_password`
    driver = config.fabric_driver
    mid_id = config.fabric_mid_id
    fabric_sqldb_connection_string = config.fabric_sqldb_connection_string
    app_env = config.app_env

    try:
        async with DefaultAzureCredential(managed_identity_client_id=mid_id) as credential:
            token = await credential.get_token("https://database.windows.net/.default")
            # logging.info("FABRIC-SQL-TOKEN: %s" % token.token)
            token_bytes = token.token.encode("utf-16-LE")
            token_struct = struct.pack(
                f"<I{len(token_bytes)}s",
                len(token_bytes),
                token_bytes
            )
            SQL_COPT_SS_ACCESS_TOKEN = 1256

            # Set up the connection
            connection_string = ""
            if app_env == 'dev':
                connection_string = f"DRIVER={driver};SERVER={server};DATABASE={database};"
            else:
                connection_string = fabric_sqldb_connection_string
            # connection_string = f"DRIVER={driver};SERVER={server};DATABASE={database};"
            conn = pyodbc.connect(
                connection_string, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct}
            )

            logging.info("Connected using Default Azure Credential")
            return conn
    except pyodbc.Error as e:
        logging.error("Failed with Default Credential: %s", str(e))
        conn = pyodbc.connect(
            f"DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}",
            timeout=5)

        logging.info("FABRIC-SQL: Connected using Username & Password")
        return conn

async def run_query_and_return_json(sql_query: str):
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
    Executes a given SQL non-query like DELETE, INSERT, UPDATE
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