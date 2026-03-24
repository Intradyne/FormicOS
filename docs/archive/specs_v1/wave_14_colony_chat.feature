# Wave 14 Colony Chat Specs

Feature: Colony chat message selection

  Scenario: Round milestone appears in chat
    When round 3 of 8 starts with Phase 1 (Goal)
    Then a ColonyChatMessage is emitted with sender "system" and event_kind "phase"
    And the content contains "Round 3/8"

  Scenario: Governance warning appears in chat
    When convergence stall is detected with similarity 0.94
    Then a ColonyChatMessage is emitted with sender "system" and event_kind "governance"
    And the content contains "Convergence stall"

  Scenario: Approval request appears in chat
    When a cloud burst approval is requested for Coder-0 at $0.12
    Then a ColonyChatMessage is emitted with sender "system" and event_kind "approval"
    And the content contains "Approval needed"

  Scenario: Colony completion appears in chat
    When the colony completes successfully in 5 rounds at cost $0.47
    Then a ColonyChatMessage is emitted with sender "system" and event_kind "complete"
    And the content contains "Completed in 5 rounds"
    And the content contains "$0.47"

  Scenario: Code execution result appears in chat
    When a CodeExecuted event is emitted with exit_code 0 and duration 340ms
    Then a ColonyChatMessage is also emitted with sender "system"
    And the content contains "Code executed" and "340ms"

  Scenario: Agent token streams do NOT appear in chat
    When an agent produces streaming token output
    Then no ColonyChatMessage is emitted for the token stream

  Scenario: DyTopo edge weights do NOT appear in chat
    When DyTopo routing updates edge weights
    Then no ColonyChatMessage is emitted for the weight update

  Scenario: Individual tool call results do NOT appear in chat
    When an agent calls memory_search and gets results
    Then no ColonyChatMessage is emitted for the tool call result


Feature: Operator colony chat messages

  Scenario: Operator sends message via MCP tool
    When the operator calls chat_colony with colony_id "col-abc" and message "Focus on the race condition"
    Then a ColonyChatMessage is emitted with sender "operator"
    And the content is "Focus on the race condition"
    And the colony_id is "col-abc"

  Scenario: Operator sends message via WS command
    When the operator sends a WS command type "chat_colony" with colony_id and message
    Then a ColonyChatMessage event is stored in the event store
    And the message is injected into the colony's context for the next round


Feature: Colony chat persistence

  Scenario: Chat history survives restart
    Given a colony has received 5 chat messages (2 system, 2 operator, 1 service)
    When the system restarts and replays events
    Then the ColonyChatViewRegistry rebuilds the colony's chat with all 5 messages
    And the messages are in chronological order by seq

  Scenario: Chat view returns messages after a sequence number
    Given a colony has 10 chat messages with seq 1–10
    When chat history is requested with after_seq 7
    Then only messages with seq 8, 9, 10 are returned
