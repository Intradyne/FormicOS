Feature: Tree navigation (S1)
  The operator navigates the tree: System → Workspace → Thread → Colony.
  Selecting a node shows that node's state in the main panel.

  Scenario: Navigate from workspace to colony
    Given a workspace "research" with thread "main" and colony "alpha"
    When I select "research" in the sidebar
    Then the main panel shows workspace config and thread list
    When I select thread "main"
    Then the main panel shows Queen chat and colony list
    When I select colony "alpha"
    Then the main panel shows topology, rounds, and metrics

  Scenario: Breadcrumb navigation
    Given I am viewing colony "alpha" in thread "main" of workspace "research"
    Then the breadcrumb shows "research > main > alpha"
    When I click "main" in the breadcrumb
    Then the main panel shows the thread view

  Scenario: Sidebar collapse
    When I collapse the sidebar
    Then it shows an icon rail with status dots for running colonies
    When I expand the sidebar
    Then the full tree is visible again
