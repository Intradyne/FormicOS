Feature: First-run bootstrap

  Scenario: Fresh database triggers welcome experience
    Given the event store is empty (last_seq == 0)
    When the application starts
    Then a default workspace "default" is created
    And a default thread "main" is created
    And templates from config/templates/ are readable and visible
    And a QueenMessage is emitted with role "queen" containing "Welcome to FormicOS"

  Scenario: Second startup does not re-trigger welcome
    Given the event store has last_seq > 0
    When the application starts
    Then no welcome QueenMessage is emitted
    And no duplicate workspace or thread is created

  Scenario: Templates are visible after first run
    Given the application completed first-run bootstrap
    When the operator opens the Templates tab
    Then at least 5 templates are visible in the browser
    And each template shows name, description, and tags

  Scenario: Welcome message appears in Queen chat
    Given the application completed first-run bootstrap
    When the operator views the Queen tab
    Then the chat shows a welcome message from the Queen
    And the message contains instructions for spawning a colony
