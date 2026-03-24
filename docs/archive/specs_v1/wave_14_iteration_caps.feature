# Wave 14 Safety — Iteration Caps

Feature: Per-caste iteration caps

  Background:
    Given a colony with a Coder agent
    And the Coder has max_iterations 25 in caste_recipes.yaml

  Scenario: Agent completes within iteration limit
    When the Coder completes in 12 iterations
    Then the agent output is preserved normally
    And no governance chat message is emitted

  Scenario: Agent hits iteration cap
    When the Coder reaches iteration 25 without completing
    Then the agent's last output is preserved
    And a ColonyChatMessage is emitted with sender "system" and event_kind "governance"
    And the message contains "hit iteration limit (25)"
    And the round continues with other agents

  Scenario: Agent hits execution timeout
    Given the Coder has max_execution_time_s 300
    When the Coder runs for more than 300 seconds
    Then the agent's last output is preserved
    And a ColonyChatMessage is emitted with sender "system" and event_kind "governance"
    And the message contains "execution timeout"
    And the round continues with other agents
