# Wave 14 Safety — Tool Permissions

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
