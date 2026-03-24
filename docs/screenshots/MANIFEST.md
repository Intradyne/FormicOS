# Screenshot Manifest

Planned screenshots for README and documentation. These should be captured from
a real running FormicOS instance during a demo workspace session.

## Shot List

### 1. queen-overview-demo.png
**Description:** Queen landing page showing the "Try the Demo" entry point, resource grid, and proactive briefing with the contradiction insight visible.
**Caption:** "The Queen landing page surfaces proactive intelligence and offers a guided demo."

### 2. dag-execution.png
**Description:** Workflow DAG mid-execution — some nodes pulsing blue (running), one green (completed), dependency arrows colored, cost accumulator visible.
**Caption:** "Parallel execution plan with live colony status, phase labels, and running cost."

### 3. knowledge-contradiction.png
**Description:** Proactive briefing showing the JWT vs session-cookies contradiction with confidence posteriors visible.
**Caption:** "Proactive intelligence detects conflicting high-confidence knowledge entries."

### 4. colony-completion.png
**Description:** Completed DAG with all nodes green, knowledge extraction annotations (entries count), and total cost footer.
**Caption:** "Colonies completed — knowledge extracted, cost tracked, ready for retrieval."

### 5. self-maintenance.png
**Description:** Maintenance colony visible in the service section, proactive briefing showing the contradiction being resolved.
**Caption:** "Self-maintenance spawns a research colony to investigate and resolve the contradiction."

### 6. demo-guide-bar.png
**Description:** The demo annotation bar showing a mid-flow step with progress pips and hint text.
**Caption:** "The guided demo bar explains what's happening without taking over the interface."

### 7. active-plans-minidag.png
**Description:** Active Plans section on the Queen overview showing a compact mini-DAG with status-colored nodes.
**Caption:** "Active Plans show compact DAG progress at a glance."

## Capture Instructions

1. Start FormicOS: `docker compose up -d`
2. Open http://localhost:8080
3. Click "Try the Demo" on the Queen landing page
4. Capture screenshots at each demo step
5. Use browser DevTools to set viewport to 1280x800
6. Save as PNG with descriptive filenames matching this manifest
7. Place in this directory

## Placeholder Status

No real screenshots have been captured yet. This manifest serves as a shot list
for when a running instance is available for capture.
