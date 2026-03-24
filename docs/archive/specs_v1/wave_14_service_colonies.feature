# Wave 14 Service Colony Specs

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


Feature: Service colony query routing

  Scenario: Successful service query
    Given a service colony "col-abc" of type "research" is registered
    When an agent calls query_service with service_type "research" and query "What JWT libraries work with async?"
    Then a ServiceQuerySent event is emitted with the query text preview
    And the query is injected into the service colony's message loop as "[Service Query: <id>]"
    And the service colony processes the query
    And a ServiceQueryResolved event is emitted with the response preview and latency
    And the response text is returned to the calling agent

  Scenario: Query to unavailable service type
    Given no service colony of type "monitoring" is registered
    When an agent calls query_service with service_type "monitoring"
    Then the tool returns error "No monitoring colony is running"

  Scenario: Service query timeout
    Given a service colony "col-abc" of type "research" is registered
    And the service colony does not respond within the timeout
    When an agent calls query_service with timeout 5
    Then the tool returns a timeout error after 5 seconds

  Scenario: Service query appears in both colonies' chats
    Given a running colony "col-xyz" queries service colony "col-abc"
    When the query completes
    Then colony "col-xyz" chat contains a message with sender "service" and source_colony "col-abc"
    And colony "col-abc" chat contains a message showing the inbound query from "col-xyz"


Feature: Service colony response matching

  Scenario: Response matched by request ID
    Given a service query with request_id "svc-12345" was sent
    When the service colony's output contains "[Service Response: svc-12345]"
    Then the ServiceRouter resolves the response
    And the waiting caller receives the response text

  Scenario: Response with unrecognized request ID is ignored
    Given no pending query with request_id "svc-99999"
    When colony output contains "[Service Response: svc-99999]"
    Then the ServiceRouter logs a warning
    And no caller is unblocked
