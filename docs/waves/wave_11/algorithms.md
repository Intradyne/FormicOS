# Wave 11 Algorithms -- Implementation Reference

**Companion to:** `docs/waves/wave_11/plan.md`
**Purpose:** Concrete patterns for each terminal. Adapt to the codebase you find.

---

## A1. Beta Distribution Confidence -- Core Math

All arithmetic uses stdlib `math`. No scipy, no numpy.

```python
import math
import time

class SkillConfidence:
    """Beta distribution confidence tracker.

    alpha = success count + prior
    beta_param = failure count + prior
    score = alpha / (alpha + beta_param)  # posterior mean
    """

    def __init__(self, alpha: float = 5.0, beta_param: float = 5.0):
        self.alpha = alpha
        self.beta_param = beta_param

    @classmethod
    def from_flat(cls, confidence: float, prior_strength: float = 10.0) -> "SkillConfidence":
        """Migrate flat confidence to Beta params."""
        alpha = confidence * prior_strength
        beta_param = (1.0 - confidence) * prior_strength
        return cls(alpha=max(alpha, 0.1), beta_param=max(beta_param, 0.1))

    @property
    def score(self) -> float:
        return self.alpha / (self.alpha + self.beta_param)

    @property
    def uncertainty(self) -> float:
        a, b = self.alpha, self.beta_param
        return (a * b) / ((a + b) ** 2 * (a + b + 1))

    @property
    def observations(self) -> float:
        return self.alpha + self.beta_param - 2.0  # subtract prior

    def update(self, success: bool, weight: float = 1.0) -> None:
        if success:
            self.alpha += weight
        else:
            self.beta_param += weight

    @staticmethod
    def combine(a: "SkillConfidence", b: "SkillConfidence") -> "SkillConfidence":
        """Combine two Beta distributions (for merge dedup)."""
        return SkillConfidence(
            alpha=a.alpha + b.alpha - 1.0,
            beta_param=a.beta_param + b.beta_param - 1.0,
        )
```

### Migration from flat confidence

```python
async def migrate_flat_to_beta(vector_port, collection: str = "skill_bank"):
    """One-time migration: add conf_alpha/conf_beta to skills missing them."""
    # Use a broad search to find skills without conf_alpha
    # For each skill:
    #   conf = payload.get("confidence", 0.5)
    #   alpha = conf * 10.0
    #   beta = (1.0 - conf) * 10.0
    #   upsert with new fields: conf_alpha, conf_beta, conf_last_validated
    # This is idempotent -- skills that already have conf_alpha are skipped.
```

Run at startup if any skill is missing `conf_alpha`. The check is a single Qdrant query with a `must_not` filter on `conf_alpha` existence.

---

## A2. UCB Exploration Bonus in Composite Scoring

The existing composite formula from Wave 9:
```python
composite = 0.50 * semantic + 0.25 * confidence + 0.25 * freshness
```

Wave 11 adds an exploration term:
```python
import math

def composite_score(
    semantic_sim: float,
    confidence: float,
    freshness: float,
    n_observations: float,
    total_colonies: int,
    ucb_c: float = 0.1,
) -> float:
    """Composite retrieval score with UCB exploration bonus.

    Parameters:
        semantic_sim: cosine similarity [0, 1]
        confidence: alpha / (alpha + beta) [0, 1]
        freshness: exp(-lambda * hours) [0, 1]
        n_observations: alpha + beta - 2 (prior-subtracted)
        total_colonies: completed colony count from projection store
        ucb_c: exploration weight (small -- nudge, don't dominate)
    """
    n = max(n_observations, 1.0)
    N = max(total_colonies, 1)
    exploration = ucb_c * math.sqrt(math.log(N) / n)

    return (
        0.50 * semantic_sim
        + 0.25 * confidence
        + 0.20 * freshness
        + 0.05 * min(exploration, 1.0)  # cap exploration contribution
    )
```

**Threading `total_colonies` into context assembly:**

The colony_manager knows the total colony count from the projection store. Pass it as a parameter:

```python
# In colony_manager._run_colony_inner(), before calling run_round:
total_colonies = len(self._runtime.projection_store.colonies)

# Thread through to assemble_context via RoundRunner
# Add total_colonies: int = 0 parameter to run_round or RoundRunner.__init__
```

---

## A3. Two-Band Dedup -- Decision Flow

```text
candidate_skill arrives for ingestion
-> search skill_bank for top-5 by cosine similarity
-> highest_cosine = max(hit.score for hit in results)

if cosine >= 0.98:
  -> NOOP (Band 1: exact duplicate)
  -> log "dedup_exact"
  -> no LLM call

if cosine in [0.82, 0.98):
  -> LLM classify via skill_dedup.classify(existing, candidate)
  -> if "ADD": ingest candidate as new skill
  -> if "NOOP": skip and log "dedup_llm_noop"
  -> if "UPDATE":
     1. skill_dedup.merge_texts(existing, candidate)
     2. re-embed merged text
     3. combine Beta distributions
     4. upsert merged skill to Qdrant
     5. emit SkillMerged event (if available)
     6. log "dedup_llm_update"

if cosine < 0.82:
  -> ADD (genuinely new)
  -> ingest normally, no LLM call
```

### LLM Classification Prompt

```python
CLASSIFY_SYSTEM = "You are a skill deduplication classifier. Respond with exactly one word."

CLASSIFY_USER = """Compare these two skill descriptions:

EXISTING: {existing_text}
CANDIDATE: {candidate_text}

Classify as:
ADD -- candidate contains genuinely new information not in existing
UPDATE -- candidate improves, extends, or corrects existing
NOOP -- candidate is redundant with existing

Respond with one word only:"""
```

Parse response: strip whitespace, uppercase, validate against {"ADD", "UPDATE", "NOOP"}. On parse failure (LLM returned prose), default to ADD (safe -- worst case is a duplicate that future dedup catches).

### Merge Text Prompt

```python
MERGE_USER = """Combine these two skills into one comprehensive skill description.
Preserve all specific details, thresholds, tool names, and error conditions.

SKILL A: {text_a}
SKILL B: {text_b}

Write one merged skill (50-200 words):"""
```

### Beta Distribution Merge

When two skills merge via UPDATE:
```python
# Additive combination minus shared prior
merged = SkillConfidence(
    alpha = existing.conf_alpha + candidate.conf_alpha - 1.0,
    beta_param = existing.conf_beta + candidate.conf_beta - 1.0,
)
# Derived confidence updates automatically
merged_confidence = merged.score
```

---

## A4. Colony Template Storage

### YAML format

```yaml
# config/templates/code-review.yaml
template_id: "tmpl-e7f3a9b2"
name: "Code Review"
description: "Coder + Reviewer pair for implementation and quality review."
version: 1
caste_names:
  - coder
  - reviewer
strategy: "stigmergic"
budget_limit: 1.0
max_rounds: 15
tags:
  - code
  - review
source_colony_id: null
created_at: "2026-03-14T12:00:00Z"
use_count: 0
```

### Template manager core functions

```python
import yaml
from pathlib import Path

TEMPLATE_DIR = Path("config/templates")

async def load_templates() -> list[ColonyTemplate]:
    """Read all YAML files from config/templates/. Return latest version per ID."""
    templates: dict[str, ColonyTemplate] = {}
    if not TEMPLATE_DIR.exists():
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        return []
    for path in TEMPLATE_DIR.glob("*.yaml"):
        with open(path) as f:
            data = yaml.safe_load(f)
        tmpl = ColonyTemplate(**data)
        existing = templates.get(tmpl.template_id)
        if existing is None or tmpl.version > existing.version:
            templates[tmpl.template_id] = tmpl
    return list(templates.values())

async def save_template(tmpl: ColonyTemplate, runtime) -> None:
    """Write template YAML and emit ColonyTemplateCreated."""
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{tmpl.template_id}-v{tmpl.version}.yaml"
    path = TEMPLATE_DIR / filename
    with open(path, "w") as f:
        yaml.dump(tmpl.model_dump(), f, default_flow_style=False, sort_keys=False)
    await runtime.emit_and_broadcast(ColonyTemplateCreated(...))

async def save_from_colony(colony_projection, runtime, llm_port) -> ColonyTemplate:
    """Create template from completed colony. LLM generates description."""
    # Extract config from ColonySpawned event data in projection
    # LLM call for description (Gemini Flash, cheap)
    # Save and return
```

### Immutable versioning

Editing a template means:
1. Load the current version
2. Apply changes
3. Increment `version`
4. Save as a new YAML file (old file untouched)
5. Emit `ColonyTemplateCreated` for the new version

The `load_templates()` function returns the highest version per `template_id`.

---

## A5. Queen Colony Naming

```python
async def name_colony(
    llm_port,
    colony_id: str,
    task: str,
    model: str = "gemini/gemini-2.5-flash",
    fallback_model: str = "llama-cpp/gpt-4",
) -> str | None:
    """Generate a 2-4 word project name for a colony.

    Returns name string or None on failure. Caller decides fallback display.
    """
    prompt = (
        "Generate a short, memorable project name (2-4 words, no quotes) "
        f"for a colony working on: {task}"
    )
    for model_addr in [model, fallback_model]:
        try:
            response = await asyncio.wait_for(
                llm_port.complete(
                    model=model_addr,
                    messages=[LLMMessage(role="user", content=prompt)],
                    temperature=0.3,
                    max_tokens=20,
                ),
                timeout=0.5,
            )
            name = response.content.strip().strip("\"'").strip()
            if 2 <= len(name) <= 50 and "\n" not in name:
                return name
        except (asyncio.TimeoutError, Exception):
            continue
    return None
```

After naming:
```python
if display_name:
    await runtime.emit_and_broadcast(ColonyNamed(
        seq=0,
        type="ColonyNamed",
        timestamp=utcnow(),
        address=colony_address,
        colony_id=colony_id,
        display_name=display_name,
        named_by="queen",
    ))
```

The frontend receives `ColonyNamed` via WebSocket and updates the colony card. Name shimmer -> real name typically takes < 1 second.

---

## A6. Suggest-Team Endpoint

```python
async def suggest_team(
    llm_port,
    objective: str,
    castes: dict[str, CasteRecipe],
    model: str = "gemini/gemini-2.5-flash",
) -> list[dict]:
    """Recommend castes for a given objective."""
    caste_desc = "\n".join(
        f"- {name}: {c.description}" for name, c in castes.items()
        if name != "queen"  # Queen is not a colony worker
    )
    prompt = f"""Given this objective, recommend which castes to include in a colony.

Available castes:
{caste_desc}

Objective: {objective}

Respond as a JSON array. Each entry: {{"caste": "name", "count": 1, "reasoning": "brief why"}}
Include only castes that are genuinely needed. Typical colony size is 2-4 agents."""

    response = await llm_port.complete(
        model=model,
        messages=[LLMMessage(role="user", content=prompt)],
        temperature=0.0,
        max_tokens=500,
    )

    # Use defensive parser to handle potential JSON issues
    from formicos.adapters.parse_defensive import parse_tool_calls_defensive
    # Or simpler: json_repair.loads() since the response should be a JSON array
    import json_repair
    try:
        result = json_repair.loads(response.content)
        if isinstance(result, list):
            return result
    except Exception:
        pass

    # Fallback: return a safe default
    return [
        {"caste": "coder", "count": 1, "reasoning": "Default implementation agent"},
        {"caste": "reviewer", "count": 1, "reasoning": "Default quality gate"},
    ]
```

---

## A7. Frontend Colony Creation Flow -- Component Structure

```text
<colony-creator> (new top-level component)
  Step 1: <objective-input>
    - on submit -> POST /api/v1/suggest-team
    - on submit -> GET /api/v1/templates

  Step 2: <team-configurator>
    - suggested castes (default)
    - or template castes (if selected)
    - add/remove caste buttons
    - budget input
    - template badge ("from Code Review v2")

  Step 3: <launch-confirm>
    - spawn_colony WS command (with optional template_id)
    - name shimmer -> ColonyNamed event -> display update
    - auto-navigate to colony-detail
```

Each step is a state in the parent component, not a separate route. The component manages step transitions via `@state() private step: 1 | 2 | 3 = 1`.

The suggest-team result and template list are fetched in parallel on Step 1 submit. Step 2 renders whichever arrives first, then updates when both are available.

---

## A8. Skill Browser -- Uncertainty Display

```typescript
// In skill-browser.ts, render uncertainty bar:

private renderConfidence(skill: SkillEntry) {
  const mean = skill.confidence;
  const uncertainty = skill.uncertainty || 0;
  const stddev = Math.sqrt(uncertainty);
  const barWidth = Math.max(stddev * 400, 2); // scale for visibility

  return html`
    <div class="confidence-display">
      <span class="conf-mean">${mean.toFixed(2)}</span>
      <div class="conf-bar-container">
        <div class="conf-bar-fill"
             style="width: ${mean * 100}%"
             class="${mean >= 0.6 ? 'high' : mean >= 0.3 ? 'mid' : 'low'}">
        </div>
        <div class="uncertainty-range"
             style="left: ${(mean - stddev) * 100}%; width: ${barWidth}%"
             title="+/-${stddev.toFixed(3)} (${(skill.conf_alpha + skill.conf_beta - 2).toFixed(0)} observations)">
        </div>
      </div>
    </div>
  `;
}
```

Narrow uncertainty bar = many observations = well-established skill.
Wide uncertainty bar = few observations = needs more data.
