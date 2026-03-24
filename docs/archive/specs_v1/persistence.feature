Feature: Event-sourced persistence (S8)
  All state persists via event sourcing. Stop and restart preserves everything.

  Scenario: State survives restart
    Given a workspace "research" with thread "main" and 2 completed colony rounds
    When the system is stopped and restarted
    Then workspace "research" appears in the sidebar
    And thread "main" contains the same colonies
    And colony round history is preserved

  Scenario: Event log is the source of truth
    Given 50 events have been written to the store
    When the materialized views are deleted and rebuilt
    Then the rebuilt state matches the pre-deletion state

  Scenario: No duplicate databases
    Given the system is running
    Then only one SQLite file exists in the data directory
    And there is no separate telemetry, config, or chat database
