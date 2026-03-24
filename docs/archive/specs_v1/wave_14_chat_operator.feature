# Wave 14 Colony Chat — Operator Messages

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
