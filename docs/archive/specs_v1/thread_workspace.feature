Feature: Thread is the operational workspace (S6)
  The thread view is where the operator works with the Queen, colonies, and merge edges.

  Scenario: Thread view combines chat and colony operations
    Given thread "main" in workspace "research" has colonies "alpha" and "beta"
    When the operator opens thread "main"
    Then the thread view shows the Queen chat
    And the thread view shows both colonies
    And the thread view shows any active merge edges between them

  Scenario: Colony spawn starts from the thread view
    Given thread "main" in workspace "research"
    When the operator asks the Queen to spawn a colony from the thread view
    Then a ColonySpawned event is emitted
    And the new colony appears in thread "main"

  Scenario: Merge controls live in the thread view
    Given thread "main" contains colonies "alpha" and "beta"
    When the operator creates a merge from "alpha" to "beta" in the thread view
    Then a MergeCreated event is emitted
    And the merge edge is visible without leaving the thread view
