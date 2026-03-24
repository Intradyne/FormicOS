# Wave 14 Colony Chat — Persistence

Feature: Colony chat persistence

  Scenario: Chat history survives restart
    Given a colony has received 5 chat messages (2 system, 2 operator, 1 service)
    When the system restarts and replays events
    Then the ColonyChatViewRegistry rebuilds the colony's chat with all 5 messages
    And the messages are in chronological order by seq

  Scenario: Chat view returns messages after a sequence number
    Given a colony has 10 chat messages with seq 1–10
    When chat history is requested with after_seq 7
    Then only messages with seq 8, 9, 10 are returned
