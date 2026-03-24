Feature: Approval workflow
  The operator can grant or deny gated actions before execution continues.

  Scenario: Approval request appears in the operator queue
    Given colony "alpha" needs approval for "cloud_burst"
    When the colony requests approval
    Then an ApprovalRequested event is emitted
    And the request appears in the Queen overview approval queue

  Scenario: Granting approval resumes the blocked action
    Given an open approval request for colony "alpha"
    When the operator grants the request
    Then an ApprovalGranted event is emitted
    And colony "alpha" resumes execution without restart

  Scenario: Denying approval blocks the pending action
    Given an open approval request for colony "alpha"
    When the operator denies the request
    Then an ApprovalDenied event is emitted
    And the blocked action is not executed
