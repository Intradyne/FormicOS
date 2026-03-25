"""Generate FormicOS eval task YAMLs from the Aider Polyglot Benchmark.

Usage::

    python scripts/generate_aider_tasks.py \\
        --benchmark-dir /path/to/polyglot-benchmark
    python scripts/generate_aider_tasks.py \\
        --benchmark-dir /path/to/polyglot-benchmark \\
        --lang python

Reads exercise directories from the polyglot-benchmark repo and generates:
  - One task YAML per exercise in config/eval/tasks/
  - One suite YAML in config/eval/suites/

Each task includes the exercise instructions, starter code, and test file
inline in the description, plus a verify_command for pass/fail evaluation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

# Test commands per language
LANG_TEST_COMMANDS: dict[str, str] = {
    "python": "python -m unittest {test_file} -v 2>&1",
    "go": "go test -v ./... 2>&1",
    "rust": "cargo test 2>&1",
    "java": "gradle test 2>&1",
    "javascript": "node {test_file} 2>&1",
    "cpp": "cmake -B build . && cmake --build build && cd build && ctest --output-on-failure 2>&1",
}

# Language-specific notes for the coder
LANG_HINTS: dict[str, str] = {
    "python": (
        "Write your solution in the starter file. The test file imports "
        "from the solution module. Run tests with workspace_execute."
    ),
    "go": (
        "Edit the .go file (not the test file). The package name must match. "
        "Run tests with: go test -v ./..."
    ),
    "rust": (
        "Edit src/lib.rs (or the starter file). Do not modify the test file. "
        "Run tests with: cargo test"
    ),
    "java": (
        "Edit the solution .java file. Do not modify the test file. "
        "Run tests with: gradle test"
    ),
    "javascript": (
        "Edit the solution .js file. Do not modify the test file. "
        "Run tests with node on the test file."
    ),
    "cpp": (
        "Edit the solution .cpp/.h files. Do not modify the test file. "
        "Build with cmake and run ctest."
    ),
}


def _read_text(path: Path) -> str:
    """Read file content, return empty string if missing."""
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _load_exercise_meta(exercise_dir: Path) -> dict:
    """Load .meta/config.json for an exercise."""
    meta_path = exercise_dir / ".meta" / "config.json"
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def generate_task_yaml(
    lang: str,
    exercise_name: str,
    exercise_dir: Path,
    seed_prefix: str = "",
) -> dict:
    """Generate a single task YAML dict for an exercise."""
    meta = _load_exercise_meta(exercise_dir)
    if not meta:
        return {}

    solution_files = meta.get("files", {}).get("solution", [])
    test_files = meta.get("files", {}).get("test", [])
    if not solution_files or not test_files:
        return {}

    # Read instructions
    instructions = ""
    for candidate in [
        exercise_dir / ".docs" / "instructions.md",
        exercise_dir / ".docs" / "instructions.append.md",
        exercise_dir / "README.md",
    ]:
        content = _read_text(candidate)
        if content:
            instructions += content + "\n\n"

    if not instructions.strip():
        return {}

    # Read starter code
    starter_sections = []
    for sf in solution_files:
        code = _read_text(exercise_dir / sf)
        starter_sections.append(f"FILE: {sf}\n```\n{code}\n```")

    # Read test code
    test_sections = []
    for tf in test_files:
        code = _read_text(exercise_dir / tf)
        test_sections.append(f"FILE: {tf}\n```\n{code}\n```")

    # Build test command
    test_cmd_template = LANG_TEST_COMMANDS.get(lang, "echo 'no test command'")
    test_cmd = test_cmd_template.format(test_file=test_files[0])

    # Build verify command (absolute path filled at runtime via workspace_seed)
    verify_cmd = test_cmd

    task_id = f"aider-{lang}-{exercise_name}"
    hint = LANG_HINTS.get(lang, "")

    description = f"""Solve the following Exercism coding exercise.

LANGUAGE: {lang}
EXERCISE: {exercise_name}

INSTRUCTIONS:
{instructions.strip()}

STARTER CODE:
{chr(10).join(starter_sections)}

TEST FILE:
{chr(10).join(test_sections)}

Your task: Edit the starter code file(s) so ALL tests pass.
Use write_workspace_file to write your solution, then use
workspace_execute to run the tests.

TEST COMMAND: {test_cmd}

If tests fail, read the error output carefully, fix your code,
and run the tests again.

{hint}

Use any Available Knowledge entries — they contain patterns
from prior exercises that may help you avoid common mistakes."""

    # Use seed_prefix to remap to container path if provided
    if seed_prefix:
        rel = f"{lang}/exercises/practice/{exercise_name}"
        seed_path = f"{seed_prefix}/{rel}"
    else:
        seed_path = str(exercise_dir).replace("\\", "/")

    task = {
        "id": task_id,
        "description": description,
        "difficulty": "moderate",
        "category": "code_implementation",
        "strategy": "sequential",
        "castes": [
            {
                "caste": "coder",
                "tier": "standard",
                "count": 1,
            },
        ],
        "success_rubric": "All tests pass with exit code 0",
        "budget_limit": 1.00,
        "max_rounds": 4,
        "eval_timeout_s": 180,
        "fast_path": True,
        # Aider benchmark extensions
        "quality_mode": "pass_fail",
        "verify_command": verify_cmd,
        "workspace_seed": seed_path,
    }
    return task


def generate_suite_yaml(
    suite_id: str,
    task_ids: list[str],
    description: str,
) -> dict:
    """Generate a suite YAML dict."""
    return {
        "id": suite_id,
        "description": description,
        "task_order": task_ids,
        "strategy": "sequential",
        "budget_per_task": 1.00,
        "max_rounds_per_task": 4,
        "escalation_policy": "none",
        "model_mix": {},  # inherit from config
        "quality_mode": "pass_fail",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate FormicOS eval tasks from Aider Polyglot Benchmark",
    )
    parser.add_argument(
        "--benchmark-dir",
        required=True,
        help="Path to polyglot-benchmark clone",
    )
    parser.add_argument(
        "--lang",
        default=None,
        help="Generate for single language (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: config/eval/)",
    )
    parser.add_argument(
        "--seed-prefix",
        default="",
        help="Container path prefix for workspace_seed "
        "(e.g. /benchmark)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be generated without writing",
    )
    args = parser.parse_args()

    benchmark_dir = Path(args.benchmark_dir)
    if not benchmark_dir.exists():
        print(f"Benchmark dir not found: {benchmark_dir}", file=sys.stderr)
        sys.exit(1)

    project_root = Path(__file__).resolve().parents[1]
    output_base = Path(args.output_dir) if args.output_dir else project_root / "config" / "eval"
    tasks_dir = output_base / "tasks"
    suites_dir = output_base / "suites"

    languages = [args.lang] if args.lang else list(LANG_TEST_COMMANDS.keys())

    all_task_ids: dict[str, list[str]] = {}  # lang -> [task_ids]
    total_generated = 0

    for lang in languages:
        practice_dir = benchmark_dir / lang / "exercises" / "practice"
        if not practice_dir.exists():
            print(f"No exercises found for {lang} at {practice_dir}", file=sys.stderr)
            continue

        lang_task_ids = []
        exercises = sorted(d.name for d in practice_dir.iterdir() if d.is_dir())

        for exercise_name in exercises:
            exercise_dir = practice_dir / exercise_name
            task = generate_task_yaml(
                lang, exercise_name, exercise_dir,
                seed_prefix=args.seed_prefix,
            )
            if not task:
                print(f"  SKIP {lang}/{exercise_name} (missing metadata)", file=sys.stderr)
                continue

            task_id = task["id"]
            lang_task_ids.append(task_id)

            if args.dry_run:
                print(f"  WOULD WRITE {task_id}.yaml")
            else:
                tasks_dir.mkdir(parents=True, exist_ok=True)
                task_path = tasks_dir / f"{task_id}.yaml"
                with task_path.open("w", encoding="utf-8") as fh:
                    yaml.dump(task, fh, default_flow_style=False, allow_unicode=True, width=120)
                total_generated += 1

        all_task_ids[lang] = lang_task_ids
        print(f"{lang}: {len(lang_task_ids)} exercises")

    # Generate per-language suites
    for lang, task_ids in all_task_ids.items():
        if not task_ids:
            continue
        suite_id = f"aider-{lang}"
        suite = generate_suite_yaml(
            suite_id=suite_id,
            task_ids=task_ids,
            description=f"Aider Polyglot Benchmark — {lang} ({len(task_ids)} exercises)",
        )
        if args.dry_run:
            print(f"  WOULD WRITE suite {suite_id}.yaml with {len(task_ids)} tasks")
        else:
            suites_dir.mkdir(parents=True, exist_ok=True)
            suite_path = suites_dir / f"{suite_id}.yaml"
            with suite_path.open("w", encoding="utf-8") as fh:
                yaml.dump(suite, fh, default_flow_style=False, allow_unicode=True, width=120)

    # Generate combined suite if multiple languages
    if len(all_task_ids) > 1:
        combined_ids = []
        for lang in languages:
            combined_ids.extend(all_task_ids.get(lang, []))
        if combined_ids:
            suite = generate_suite_yaml(
                suite_id="aider-polyglot",
                task_ids=combined_ids,
                description=(
                    f"Aider Polyglot Benchmark — all languages"
                    f" ({len(combined_ids)} exercises)"
                ),
            )
            if args.dry_run:
                print(f"  WOULD WRITE suite aider-polyglot.yaml with {len(combined_ids)} tasks")
            else:
                suite_path = suites_dir / "aider-polyglot.yaml"
                with suite_path.open("w", encoding="utf-8") as fh:
                    yaml.dump(suite, fh, default_flow_style=False, allow_unicode=True, width=120)

    if not args.dry_run:
        print(f"\nGenerated {total_generated} task YAMLs")
    else:
        total = sum(len(ids) for ids in all_task_ids.values())
        print(f"\nDry run: would generate {total} task YAMLs")


if __name__ == "__main__":
    main()
