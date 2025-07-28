# from datetime import datetime
import struct

# import pandas as pd
# from api.models.input_models import ChartFilters
from common.config.config import Config
import logging
from azure.identity.aio import DefaultAzureCredential
import pyodbc


async def get_fabric_db_connection():
    """Get a connection to the SQL database"""
    config = Config()

    server = config.fabric_sqldb_server
    database = config.fabric_sqldb_database
    username = config.fabric_sqldb_username
    password = config.fabric_sqldb_database # Assuming this is a mistake in the original code, it should be `fabric_sqldb_password`
    driver = config.fabric_driver
    mid_id = config.fabric_mid_id

    # server = config.sqldb_server
    # database = config.sqldb_database
    # username = config.sqldb_username
    # password = config.sqldb_database # Assuming this is a mistake in the original code, it should be `sqldb_password`
    # driver = config.sqldb_driver
    # mid_id = config.sqldb_mid_id


    try:
        async with DefaultAzureCredential(managed_identity_client_id=mid_id) as credential:
            token = await credential.get_token("https://database.windows.net/.default")
            logging.info("AVJ-FABRIC-SQL-TOKEN: %s" % token.token)
            token_bytes = token.token.encode("utf-16-LE")
            token_struct = struct.pack(
                f"<I{len(token_bytes)}s",
                len(token_bytes),
                token_bytes
            )
            SQL_COPT_SS_ACCESS_TOKEN = 1256

            # Set up the connection
            connection_string = f"DRIVER={driver};SERVER={server};DATABASE={database};"
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


async def execute_fabric_sql_query(sql_query):
    """
    Executes a given SQL query and returns the result as a concatenated string.
    """
    conn = await get_fabric_db_connection()
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(sql_query)
        result = ''.join(str(row) for row in cursor.fetchall())
        logging.info("AVJ-FABRIC-SQL-QUERY: %s" % sql_query)
        logging.info("AVJ-FABRIC-SQL-RESULT: %s" % result)
        return result
    except Exception as e:
        logging.error("Error executing SQL query: %s", e)
        return None
    finally:
        if cursor:
            cursor.close()
        conn.close()
