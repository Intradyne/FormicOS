Feature: Caste-phase compute routing (Wave 9, ADR-012)
  The compute router selects models per (phase, caste) from a YAML routing table,
  with budget-aware fallback and adapter verification.

  Scenario: Routing table directs reviewer to local model
    Given the routing table maps execute/reviewer to "llama-cpp/gpt-4"
    And the cascade default for reviewer is "anthropic/claude-sonnet-4.6"
    When a reviewer agent executes in phase "execute"
    Then the LLM call uses model "llama-cpp/gpt-4"
    And AgentTurnStarted.model is "llama-cpp/gpt-4"

  Scenario: Missing routing entry falls through to cascade default
    Given the routing table has no entry for phase "compress"
    And the cascade default for archivist is "llama-cpp/gpt-4"
    When an archivist agent executes in phase "compress"
    Then the LLM call uses model "llama-cpp/gpt-4"
    And the routing reason is "cascade_default"

  Scenario: Budget gate forces cheapest model
    Given the routing table maps execute/coder to "anthropic/claude-sonnet-4.6"
    And the colony budget remaining is $0.05
    And the cheapest registered model is "llama-cpp/gpt-4"
    When a coder agent executes in phase "execute"
    Then the LLM call uses model "llama-cpp/gpt-4"
    And the routing reason is "budget_gate"

  Scenario: Missing adapter triggers silent fallback
    Given the routing table maps execute/researcher to "gemini/gemini-2.5-flash"
    And no adapter is registered for provider "gemini"
    And the cascade default for researcher is "llama-cpp/gpt-4"
    When a researcher agent executes in phase "execute"
    Then the LLM call uses model "llama-cpp/gpt-4"
    And the routing reason is "adapter_fallback"

  Scenario: Empty routing table preserves existing behavior
    Given the routing table is empty
    And the cascade default for coder is "llama-cpp/gpt-4"
    When a coder agent executes in phase "execute"
    Then the LLM call uses model "llama-cpp/gpt-4"
    And the routing reason is "cascade_default"

  Scenario: Every routing decision is logged
    Given any agent executes any phase
    Then a structlog entry with key "compute_router.route" is emitted
    And the entry contains caste, phase, selected, reason, and budget_remaining
