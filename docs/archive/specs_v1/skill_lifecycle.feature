Feature: Skill lifecycle management (Wave 9, ADR-010)
  Skills are curated through quality gates, confidence-weighted retrieval,
  confidence evolution, and time decay.

  Scenario: Confidence-weighted retrieval prefers higher-confidence skills
    Given the skill bank contains skill A with confidence 0.8 and skill B with confidence 0.3
    And both skills have similar semantic relevance to the query
    When context assembly retrieves skills for a round
    Then skill A ranks higher than skill B in the composite score
    And injected skill text includes "[conf:0.8]" annotation

  Scenario: Freshness decay reduces stale skill ranking
    Given skill A was extracted 1 day ago and skill B was extracted 180 days ago
    And both have identical confidence and semantic relevance
    When context assembly computes composite scores
    Then skill A's freshness component is approximately 1.0
    And skill B's freshness component is approximately 0.25

  Scenario: Ingestion gate rejects low-quality source colonies
    Given a colony completes with quality_score 0.2
    When skill crystallization attempts to ingest extracted skills
    Then skills are rejected with reason "low_source_quality"
    And skills_extracted count is 0

  Scenario: Ingestion gate rejects semantic duplicates
    Given the skill bank contains "Use dependency injection for testability"
    When crystallization extracts "Apply dependency injection to improve testability"
    And the cosine similarity exceeds 0.92
    Then the new skill is rejected with reason "duplicate"

  Scenario: Ingestion gate rejects trivially short content
    When crystallization extracts a skill with content "Do testing"
    And the content length is under 20 characters
    Then the skill is rejected with reason "content_too_short"

  Scenario: Successful colony bumps retrieved skill confidence
    Given colony A retrieves skill S1 (confidence 0.5) during its rounds
    When colony A completes successfully
    Then S1 confidence is updated to 0.6
    And the update records algorithm_version "v1"

  Scenario: Failed colony reduces retrieved skill confidence
    Given colony B retrieves skill S1 (confidence 0.6) during its rounds
    When colony B fails
    Then S1 confidence is updated to 0.5

  Scenario: Confidence is clamped to valid range
    Given skill S2 has confidence 0.1
    When a failed colony reduces its confidence
    Then S2 confidence remains at 0.1 (clamped to minimum)

  Scenario: Colony observation hook fires on completion
    When any colony completes (success or failure)
    Then a structlog entry with key "colony_observation" is emitted
    And the entry contains colony_id, quality_score, skills_retrieved, and total_cost
