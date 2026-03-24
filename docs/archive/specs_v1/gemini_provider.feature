Feature: Gemini LLM provider and defensive structured output
  Google Gemini is a third LLM provider behind LLMPort with defensive
  tool-call parsing shared across all three adapters.

  Background:
    Given the GEMINI_API_KEY environment variable is set
    And the adapter factory recognizes the "gemini/" model address prefix

  # --- Adapter basics ---

  Scenario: Gemini text completion returns normalized response
    Given a Gemini adapter configured for gemini-2.5-flash
    When a completion is requested with a user message
    Then the response has text content
    And finish_reason is "stop"
    And input_tokens and output_tokens are populated

  Scenario: Gemini tool call detected from response parts
    Given tools are provided in the completion request
    When Gemini returns a functionCall part with finishReason "STOP"
    Then the response contains a ToolCall with the correct name and arguments
    And finish_reason is "tool_use" (not "stop")

  Scenario: Gemini tool result round-trip preserves thoughtSignature
    Given Gemini returned a tool call with a thoughtSignature
    When the tool result is fed back in the next turn
    Then the thoughtSignature is included in the functionCall part of the history

  Scenario: Gemini RECITATION block surfaces as blocked
    Given Gemini returns finishReason "RECITATION"
    When the response is parsed
    Then finish_reason is "blocked"
    And the response text is empty or contains a block indicator

  Scenario: Gemini SAFETY block surfaces as blocked
    Given Gemini returns finishReason "SAFETY"
    When the response is parsed
    Then finish_reason is "blocked"

  Scenario: Gemini retry on 429 rate limit
    Given Gemini returns HTTP 429 on the first request
    And Gemini returns HTTP 200 on the second request
    When a completion is requested
    Then the response is successful
    And structlog contains a retry warning

  Scenario: Gemini streaming yields text chunks
    Given a Gemini adapter configured for streaming
    When a streaming completion is requested
    Then text chunks are yielded incrementally
    And the final chunk carries usageMetadata

  # --- Adapter factory routing ---

  Scenario: Model address prefix routes to correct adapter
    Given model address "gemini/gemini-2.5-flash"
    When the adapter factory resolves the adapter
    Then GeminiAdapter is returned
    Given model address "anthropic/claude-sonnet-4.6"
    When the adapter factory resolves the adapter
    Then AnthropicAdapter is returned
    Given model address "llama-cpp/gpt-4"
    When the adapter factory resolves the adapter
    Then OpenAICompatibleAdapter is returned

  # --- Defensive parsing (all providers) ---

  Scenario: Stage 1 parses clean JSON tool call
    Given raw text '{"name":"read_file","arguments":{"path":"/tmp"}}'
    When parse_tool_calls_defensive is called
    Then one ToolCall is returned with name "read_file"

  Scenario: Stage 2 repairs trailing comma in JSON
    Given raw text '{"name":"read_file","arguments":{"path":"/tmp",}}'
    When parse_tool_calls_defensive is called
    Then one ToolCall is returned with name "read_file"

  Scenario: Stage 3 extracts JSON from markdown fence
    Given raw text containing a ```json code fence wrapping a tool call
    When parse_tool_calls_defensive is called
    Then the tool call is extracted from inside the fence

  Scenario: Stage 3 strips Qwen3 thinking tags
    Given raw text '<think>reasoning</think>{"name":"read_file","arguments":{"path":"/tmp"}}'
    When parse_tool_calls_defensive is called
    Then the thinking tags are stripped
    And one ToolCall is returned with name "read_file"

  Scenario: Hallucinated tool name fuzzy-matched to known tools
    Given known tools are {"read_file", "write_file", "search"}
    And raw text contains a tool call with name "read_files"
    When parse_tool_calls_defensive is called
    Then the tool call name is corrected to "read_file"

  Scenario: Unknown tool name with no close match is rejected
    Given known tools are {"read_file", "write_file", "search"}
    And raw text contains a tool call with name "hack_system"
    When parse_tool_calls_defensive is called
    Then the tool call is rejected
    And an empty list is returned

  Scenario: Gemini string-args bug is handled
    Given raw text '{"name":"read_file","args":"{\"path\":\"/tmp\"}"}'
    When parse_tool_calls_defensive is called
    Then arguments are parsed from the JSON string
    And the ToolCall has arguments {"path": "/tmp"}

  # --- Routing table with Gemini ---

  Scenario: Researcher routes to Gemini Flash in execute phase
    Given the routing table has researcher execute mapped to "gemini/gemini-2.5-flash"
    When route_fn is called with caste "researcher" and phase "execute"
    Then the selected model is "gemini/gemini-2.5-flash"

  Scenario: Blocked response triggers fallback chain
    Given primary model is "gemini/gemini-2.5-flash"
    And the fallback model is "llama-cpp/gpt-4"
    When the primary returns finish_reason "blocked"
    Then the fallback model is tried
    And structlog logs fallback_triggered=true

  Scenario: Budget gate forces cheapest model
    Given budget_remaining is $0.05
    When route_fn is called
    Then the cheapest registered model (cost_per_input_token 0.0) is selected
    And the structlog reason is "budget_gate"
