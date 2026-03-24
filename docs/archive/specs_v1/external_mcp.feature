Feature: External MCP orchestration (S7)
  External clients can orchestrate FormicOS through workspace-scoped MCP tools.

  Scenario: Spawn colony tool is workspace-scoped
    Given external client "queen-cli" is attached to workspace "research"
    When the client calls MCP tool "spawn_colony" for thread "main"
    Then the colony is created inside workspace "research"
    And no other workspace is modified

  Scenario: Workspace list and status are queryable over MCP
    Given workspaces "research" and "refactor-auth" exist
    When the client calls MCP tool "list_workspaces"
    Then both workspace identifiers are returned
    When the client calls MCP tool "get_status" for workspace "research"
    Then the status includes its threads and colonies

  Scenario: Queen chat is available over MCP
    Given thread "main" exists in workspace "research"
    When the client calls MCP tool "chat_queen" with message "Plan the auth refactor"
    Then a QueenMessage event is emitted with role "operator"
    And a QueenMessage event is emitted with role "queen"
