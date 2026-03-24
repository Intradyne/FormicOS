# Wave 14 Service Colonies — Activation

Feature: Service colony activation

  Scenario: Completed colony activated as service
    Given a colony "col-abc" with status "completed"
    When the operator calls activate_service with colony_id "col-abc" and service_type "research"
    Then a ColonyServiceActivated event is emitted
    And the colony status becomes "service"
    And the colony is registered in the ServiceRouter as type "research"
    And the colony's agents have status "idle"

  Scenario: Running colony cannot be activated as service
    Given a colony "col-xyz" with status "running"
    When the operator calls activate_service with colony_id "col-xyz"
    Then the activation is rejected with error "Colony must be completed before activation"

  Scenario: Service colony appears in fleet view
    Given a colony "col-abc" with status "service"
    Then the colony snapshot includes status "service"
    And the view state includes the colony in the service colony list
