Feature: Model cascade resolution (S5)
  Models resolve through nullable cascade: Thread → Workspace → System default.

  Scenario: System default is used when no overrides exist
    Given system default coder model is "llama-cpp/gpt-4"
    And workspace "research" has no coder model override
    When a colony in "research" needs a coder model
    Then it resolves to "llama-cpp/gpt-4"

  Scenario: Workspace override takes precedence
    Given system default coder model is "llama-cpp/gpt-4"
    And workspace "research" overrides coder model to "ollama/qwen3-30b"
    When a colony in "research" needs a coder model
    Then it resolves to "ollama/qwen3-30b"

  Scenario: Override can be cleared to inherit
    Given workspace "research" overrides coder model to "ollama/qwen3-30b"
    When the operator clears the workspace coder model override
    Then the workspace coder model shows "inherit: llama-cpp/gpt-4"
    And colonies resolve to the system default

  Scenario: Model change takes effect without restart
    Given a running colony using "llama-cpp/gpt-4"
    When the operator changes the workspace model override
    Then the next round uses the new model
    And no restart is required
