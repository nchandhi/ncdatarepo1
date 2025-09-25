using System.Text.Json;
using CsApi.Interfaces;
using CsApi.Models;
using CsApi.Services;
using CsApi.Repositories;
using Microsoft.AspNetCore.Mvc;

namespace CsApi.Controllers;

[ApiController]
[Route("api")] // matches /api prefix
public class ChatController : ControllerBase
{
    private readonly IChatService _chatService;
    private readonly IUserContextAccessor _userContextAccessor;
    private readonly ISqlConversationRepository _sqlRepo;

    public ChatController(IChatService chatService, IUserContextAccessor userContextAccessor, ISqlConversationRepository sqlRepo)
    { _chatService = chatService; _userContextAccessor = userContextAccessor; _sqlRepo = sqlRepo; }

    [HttpPost("chat")]
    public async Task Chat([FromBody] ChatRequest request, [FromServices] AzureAIAgentOrchestrator orchestrator, CancellationToken ct)
    {
        Response.ContentType = "application/json-lines";
        if (string.IsNullOrWhiteSpace(request.Query))
        {
            await Response.WriteAsync(JsonSerializer.Serialize(new { error = "query is required" }) + "\n\n", ct);
            return;
        }
        var userId = Request.Headers["x-ms-client-principal-id"].FirstOrDefault();
        var convId = await _sqlRepo.EnsureConversationAsync(userId, request.ConversationId, title: string.Empty, ct);
        var userMessage = new ChatMessage { Id = Guid.NewGuid().ToString(), Role = "user", Content = request.Query, CreatedAt = DateTime.UtcNow };
        await _sqlRepo.AddMessageAsync(userId, convId, userMessage, ct);

        // Use orchestrator agent for RAG/AI response
        var agent = orchestrator.Agent;
        var thread = new Microsoft.SemanticKernel.Agents.AzureAI.AzureAIAgentThread(agent.Client);
        var message = new Microsoft.SemanticKernel.ChatMessageContent(Microsoft.SemanticKernel.ChatCompletion.AuthorRole.User, request.Query);
        var acc = "";
        await foreach (var response in agent.InvokeStreamingAsync(message, thread))
        {
            acc += response.ToString();
            var envelope = new
            {
                id = convId,
                model = "rag-model",
                created = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
                choices = new[] { new { messages = new[] { new { role = "assistant", content = acc } }, delta = new { role = "assistant", content = acc } } }
            };
            await Response.WriteAsync(JsonSerializer.Serialize(envelope) + "\n\n", ct);
            await Response.Body.FlushAsync(ct);
        }
        var assistant = new ChatMessage { Id = Guid.NewGuid().ToString(), Role = "assistant", Content = acc, CreatedAt = DateTime.UtcNow };
        await _sqlRepo.AddMessageAsync(userId, convId, assistant, ct);
        await thread.DeleteAsync();
    }

    [HttpGet("layout-config")]
    public IActionResult LayoutConfig([FromServices] IConfiguration config)
    {
        var layoutConfigStr = config["REACT_APP_LAYOUT_CONFIG"] ?? string.Empty;
        if (!string.IsNullOrWhiteSpace(layoutConfigStr))
        {
            try
            {
                using var doc = JsonDocument.Parse(layoutConfigStr);
                return new JsonResult(doc.RootElement.Clone());
            }
            catch (JsonException)
            {
                return BadRequest(new { error = "Invalid layout configuration format." });
            }
        }
        return BadRequest(new { error = "Layout config not found in environment variables" });
    }

    [HttpGet("display-chart-default")]
    public IActionResult DisplayChartDefault([FromServices] IConfiguration config)
    {
        var val = config["DISPLAY_CHART_DEFAULT"] ?? string.Empty;
        if (!string.IsNullOrWhiteSpace(val))
        {
            return new JsonResult(new { isChartDisplayDefault = val });
        }
        return BadRequest(new { error = "DISPLAY_CHART_DEFAULT flag not found in environment variables" });
    }

    [HttpPost("fetch-azure-search-content")]
    public async Task<IActionResult> FetchAzureSearchContent([FromBody] FetchAzureSearchContentRequest req)
    {
        if (string.IsNullOrWhiteSpace(req?.Url))
            return BadRequest(new { error = "URL is required" });
        try
        {
            using var httpClient = new HttpClient();
            var requestMsg = new HttpRequestMessage(HttpMethod.Get, req.Url);
            requestMsg.Headers.Add("Content-Type", "application/json");
            var response = await httpClient.SendAsync(requestMsg);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                return Ok(new { content = json });
            }
            return StatusCode((int)response.StatusCode, new { error = $"Error: HTTP {response.StatusCode}" });
        }
        catch (Exception)
        {
            return StatusCode(500, new { error = "Internal server error" });
        }
    }

    public class FetchAzureSearchContentRequest { public string? Url { get; set; } }
}
