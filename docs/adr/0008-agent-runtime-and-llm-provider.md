# ADR 0008: Own agent loop on the Anthropic SDK; AMD Radeon Cloud as the model provider

Date: 2026-11-27. Status: accepted.

## Context
The agent (`finrag.agent`) is a short tool-calling loop on the Anthropic Client SDK. It
calls two fixed-SQL tools (ADR 0003) and writes every tool call to `audit_log`.

Two questions came up:
1. Should the project use an agent framework: LangChain, LangGraph, LlamaIndex, the
   OpenAI Agents SDK, the Claude Agent SDK, or the Anthropic SDK tool runner?
2. Which model should the agent use?

What this project must show is reproducible data pipelines, retrieval and tools that can
be tested, and an audit record of every tool call. Data pipelines will be orchestrated
separately (step 10); an agent framework would not help with these goals.

AMD Radeon Cloud (Token Factory) offers a daily credit of USD 1 and a limit of 20 requests
per minute. Its API documentation lists both an OpenAI-compatible `/v1/chat/completions`
endpoint and an Anthropic-compatible `/v1/messages` endpoint under
`https://developer.amd.com.cn/radeon/api/v1`; the Anthropic endpoint accepts the key in
the `x-api-key` header, as the Anthropic SDK sends it. On 2026-11-27,
`DeepSeek-V4.1-Flash` returned a correct tool call for a `get_fact` schema (company "3M",
concept "revenue", fiscal year 2018) through both endpoints; through `/v1/messages` the
reply had `stop_reason` `tool_use` and one `tool_use` block, in the Anthropic format.

## Decision
- **No agent framework.** The agent keeps its own loop. Retrieval and tools stay fixed,
  parameterized SQL, so they can be tested and audited without a framework in between.
- **One interface: the Anthropic Messages API.** The agent keeps the Anthropic Client SDK.
  Its base URL, API key and model come from settings. The default is AMD's
  Anthropic-compatible endpoint (SDK base URL `https://developer.amd.com.cn/radeon/api`,
  key `AMD_API_KEY`) with the model `amd:DeepSeek-V4.1-Flash`. The `amd:` prefix is kept in
  logs and stored results and removed before the API call. Pointing the same settings at
  Anthropic's own API needs no code change.
- **Calling rules:** a timeout per request; bounded retries on HTTP 429 and 5xx that
  honor `Retry-After`; no retry on other 4xx errors. Evaluation runs that send requests in
  parallel share one cool-down, so they stay under the rate limit together.
- **Evaluation** (step 6) reports answer accuracy, groundedness, refusals, cost and
  latency, with the model name on every result.
- **Azure: open, to be decided in step 6 or step 11.** See "Open question: an Azure model".
- **To revisit:** LangGraph in step 9, if human review must pause and resume a running
  agent; an MCP server for `get_fact` and `search_filings` in step 9 or 10, so other
  agents can use the same audited tools.

## Open question: an Azure model
Financial institutions usually run their workloads on an enterprise cloud, and many use
Azure together with Microsoft 365 and Microsoft Entra ID. A model deployed in the
institution's own Azure subscription keeps prompts, data and call records inside that
subscription, and can use Entra ID authentication instead of stored keys. Regulated firms
generally need such controls before they send internal documents to a model. The AMD
endpoint is suitable only for public data. Two routes exist:

|                   | A: Claude deployed in Microsoft Foundry                                                                                          | B: an Azure OpenAI model (for example the deployment `gpt-6-luna`)                                      |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Interface         | Anthropic Messages API at `https://<resource>.services.ai.azure.com/anthropic`                                                   | OpenAI Responses API at `https://<resource>.services.ai.azure.com/openai/v1`                            |
| Code change       | None in the agent loop: base URL, key and model come from settings; the SDK also offers an `AnthropicFoundry` client             | A second backend: another message format, tool-call format and response structure to implement and test |
| Authentication    | API key or Microsoft Entra ID                                                                                                    | API key or Microsoft Entra ID                                                                           |
| Fit with this ADR | Keeps one interface                                                                                                              | Reverses "one interface"                                                                                |
| Known limits      | Not available on Foundry: Admin API, Message Batches API, Models API and some other Claude features; the agent uses none of them | Tool calling of the specific deployment not yet verified                                                |

Until a route is chosen, the agent supports only the Anthropic interface. Choosing route B
needs a new ADR that supersedes the interface part of this one.

## Alternatives considered
- LlamaIndex: would take over chunking and retrieval, which must keep page boundaries
  (ADR 0007) and fixed SQL (ADR 0003).
- LangChain: wrappers and many indirect dependencies for a loop of about 70 lines.
- OpenAI Agents SDK: strong for handoffs between several agents; this project has one
  agent, and its built-in tracing sends data to OpenAI unless configured otherwise.
- Claude Agent SDK: runs Claude Code with file and command tools; this agent must only
  call two fixed tools.
- Anthropic SDK tool runner: in beta; per-call audit logging and a round limit would
  need wrappers anyway.
- A second backend for AMD's OpenAI-compatible endpoint: works, but adds a second message
  format and code path to test, which the Anthropic-compatible endpoint makes unnecessary.

## Consequences
- The AMD endpoint is `developer.amd.com.cn`. Only public filings and questions are sent;
  a deployment with private data would need a provider review first.
- A compatible endpoint may not support every Anthropic feature (for example prompt
  caching or extended thinking); the agent uses only messages, a system prompt and tools.
- The daily credit limits evaluation runs; evaluation must be resumable and report cost.
  The Messages response reports token counts (`usage.input_tokens`, `output_tokens` and
  the cache fields) but no cost, so cost is computed from tokens and the published price.
- The cloud sandbox and the Linux VM cannot reach the AMD API, so automated tests use a
  fake client; real calls run on the Mac.
- Implementation happens at the start of step 6, together with the timeout and retry
  settings.
