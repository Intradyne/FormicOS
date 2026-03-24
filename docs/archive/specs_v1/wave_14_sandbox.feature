# Wave 14 Sandbox Specs

Feature: Sandboxed code execution via code_execute tool

  Scenario: Successful code execution
    When an agent calls code_execute with code "print(42)"
    Then the result has exit_code 0
    And the result stdout contains "42"
    And a CodeExecuted event is emitted with blocked false
    And a ColonyChatMessage is emitted containing "Code executed" and "exit 0"

  Scenario: Code with runtime error
    When an agent calls code_execute with code "1/0"
    Then the result has exit_code 1
    And the result stderr contains "ZeroDivisionError"
    And a CodeExecuted event is emitted with blocked false
    And a ColonyChatMessage is emitted containing "Code failed"

  Scenario: AST pre-parser blocks dangerous import
    When an agent calls code_execute with code "import subprocess; subprocess.run(['ls'])"
    Then the code is rejected before execution
    And the result contains "Blocked import: subprocess"
    And a CodeExecuted event is emitted with blocked true
    And a ColonyChatMessage is emitted containing "Code blocked"

  Scenario: AST pre-parser blocks os import
    When an agent calls code_execute with code "import os; os.remove('/etc/passwd')"
    Then the code is rejected before execution
    And the result contains "Blocked import: os"

  Scenario: AST pre-parser blocks eval builtin
    When an agent calls code_execute with code "eval('__import__(\"os\").system(\"rm -rf /\")')"
    Then the code is rejected before execution
    And the result contains "Blocked builtin: eval"

  Scenario: Execution timeout
    When an agent calls code_execute with code "import time; time.sleep(999)" and timeout 5
    Then the result has exit_code indicating timeout
    And the result stderr contains timeout indication

  Scenario: Output truncation
    When an agent calls code_execute with code that produces 50KB of stdout
    Then the result stdout is truncated to 10KB
    And the CodeExecuted event stdout_preview is truncated to 500 chars

  Scenario: ANSI escape stripping
    When an agent calls code_execute with code that produces ANSI-colored output
    Then the result stdout contains no ANSI escape sequences

  Scenario: Container pool recycling
    Given the sandbox pool has 3 warm containers
    When code_execute is called
    Then the container is acquired from the pool
    And after execution the container's /tmp is cleaned
    And the container is returned to the pool
