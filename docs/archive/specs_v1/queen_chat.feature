Feature: Queen multi-chat threads (S4)
  The operator converses with the Queen per-thread. The Queen spawns colonies.

  Scenario: Send a message to the Queen
    Given a thread "main" in workspace "research"
    When the operator sends "Analyze the authentication module"
    Then a QueenMessage event is emitted with role "operator"
    And the Queen responds with a plan
    And a QueenMessage event is emitted with role "queen"

  Scenario: Queen spawns a colony from chat
    Given the operator asked the Queen to "refactor the auth module"
    When the Queen decides to spawn a colony
    Then a ColonySpawned event is emitted
    And the colony appears in the thread view
    And the colony begins running rounds

  Scenario: Multiple threads have independent conversations
    Given threads "main" and "experiment" in workspace "research"
    When the operator sends a message in thread "main"
    Then the message appears only in "main"'s Queen chat
    And thread "experiment"'s chat is unaffected
