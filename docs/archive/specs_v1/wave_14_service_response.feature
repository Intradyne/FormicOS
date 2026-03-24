# Wave 14 Service Colonies — Response Matching

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
