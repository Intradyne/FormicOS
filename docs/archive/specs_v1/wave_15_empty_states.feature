Feature: Empty states

  Scenario: Queen overview shows guidance when no colonies exist
    Given no colonies have been spawned
    When the operator views the Queen tab
    Then the overview shows template suggestions
    And the overview shows a prompt to describe a task

  Scenario: Knowledge view explains itself when empty
    Given no colonies have completed
    When the operator views the Knowledge tab
    Then the view shows a message explaining knowledge grows with colony runs

  Scenario: Thread view shows spawn prompt when empty
    Given a thread with no colonies
    When the operator views the thread
    Then the view shows a message suggesting to spawn a colony
