# Wave 14 Colony Chat — Message Selection

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
