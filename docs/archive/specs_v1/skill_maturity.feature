Feature: Skill bank maturity -- Bayesian confidence and LLM deduplication
  Skill confidence uses Beta distribution for statistical rigor. Near-duplicate
  skills are classified by LLM before ingestion. The skill browser shows
  uncertainty and merge history.

  Background:
    Given the Qdrant vector backend is active
    And the skill_bank collection exists with payload indexes

  # --- Bayesian confidence ---

  Scenario: New skill initializes with default Beta prior
    Given no skills exist in the skill bank
    When a colony completes and crystallizes a skill
    Then the skill has conf_alpha 5.0 and conf_beta 5.0
    And the derived confidence is 0.5

  Scenario: Existing skills migrate to Beta distribution on first access
    Given a skill exists with flat confidence 0.7 and no conf_alpha field
    When the confidence migration runs
    Then the skill has conf_alpha 7.0 and conf_beta 3.0
    And the derived confidence remains 0.7

  Scenario: Colony success increases alpha
    Given a skill was retrieved during colony "col_1"
    And colony "col_1" completes successfully
    When skill confidence is updated
    Then conf_alpha increases by 1.0
    And conf_beta is unchanged
    And the derived confidence increases

  Scenario: Colony failure increases beta
    Given a skill was retrieved during colony "col_2"
    And colony "col_2" fails
    When skill confidence is updated
    Then conf_beta increases by 1.0
    And conf_alpha is unchanged
    And the derived confidence decreases

  Scenario: SkillConfidenceUpdated event fires once per colony completion
    Given 3 skills were retrieved during colony "col_1"
    When colony "col_1" completes
    Then exactly one SkillConfidenceUpdated event is emitted
    And skills_updated is 3
    And colony_succeeded is true

  Scenario: Uncertainty decreases with more observations
    Given skill A has conf_alpha 2.0 and conf_beta 2.0
    And skill B has conf_alpha 50.0 and conf_beta 50.0
    Then skill A has higher uncertainty than skill B
    And both have derived confidence approximately 0.5

  # --- UCB exploration bonus ---

  Scenario: Under-observed skills get retrieval boost
    Given skill A has 2 observations and confidence 0.5
    And skill B has 100 observations and confidence 0.5
    When both are candidates for the same query
    Then skill A's composite score includes a positive exploration bonus
    And skill A's exploration bonus is larger than skill B's

  Scenario: Exploration bonus decays with observations
    Given a skill starts with 1 observation
    When the skill accumulates 20 observations
    Then the exploration bonus has decreased substantially

  # --- Two-band deduplication ---

  Scenario: Exact duplicate is silently skipped (Band 1)
    Given a skill exists with text "Use dependency injection for testability"
    When a candidate skill has cosine similarity >= 0.98 with the existing skill
    Then the candidate is not ingested
    And no LLM call is made
    And structlog logs a NOOP with reason "exact_duplicate"

  Scenario: Semantic near-match triggers LLM classification (Band 2)
    Given a skill exists with text "Use dependency injection for testability"
    When a candidate has cosine similarity 0.90 with the existing skill
    Then an LLM classification call is made
    And the call includes both skill texts

  Scenario: LLM classifies candidate as ADD
    Given LLM classification returns "ADD"
    When the candidate is processed
    Then the candidate is ingested as a new skill
    And the existing skill is unchanged

  Scenario: LLM classifies candidate as UPDATE
    Given LLM classification returns "UPDATE"
    When the candidate is processed
    Then the existing skill text is replaced with a merged version
    And the existing skill is re-embedded
    And the Beta distributions are combined
    And a SkillMerged event is emitted
    And structlog logs the merge with both skill IDs

  Scenario: LLM classifies candidate as NOOP
    Given LLM classification returns "NOOP"
    When the candidate is processed
    Then the candidate is not ingested
    And structlog logs a NOOP with reason "llm_classified_redundant"

  Scenario: LLM dedup uses Gemini Flash by default
    Given GEMINI_API_KEY is configured
    When an LLM classification call is made
    Then the call routes to gemini/gemini-2.5-flash
    And the cost per classification is under $0.001

  Scenario: LLM dedup falls back to local model
    Given GEMINI_API_KEY is not configured
    When an LLM classification call is made
    Then the call routes to the local model
    And classification still returns ADD, UPDATE, or NOOP

  Scenario: Below-threshold candidate ingests normally
    Given a candidate has cosine similarity 0.75 with the closest existing skill
    Then the candidate is ingested as a new skill
    And no LLM classification is performed

  # --- Beta distribution merge on UPDATE ---

  Scenario: UPDATE combines Beta distributions correctly
    Given existing skill has conf_alpha 10.0 and conf_beta 5.0
    And candidate skill has conf_alpha 3.0 and conf_beta 2.0
    When LLM classifies as UPDATE and merge completes
    Then the merged skill has conf_alpha 12.0 and conf_beta 6.0

  # --- Skill browser display ---

  Scenario: Skill browser shows confidence with uncertainty
    Given a skill has conf_alpha 5.0 and conf_beta 2.0
    When the skill browser renders
    Then confidence shows as approximately 0.71
    And an uncertainty indicator is visible

  Scenario: Skill browser shows merge badge
    Given a skill was created by merging two other skills
    When the skill browser renders
    Then a "merged" badge is visible on the skill card

  Scenario: Skills API returns Beta distribution fields
    When GET /api/v1/skills is called
    Then each skill entry includes conf_alpha, conf_beta, and confidence
