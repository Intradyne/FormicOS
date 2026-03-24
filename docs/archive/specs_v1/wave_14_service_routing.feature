# Wave 14 Service Colonies — Query Routing

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
