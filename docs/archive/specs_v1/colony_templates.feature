Feature: Colony templates and naming
  Colony configurations can be saved as reusable templates. Colonies receive
  Queen-assigned human-readable names. The suggest-team endpoint recommends
  castes for a given objective.

  Background:
    Given the FormicOS application is running
    And at least one workspace and thread exist

  # --- Template creation ---

  Scenario: Save template from completed colony
    Given colony "col_1" completed successfully with castes ["coder", "reviewer"]
    When the operator saves colony "col_1" as a template
    Then a ColonyTemplateCreated event is emitted
    And a YAML file exists in config/templates/
    And the template contains caste_names ["coder", "reviewer"]
    And the template has a source_colony_id of "col_1"

  Scenario: Create template manually via REST
    When a POST request to /api/v1/templates contains name "Code Review" and castes ["coder", "reviewer"]
    Then a ColonyTemplateCreated event is emitted
    And the template is listed in GET /api/v1/templates

  Scenario: Template creation generates description via LLM
    Given a colony completed with task "Refactor auth module to JWT"
    When the operator saves the colony as a template
    Then the template description is non-empty
    And the description relates to the original task

  # --- Template usage ---

  Scenario: Spawn colony from template
    Given a template "tmpl_1" exists with castes ["coder", "reviewer"] and budget 1.0
    When a colony is spawned with template_id "tmpl_1" and task "Fix login bug"
    Then a ColonySpawned event is emitted with castes ["coder", "reviewer"]
    And a ColonyTemplateUsed event is emitted linking "tmpl_1" to the new colony
    And the colony budget_limit is 1.0

  Scenario: Template fields can be overridden at spawn time
    Given a template "tmpl_1" exists with budget 1.0 and max_rounds 25
    When a colony is spawned with template_id "tmpl_1" and budget_limit 2.0
    Then the colony budget_limit is 2.0
    And max_rounds remains 25

  Scenario: Template use_count increments on spawn
    Given template "tmpl_1" has use_count 3
    When a colony is spawned from template "tmpl_1"
    Then template "tmpl_1" use_count becomes 4

  # --- Template versioning ---

  Scenario: Template edit creates new version
    Given template "tmpl_1" exists at version 1
    When the operator edits template "tmpl_1" to add caste "researcher"
    Then a new YAML file is created with version 2
    And the version 1 file is retained unchanged
    And GET /api/v1/templates returns version 2 as the latest

  # --- Template listing ---

  Scenario: List templates returns latest versions
    Given templates exist: "Code Review" v2, "Research Sprint" v1
    When GET /api/v1/templates is called
    Then 2 templates are returned
    And "Code Review" shows version 2

  # --- Colony naming ---

  Scenario: Queen assigns display name after colony creation
    Given a colony is spawned with task "Refactor the auth module"
    When the Queen naming LLM call succeeds
    Then a ColonyNamed event is emitted
    And the colony projection has a non-empty display_name
    And the display_name is 2-4 words

  Scenario: Colony naming falls back to UUID on LLM failure
    Given a colony is spawned with task "Fix bug"
    And the naming LLM call times out
    Then the colony projection display_name starts with "colony-"
    And no ColonyNamed event is emitted

  Scenario: Colony name is cosmetic and does not affect routing
    Given colony "col_1" has display_name "Auth Refactor Sprint"
    When events are queried for colony "col_1"
    Then all event addresses use the UUID, not the display name

  Scenario: Colony name updates via WebSocket
    Given the frontend is connected via WebSocket
    When a ColonyNamed event is emitted
    Then the colony card updates to show the new display_name

  # --- Suggest-team endpoint ---

  Scenario: Suggest-team returns caste recommendations
    When POST /api/v1/suggest-team is called with objective "Write unit tests for the API"
    Then the response contains a castes array
    And each entry has caste, count, and reasoning fields
    And at least one caste is "coder"

  Scenario: Suggest-team works with local model fallback
    Given the Gemini API key is not configured
    When POST /api/v1/suggest-team is called
    Then the response still contains caste recommendations
    And the recommendations use the local model

  Scenario: Suggest-team result feeds colony creation flow
    Given suggest-team returns ["coder", "reviewer", "researcher"]
    When the operator accepts the suggestion and spawns a colony
    Then the colony is created with castes ["coder", "reviewer", "researcher"]
