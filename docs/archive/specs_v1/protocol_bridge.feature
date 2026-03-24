Feature: WebSocket command bridge
  The web UI issues workspace-scoped commands that map to the same operations as MCP tools.

  Scenario: Spawn colony command stays workspace-scoped
    Given the operator is connected to workspace "research"
    When the UI sends a "spawn_colony" command for thread "main"
    Then the same colony-spawn operation exposed by MCP is invoked
    And the spawned colony belongs to workspace "research"

  Scenario: Event subscribers receive matching state updates
    Given the operator is subscribed to workspace "research"
    When colony "alpha" completes a round
    Then the subscriber receives a WebSocket event message for that round
    And the subscriber receives an updated state snapshot

  Scenario: Unsubscribe stops further event delivery
    Given the operator is subscribed to workspace "research"
    When the UI sends an "unsubscribe" command
    Then no further event messages are delivered to that client
