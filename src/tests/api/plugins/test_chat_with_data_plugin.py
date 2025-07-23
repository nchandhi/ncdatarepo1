import pytest
from unittest.mock import patch, MagicMock, AsyncMock, Mock
from plugins.chat_with_data_plugin import ChatWithDataPlugin
from azure.ai.agents.models import (RunStepToolCallDetails, MessageRole, ListSortOrder)


@pytest.fixture
def mock_config():
    config_mock = MagicMock()
    config_mock.azure_openai_deployment_model = "gpt-4"
    config_mock.azure_openai_endpoint = "https://test-openai.azure.com/"
    config_mock.azure_openai_api_version = "2024-02-15-preview"
    config_mock.azure_ai_search_endpoint = "https://search.test.azure.com/"
    config_mock.azure_ai_search_api_key = "search-api-key"
    config_mock.azure_ai_search_index = "test_index"
    config_mock.use_ai_project_client = False
    config_mock.azure_ai_project_conn_string = "test-connection-string"
    return config_mock


@pytest.fixture
def chat_plugin(mock_config):
    with patch("plugins.chat_with_data_plugin.Config", return_value=mock_config):
        plugin = ChatWithDataPlugin()
        return plugin


class TestChatWithDataPlugin:
    @pytest.mark.asyncio
    @patch("plugins.chat_with_data_plugin.execute_sql_query", new_callable=AsyncMock)
    @patch("plugins.chat_with_data_plugin.SQLAgentFactory.get_agent", new_callable=AsyncMock)
    async def test_get_sql_response_with_sql_agent(self, mock_get_agent, mock_execute_sql, chat_plugin):
        # Mocks
        mock_agent = MagicMock()
        mock_agent.id = "agent-id"
        mock_client = MagicMock()

        # Set return value for get_agent
        mock_get_agent.return_value = {"agent": mock_agent, "client": mock_client}

        # Mock thread creation
        mock_thread = MagicMock()
        mock_thread.id = "thread-id"
        mock_client.agents.threads.create.return_value = mock_thread

        # Mock message creation: no return needed

        # Mock run creation and success status
        mock_run = MagicMock()
        mock_run.status = "succeeded"
        mock_client.agents.runs.create_and_process.return_value = mock_run

        # Mock response message with SQL text
        mock_agent_msg = MagicMock()
        mock_agent_msg.role = MessageRole.AGENT
        mock_agent_msg.text_messages = [MagicMock(text=MagicMock(value="```sql\nSELECT CAST(StartTime AS DATE) AS date, COUNT(*) AS total_calls FROM km_processed_data WHERE StartTime >= DATEADD(DAY, -7, GETDATE()) GROUP BY CAST(StartTime AS DATE) ORDER BY date ASC;\n```"))]
        mock_client.agents.messages.list.return_value = [mock_agent_msg]

        # Mock final SQL execution
        mock_execute_sql.return_value = "(datetime.date(2025, 6, 27), 11)(datetime.date(2025, 6, 28), 20)(datetime.date(2025, 6, 29), 29)(datetime.date(2025, 6, 30), 17)(datetime.date(2025, 7, 1), 19)(datetime.date(2025, 7, 2), 16)"

        # Mock thread deletion
        mock_client.agents.threads.delete.return_value = None

        # Act
        result = await chat_plugin.get_sql_response("Total number of calls by date for last 7 days")

        # Assert
        assert result == "(datetime.date(2025, 6, 27), 11)(datetime.date(2025, 6, 28), 20)(datetime.date(2025, 6, 29), 29)(datetime.date(2025, 6, 30), 17)(datetime.date(2025, 7, 1), 19)(datetime.date(2025, 7, 2), 16)"
        mock_execute_sql.assert_called_once_with("SELECT CAST(StartTime AS DATE) AS date, COUNT(*) AS total_calls FROM km_processed_data WHERE StartTime >= DATEADD(DAY, -7, GETDATE()) GROUP BY CAST(StartTime AS DATE) ORDER BY date ASC;")
        mock_client.agents.threads.create.assert_called_once()
        mock_client.agents.messages.create.assert_called_once()
        mock_client.agents.runs.create_and_process.assert_called_once()
        mock_client.agents.messages.list.assert_called_once_with(thread_id="thread-id", order=ListSortOrder.ASCENDING)
        mock_client.agents.threads.delete.assert_called_once_with(thread_id="thread-id")

    @pytest.mark.asyncio
    @patch("plugins.chat_with_data_plugin.execute_sql_query")
    @patch("plugins.chat_with_data_plugin.SQLAgentFactory.get_agent", new_callable=AsyncMock)
    async def test_get_sql_response_exception(self, mock_get_agent, mock_execute_sql, chat_plugin):
        # Setup mock to raise exception
        mock_get_agent.side_effect = Exception("Test error")
        
        # Call the method
        result = await chat_plugin.get_sql_response("Show me data")
        
        # Assertions
        assert result == "Details could not be retrieved. Please try again later."
        mock_execute_sql.assert_not_called()


    @pytest.mark.asyncio
    @patch("plugins.chat_with_data_plugin.SearchAgentFactory.get_agent", new_callable=AsyncMock)
    async def test_get_answers_from_calltranscripts_success(self, mock_get_agent, chat_plugin):
        # Use the fixture passed by pytest
        self.chat_plugin = chat_plugin  # or just use `chat_plugin` directly

        # Mock agent and client setup
        mock_agent = MagicMock()
        mock_agent.id = "mock-agent-id"
        mock_client = MagicMock()
        mock_get_agent.return_value = {"agent": mock_agent, "client": mock_client}

        # Mock thread creation
        mock_thread = MagicMock()
        mock_thread.id = "thread-id"
        mock_client.agents.threads.create.return_value = mock_thread

        # Mock run creation
        mock_run = MagicMock()
        mock_run.status = "succeeded"
        mock_run.id = "run-id"
        mock_client.agents.runs.create_and_process.return_value = mock_run

        # Mock run steps
        mock_run_step = MagicMock()
        mock_run_step.step_details = RunStepToolCallDetails(tool_calls=[
            {
                "azure_ai_search": {
                    "output": str({
                        "metadata": {
                            "get_urls": ["https://example.com/doc1"],
                            "titles": ["Document Title 1"]
                        }
                    })
                }
            }
        ])
        mock_client.agents.run_steps.list.return_value = [mock_run_step]

        # Mock agent message with answer
        mock_agent_msg = MagicMock()
        mock_agent_msg.role = MessageRole.AGENT
        mock_agent_msg.text_messages = [MagicMock(text=MagicMock(value="This is a test answer with citation 【3:0†source】"))]
        mock_client.agents.messages.list.return_value = [mock_agent_msg]

        # Mock thread deletion
        mock_client.agents.threads.delete.return_value = None

        # Call the method
        result = await chat_plugin.get_answers_from_calltranscripts("What is the summary?")

        # Assert
        assert isinstance(result, dict)
        assert result["answer"] == "This is a test answer with citation [1]"
        assert result["citations"] == [{"url": "https://example.com/doc1", "title": "Document Title 1"}]

    @pytest.mark.asyncio
    @patch("plugins.chat_with_data_plugin.SearchAgentFactory.get_agent", new_callable=AsyncMock)
    async def test_get_answers_from_calltranscripts_exception(self, mock_get_agent, chat_plugin):
        # Setup the mock to raise an exception
        mock_get_agent.side_effect = Exception("Test error")

        # Call the method
        result = await chat_plugin.get_answers_from_calltranscripts("Sample question")

        # Assertions
        assert result == "Details could not be retrieved. Please try again later."