# Wave 33.5 Team 1 — Worker Caste Prompt Rewrite

## Role

You are rewriting the system prompts for the four worker castes (coder, reviewer, researcher, archivist) in `config/caste_recipes.yaml`. The current prompts are 5-line stubs with zero awareness of the knowledge system, tools, collaboration patterns, or institutional memory. You are upgrading them to 15-25 lines of dense, action-oriented, system-aware instruction — following the Queen prompt's style (85 lines at lines 9-89 of the same file).

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `config/caste_recipes.yaml` | MODIFY | Rewrite 4 worker caste `system_prompt` blocks |
| `tests/unit/config/test_caste_prompts.py` | CREATE | Verify prompt length, tool mentions, system awareness keywords |

## DO NOT TOUCH

- The Queen prompt (lines 9-89). It's being redesigned in a future wave.
- The `tools:` arrays for any caste. These are correct as-is.
- Temperature, max_tokens, max_iterations, max_execution_time_s, base_tool_calls_per_iteration for any caste.
- Any source file in `src/`. This is a YAML-only change.

---

## Current prompts and their tools

### Coder (lines 99-107, tools at line 110)

Current prompt (~5 lines):
```
You are a Coder agent in a FormicOS colony. Your role is to:
1. Read the task description and relevant context
2. Write clean, tested implementation code
3. Run tests and fix failures
4. Report your output concisely
Follow the project's coding standards. Write tests for your code.
Commit incrementally with descriptive messages.
```

Tools: `memory_search`, `memory_write`, `code_execute`, `knowledge_detail`, `transcript_search`, `artifact_inspect`

### Reviewer (lines 118-125, tools at line 128)

Current prompt (~5 lines). Similar stub.

Tools: `memory_search`, `knowledge_detail`, `transcript_search`, `artifact_inspect` (4 tools — read-only by design, no write tools)

### Researcher (lines 136-143, tools at line 146)

Current prompt (~5 lines). Similar stub.

Tools: `memory_search`, `memory_write`, `knowledge_detail`, `transcript_search`, `artifact_inspect`

### Archivist (lines 154-161, tools at line 164)

Current prompt (~5 lines). Similar stub.

Tools: `memory_search`, `memory_write`, `knowledge_detail`, `artifact_inspect` (4 tools — no transcript_search)

---

## Rewrite specifications

Each prompt must include these three sections in 15-25 lines total. Density over length — follow the Queen prompt's style of packing meaning into every line.

### Section 1: Tool awareness with usage guidance

List ALL tools the caste has access to, each with a 1-line usage hint. Examples:

```
Tools available to you:
- memory_search: Search institutional knowledge. Results are annotated with confidence
  tiers (HIGH/MODERATE/LOW/EXPLORATORY). Treat exploratory entries with appropriate skepticism.
- code_execute: Run code in the sandbox. All outputs are credential-scanned — never embed
  real API keys or secrets.
- memory_write: Store important findings for future colonies. Be specific — vague entries
  are noise; precise entries become durable skills.
```

Match the tool descriptions to what each tool actually does:
- `memory_search` — searches institutional knowledge (skills, experiences). Results have confidence levels.
- `memory_write` — stores findings for future colonies. Only coder, researcher, and archivist have this.
- `code_execute` — runs code in sandbox. Only coder has this. Outputs are credential-scanned.
- `knowledge_detail` — gets full details on a specific knowledge entry (confidence, provenance, observations).
- `transcript_search` — searches past colony transcripts. NOT for current colony data. NOT for general knowledge queries.
- `artifact_inspect` — examines artifacts from completed colonies.

### Section 2: System awareness (brief, not lecturing)

3-4 lines covering:
- Knowledge entries you access are tracked. Successful use strengthens confidence; if an entry seems wrong, say so explicitly.
- Your output will be scanned for extractable knowledge. Write clear conclusions, not just raw output.
- If retrieved knowledge seems irrelevant to your query, note it — this helps detect stale entries (prediction error signal).
- Credential scanning applies to all content — never include real secrets.

Tailor to the caste:
- **Coder**: Emphasize that clear conclusions in output get extracted as skills. Tool outputs are scanned for credentials.
- **Reviewer**: Emphasize that quality assessments influence knowledge promotion. Flagging outdated entries by name feeds back into confidence scoring.
- **Researcher**: Emphasize citing which knowledge entries were helpful. Distinguishing verified facts from preliminary findings.
- **Archivist**: Emphasize decay_class classification (ephemeral/stable/permanent), Beta(5,5) prior, precision over volume.

### Section 3: Collaboration context

1-2 lines:
- In stigmergic colonies, your output feeds into subsequent rounds. Other agents read what you write — be explicit about decisions and tradeoffs.
- Tailor to role: coder writes for reviewer; reviewer writes for future coders; researcher writes for the colony; archivist writes for the institution.

---

## Constraints

- Each prompt: 15-25 lines. Hard cap at 30 lines. Count lines in the YAML `system_prompt:` block.
- YAML multi-line string format: use `|` (literal block scalar) to preserve line breaks. The current prompts already use this format.
- Preserve the exact indentation level of the current prompts (2-space indent inside the caste block, 4-space indent for the prompt content).
- Do NOT add markdown formatting (headers, bold, etc.) inside prompts — agents receive these as plain text.
- Tool names must exactly match the caste's `tools:` array. Don't mention tools the caste doesn't have.

---

## Tests

Create `tests/unit/config/test_caste_prompts.py`:

```python
import yaml
from pathlib import Path

def test_caste_prompts():
    """Verify rewritten prompts meet specifications."""
    recipes = yaml.safe_load(Path("config/caste_recipes.yaml").read_text())

    for caste_name in ["coder", "reviewer", "researcher", "archivist"]:
        caste = recipes[caste_name]
        prompt = caste["system_prompt"]
        tools = caste["tools"]
        lines = [l for l in prompt.strip().split("\n") if l.strip()]

        # Length: 15-30 lines
        assert 15 <= len(lines) <= 30, f"{caste_name}: {len(lines)} lines"

        # Every tool mentioned in prompt
        for tool in tools:
            assert tool in prompt, f"{caste_name}: missing tool {tool}"

        # System awareness keywords
        assert "confidence" in prompt.lower(), f"{caste_name}: missing confidence awareness"
        assert "knowledge" in prompt.lower(), f"{caste_name}: missing knowledge awareness"

    # Queen prompt NOT modified (still starts with original first line)
    queen_prompt = recipes["queen"]["system_prompt"]
    assert "You are the Queen" in queen_prompt or "strategic" in queen_prompt.lower()
```

## Validation

```bash
python -c "import yaml; yaml.safe_load(open('config/caste_recipes.yaml'))"  # YAML parse check
pytest tests/unit/config/test_caste_prompts.py -v
ruff check src/ && pyright src/ && pytest
```
