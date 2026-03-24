Feature: Default configuration

  Scenario: All templates use CasteSlot format
    Given the templates in config/templates/
    When each template YAML is parsed
    Then every template has a "castes" key (not "caste_names")
    And each caste entry has "caste", "tier", and "count" fields

  Scenario: All templates have governance blocks
    Given the templates in config/templates/
    When each template YAML is parsed
    Then every template has a "governance" key
    And governance includes "max_rounds" >= 4
    And governance includes "budget_usd" >= 1.0

  Scenario: At least one template includes Archivist
    Given the templates in config/templates/
    When all templates are checked
    Then at least one template has a caste entry with caste "archivist"

  Scenario: All castes have safety limits
    Given the caste recipes in config/caste_recipes.yaml
    When each caste is checked
    Then every caste has "max_iterations" > 0
    And every caste has "max_execution_time_s" > 0

  Scenario: Coder caste has code_execute in tools
    Given the caste recipes in config/caste_recipes.yaml
    When the coder recipe is checked
    Then the tools list includes "code_execute"
