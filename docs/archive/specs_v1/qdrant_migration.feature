Feature: Qdrant vector store migration
  The skill bank and vector search operations use Qdrant via the VectorPort
  interface, replacing LanceDB with payload-filtered search and tenant indexing.

  Background:
    Given the Qdrant container is running and healthy on port 6333
    And the vector backend config is set to "qdrant"
    And the skill_bank collection exists with COSINE distance and 1024 dimensions

  Scenario: Skill upsert stores document with payload metadata
    Given a VectorDocument with content "Use dependency injection for testability"
    And metadata confidence 0.7 and algorithm_version "v1" and namespace "ws_default"
    When the document is upserted to the skill_bank collection
    Then the Qdrant collection contains a point with the document ID
    And the point payload includes confidence 0.7
    And the point payload includes namespace "ws_default"

  Scenario: Skill search returns ranked results with payload
    Given 5 skills exist in the skill_bank collection
    When a search is performed for "testing best practices" with top_k 3
    Then 3 results are returned
    And each result has a score between 0.0 and 1.0
    And each result includes payload fields confidence and source_colony

  Scenario: Payload-filtered search excludes source colony
    Given skill A from colony "col_1" and skill B from colony "col_2"
    When a search is performed excluding source_colony "col_1"
    Then skill A is not in the results
    And skill B is in the results

  Scenario: Confidence range filter narrows results
    Given skills with confidence values 0.2, 0.5, 0.8
    When a search is performed with confidence range 0.3 to 1.0
    Then only skills with confidence >= 0.3 are returned

  Scenario: Namespace isolation prevents cross-workspace leakage
    Given skill X in namespace "workspace_a" and skill Y in namespace "workspace_b"
    When a search is performed in namespace "workspace_a"
    Then only skill X is returned

  Scenario: Graceful degradation when Qdrant is unreachable
    Given the Qdrant container is stopped
    When a search is performed
    Then an empty result list is returned
    And a warning is logged with message containing "Qdrant unavailable"

  Scenario: Migration transfers LanceDB data without re-embedding
    Given 10 skills exist in the LanceDB skill_bank table
    When the migration script runs
    Then the Qdrant skill_bank collection contains 10 points
    And each point has the same vector as the LanceDB source
    And each point has payload fields matching the LanceDB metadata

  Scenario: Collection creation is idempotent
    Given the skill_bank collection already exists
    When ensure_collection is called again
    Then no error is raised
    And the collection configuration is unchanged

  Scenario: Feature flag switches vector backend
    Given vector.backend is set to "qdrant" in formicos.yaml
    When the application starts
    Then the VectorPort is backed by QdrantVectorPort
    And skill retrieval uses Qdrant query_points
