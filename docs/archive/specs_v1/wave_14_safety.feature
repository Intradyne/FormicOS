# Wave 14 Safety Specs

Feature: Budget regime injection into agent prompts

  Background:
    Given a colony with budget $5.00
    And a Coder agent with tier "standard"

  Scenario: Full exploration regime at ≥70% remaining
    Given the colony has spent $1.00
    When the agent's system prompt is assembled
    Then the prompt contains "[Budget Status]"
    And the prompt contains "remaining (80%)"
    And the prompt contains "room for detailed exploration"

  Scenario: Focused regime at 30–70% remaining
    Given the colony has spent $3.00
    When the agent's system prompt is assembled
    Then the prompt contains "remaining (40%)"
    And the prompt contains "Be focused"

  Scenario: Wrap-up regime at 10–30% remaining
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


Feature: Caste tool permission enforcement

  Scenario: Coder can use code_execute
    Given an agent with caste "coder"
    When the agent attempts to call tool "code_execute"
    Then the tool call is permitted

  Scenario: Reviewer cannot use code_execute
    Given an agent with caste "reviewer"
    When the agent attempts to call tool "code_execute"
    Then the tool call is denied
    And the agent receives error "Tool 'code_execute' is not permitted for caste 'reviewer'"

  Scenario: Researcher cannot use code_execute
    Given an agent with caste "researcher"
    When the agent attempts to call tool "code_execute"
    Then the tool call is denied

  Scenario: Researcher can use web_search
    Given an agent with caste "researcher"
    When the agent attempts to call tool "web_search"
    Then the tool call is permitted

  Scenario: Coder cannot use kill_colony
    Given an agent with caste "coder"
    When the agent attempts to call tool "kill_colony"
    Then the tool call is denied

  Scenario: Unknown tool is denied by default
    Given an agent with caste "reviewer"
    When the agent attempts to call tool "unknown_tool_xyz"
    Then the tool call is denied
