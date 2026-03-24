Feature: Merge, prune, and broadcast (S2)
  The operator controls cross-colony information flow through merge edges.

  Scenario: Create a merge edge
    Given colonies "alpha" and "beta" in thread "main"
    When the operator creates a merge from "alpha" to "beta"
    Then a MergeCreated event is emitted
    And a visible edge appears from "alpha" to "beta" in the thread view

  Scenario: Merged context appears in next round
    Given a merge edge from "alpha" to "beta"
    And colony "alpha" has completed round 1 with output "analysis results"
    When colony "beta" runs round 1
    Then "beta"'s agents receive "alpha"'s compressed output in their context

  Scenario: Prune a merge edge
    Given a merge edge from "alpha" to "beta"
    When the operator prunes the edge
    Then a MergePruned event is emitted
    And the edge disappears from the thread view
    And colony "beta" no longer receives "alpha"'s output

  Scenario: Broadcast to siblings
    Given colonies "alpha", "beta", and "gamma" in thread "main"
    When the operator broadcasts "alpha"
    Then merge edges are created from "alpha" to "beta" and "alpha" to "gamma"
