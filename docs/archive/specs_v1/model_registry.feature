Feature: Model registry visibility and assignments (S5)
  The operator can inspect registered models and change caste assignments.

  Scenario: Registered model capabilities are visible
    Given the system model registry contains "anthropic/claude-sonnet-4.6"
    When the operator opens the model registry
    Then the model shows tool support and vision support
    And the model shows a 200000 token context window

  Scenario: Missing credentials surface as unavailable
    Given model "anthropic/claude-haiku-4.5" requires env var "ANTHROPIC_API_KEY"
    And that env var is not set
    When the operator opens the model registry
    Then the model status is "no_key"

  Scenario: Changing a caste assignment emits an event
    Given workspace "research" assigns coder model "anthropic/claude-sonnet-4.6"
    When the operator changes the coder model to "ollama/llama3.3"
    Then a ModelAssignmentChanged event is emitted
    And the next colony round resolves the new model
