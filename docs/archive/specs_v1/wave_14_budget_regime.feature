# Wave 14 Safety — Budget Regime

Feature: Budget regime injection into agent prompts

  Background:
    Given a colony with budget $5.00
    And a Coder agent with tier "standard"

  Scenario: Full exploration regime at >=70% remaining
    Given the colony has spent $1.00
    When the agent's system prompt is assembled
    Then the prompt contains "[Budget Status]"
    And the prompt contains "remaining (80%)"
    And the prompt contains "room for detailed exploration"

  Scenario: Focused regime at 30-70% remaining
    Given the colony has spent $3.00
    When the agent's system prompt is assembled
    Then the prompt contains "remaining (40%)"
    And the prompt contains "Be focused"

  Scenario: Wrap-up regime at 10-30% remaining
    Given the colony has spent $4.00
    When the agent's system prompt is assembled
    Then the prompt contains "remaining (20%)"
    And the prompt contains "Wrap up"

  Scenario: Exhaustion regime at <10% remaining
    Given the colony has spent $4.60
    When the agent's system prompt is assembled
    Then the prompt contains "remaining (8%)"
    And the prompt contains "Answer with what you have"

  Scenario: Budget block includes iteration count
    Given the agent has used 3 of 25 iterations
    When the agent's system prompt is assembled
    Then the prompt contains "Iterations used: 3/25"

  Scenario: Budget block includes round progress
    Given the colony is on round 4 of 10
    When the agent's system prompt is assembled
    Then the prompt contains "Round: 4/10"
