Feature: Colony round execution
  Colonies execute auditable rounds through the goal, intent, route, execute, and compress phases.

  Scenario: A round emits the five phase sequence
    Given colony "alpha" is running with strategy "stigmergic"
    When round 1 starts
    Then a RoundStarted event is emitted
    And PhaseEntered events are emitted in order "goal", "intent", "route", "execute", "compress"
    And a RoundCompleted event is emitted

  Scenario: Sequential strategy runs one agent turn at a time
    Given colony "alpha" uses strategy "sequential"
    And colony "alpha" has agents "coder" and "reviewer"
    When round 1 executes
    Then agent turns are started one at a time
    And no execution group contains more than one agent

  Scenario: High convergence completes the colony
    Given colony "alpha" uses convergence threshold 0.95
    And round 3 reaches convergence 0.97
    When round 3 completes
    Then a RoundCompleted event is emitted with convergence 0.97
    And a ColonyCompleted event is emitted

  Scenario: Repeated high stability with no progress triggers a warning
    Given colony "alpha" has stability above 0.95 for 2 consecutive rounds
    And colony "alpha" has progress below 0.01 for those rounds
    When governance evaluates round 2
    Then the colony is marked with a tunnel-vision warning
