Feature: Startup and first-run setup (S9)
  FormicOS starts cleanly with docker compose and supports local-only operation.

  Scenario: Docker compose brings the system up
    Given the repository is configured with valid environment variables
    When the operator runs "docker compose up"
    Then the web surface starts
    And the operator can reach the FormicOS UI

  Scenario: First run works with local models only
    Given no cloud API keys are configured
    And at least one local model is available
    When the operator starts FormicOS
    Then the system boots without requiring a cloud connection
    And local models are visible in the model registry

  Scenario: First-run setup exposes missing credentials without blocking boot
    Given cloud models are configured without their API keys
    When the operator opens the model registry after startup
    Then those models are marked "no_key"
    And the rest of the system remains usable
