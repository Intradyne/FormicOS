Feature: Workspace configuration containers (S3)
  Workspace settings override system defaults without a process restart.

  Scenario: Updating workspace governance changes new colony behavior
    Given workspace "research" inherits the system strategy and budget
    When the operator updates the workspace strategy to "sequential"
    And the operator updates the workspace budget to 2.50
    Then a WorkspaceConfigChanged event is emitted for each changed field
    And newly spawned colonies in "research" use the updated values

  Scenario: Clearing a workspace override restores inheritance
    Given workspace "research" overrides the coder model to "ollama/llama3.3"
    When the operator clears the workspace coder override
    Then the workspace shows the inherited system model
    And future colony rounds resolve the inherited model

  Scenario: Caste recipes are visible before colony spawn
    Given caste recipes are loaded from configuration
    When the operator opens the Castes view
    Then the operator sees queen, coder, reviewer, researcher, and archivist recipes
    And each recipe shows its default tools and token limits
