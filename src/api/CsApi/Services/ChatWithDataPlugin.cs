using System.Threading.Tasks;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
using Microsoft.SemanticKernel.Agents.AzureAI;
using System.ComponentModel;

namespace CsApi.Services
{
    public class ChatWithDataPlugin
    {
        private readonly AzureAIAgentOrchestrator _orchestrator;
        public ChatWithDataPlugin(AzureAIAgentOrchestrator orchestrator)
        {
            _orchestrator = orchestrator;
        }

        [KernelFunction]
        public async Task<string> ChatWithSQLDatabase(string input)
        {
            // TODO: Implement SQL chat logic using Semantic Kernel agent API
            // The following calls are stubbed out due to missing methods in current SDK
            // var agent = _orchestrator.Agent;
            // var client = agent.Client;
            // var thread = await client.Threads.CreateAsync();
            // await client.Messages.CreateAsync(thread.Id, Microsoft.SemanticKernel.ChatCompletion.AuthorRole.User, input);
            // var run = await client.Runs.CreateAndProcessAsync(thread.Id, agent.Id);
            // if (run.Status == "failed")
            //     return "Details could not be retrieved. Please try again later.";
            // string sqlQuery = "";
            // var messages = await client.Messages.ListAsync(thread.Id, order: "ASCENDING");
            // foreach (var msg in messages)
            // {
            //     if (msg.Role == "agent" && msg.TextMessages?.Count > 0)
            //     {
            //         sqlQuery = msg.TextMessages[^1].Text.Value;
            //         break;
            //     }
            // }
            // sqlQuery = sqlQuery.Replace("```sql", "").Replace("```", "").Trim();
            // await client.Threads.DeleteAsync(thread.Id);
            // return sqlQuery;
            return "[Stub] SQL chat response";
        }

        [KernelFunction]
        public async Task<string> GenerateChartData(string input)
        {
            // TODO: Implement chart data logic using Semantic Kernel agent API
            // The following calls are stubbed out due to missing methods in current SDK
            // var agent = _orchestrator.Agent;
            // var client = agent.Client;
            // var thread = await client.Threads.CreateAsync();
            // await client.Messages.CreateAsync(thread.Id, Microsoft.SemanticKernel.ChatCompletion.AuthorRole.User, input.Trim());
            // var run = await client.Runs.CreateAndProcessAsync(thread.Id, agent.Id);
            // if (run.Status == "failed")
            //     return "Details could not be retrieved. Please try again later.";
            // string chartdata = "";
            // var messages = await client.Messages.ListAsync(thread.Id, order: "ASCENDING");
            // foreach (var msg in messages)
            // {
            //     if (msg.Role == "agent" && msg.TextMessages?.Count > 0)
            //     {
            //         chartdata = msg.TextMessages[^1].Text.Value;
            //         break;
            //     }
            // }
            // await client.Threads.DeleteAsync(thread.Id);
            // return chartdata;
            return "[Stub] Chart data response";
        }

        public async Task<string> GetSqlResponseAsync(string input)
        {
            // Stub implementation for build error resolution
            return await ChatWithSQLDatabase(input);
        }

        public async Task<string> GetChartDataAsync(string input)
        {
            // Stub implementation for build error resolution
            return await GenerateChartData(input);
        }
    }
}
