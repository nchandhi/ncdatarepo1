from datetime import datetime, date
import struct
import json
from common.config.config import Config
import logging
from azure.identity.aio import AzureCliCredential
import pyodbc
from typing import Tuple, Any
from azure.identity import DefaultAzureCredential

async def get_fabric_db_connection():
    """Get a connection to the SQL database"""
    config = Config()

    server = config.fabric_sqldb_server
    database = config.fabric_sqldb_database
    driver = config.fabric_driver
    fabric_sqldb_connection_string = config.fabric_sqldb_connection_string
    app_env = config.app_env

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
        logging.info("FABRIC-SQL:Failed to connect Fabric SQL Database")      
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

async def execute_sql_query(sql_query):
    """
    Executes a given SQL query and returns the result as a concatenated string.
    """
    conn = await get_fabric_db_connection()
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(sql_query)
        result = ''.join(str(row) for row in cursor.fetchall())
        return result
    except Exception as e:
        logging.error("Error executing SQL query: %s", e)
        return None
    finally:
        if cursor:
            cursor.close()
        conn.close() 

async def get_fabric_db_connection1():
    """Get a connection to the SQL database"""
    config = Config()

    server = config.fabric_sqldb_server
    database = config.fabric_sqldb_database
    driver =  config.fabric_driver
    fabric_sqldb_connection_string = config.fabric_sqldb_connection_string
    app_env = "dev" # config.app_env

    try:
        # logging.info("FABRIC-SQL-app_env: %s" % app_env)
        # Set up the connection
        conn=None
        connection_string = ""
        if app_env == 'dev':
            async with AioDefaultAzureCredential() as credential:
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
                print('connected to fabric sql db')        
        else:
            connection_string = fabric_sqldb_connection_string
            conn = pyodbc.connect(connection_string)

        # logging.info("FABRIC-SQL-connection_string: %s" % connection_string)        
        # logging.info("FABRIC-SQL-User: %s" % conn.getinfo(pyodbc.SQL_USER_NAME))
        # logging.info("FABRIC-SQL:Successfully Connected to Fabric SQL Database")
        return conn
    except :#pyodbc.Error as e:
        # logging.info("FABRIC-SQL:Failed to connect Fabric SQL Database")      
        # return conn
        print("Failed to connect to Fabric SQL Database")
        pass