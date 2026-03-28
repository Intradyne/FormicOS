"""Bootstrap knowledge hierarchy — offline LLM-only tool.

Wave 67: Assigns hierarchy_path values to existing knowledge entries by
grouping them by domain tag and asking an LLM to identify topic sub-clusters
within each domain. For 300 entries across 15 domains, this is ~15 LLM calls.

NOT imported by the runtime. Run manually:
    python scripts/bootstrap_hierarchy.py --workspace-id <id> [--base-url http://localhost:8080]

See ADR-049 for design rationale.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from typing import Any

import httpx


def _normalize_domain(raw: str) -> str:
    return re.sub(r"[\s\-]+", "_", raw.strip()).lower()


def _group_by_domain(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in entries:
        domains = e.get("domains", [])
        primary = domains[0] if domains else "uncategorized"
        normalized = _normalize_domain(primary)
        groups[normalized].append(e)
    return dict(groups)


def _build_cluster_prompt(domain: str, entries: list[dict[str, Any]]) -> str:
    entry_summaries = []
    for e in entries[:30]:  # cap per-batch to avoid prompt overflow
        title = e.get("title", "untitled")
        summary = e.get("summary", "")[:100]
        entry_summaries.append(f"  - [{e.get('id', '?')[:12]}] {title}: {summary}")

    entries_text = "\n".join(entry_summaries)
    return f"""You are organizing knowledge entries for the domain "{domain}".

Below are {len(entry_summaries)} entries in this domain. Identify 2-5 topic
sub-clusters that naturally group these entries. Each entry should belong to
exactly one topic.

Entries:
{entries_text}

Respond with a JSON array of objects, each with:
- "topic": short topic name (lowercase, underscores, no spaces)
- "entry_ids": list of entry ID prefixes that belong to this topic

Example:
[
  {{"topic": "authentication", "entry_ids": ["abc123", "def456"]}},
  {{"topic": "testing", "entry_ids": ["ghi789"]}}
]

Return ONLY the JSON array, no other text."""


def _assign_hierarchy_paths(
    domain: str,
    entries: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
) -> dict[str, str]:
    """Map entry IDs to hierarchy paths based on cluster assignments."""
    id_to_path: dict[str, str] = {}

    # Build reverse lookup: entry_id_prefix -> full entry_id
    full_ids = {e.get("id", ""): e.get("id", "") for e in entries}

    for cluster in clusters:
        topic = _normalize_domain(cluster.get("topic", "misc"))
        path = f"/{domain}/{topic}/"
        for prefix in cluster.get("entry_ids", []):
            # Match prefix to full ID
            for full_id in full_ids:
                if full_id.startswith(prefix):
                    id_to_path[full_id] = path
                    break

    # Entries not assigned to any cluster get domain-only path
    for e in entries:
        eid = e.get("id", "")
        if eid and eid not in id_to_path:
            id_to_path[eid] = f"/{domain}/"

    return id_to_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap knowledge hierarchy paths")
    parser.add_argument("--workspace-id", required=True, help="Workspace ID")
    parser.add_argument("--base-url", default="http://localhost:8080", help="FormicOS base URL")
    parser.add_argument("--dry-run", action="store_true", help="Print assignments without applying")
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url, timeout=30.0)

    # Fetch entries
    print(f"Fetching entries for workspace {args.workspace_id}...")
    resp = client.get(f"/api/v1/workspaces/{args.workspace_id}/knowledge")
    if resp.status_code != 200:
        print(f"Failed to fetch entries: {resp.status_code}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    entries = data.get("entries", data.get("items", []))
    print(f"  Found {len(entries)} entries")

    if not entries:
        print("No entries to process.")
        return

    # Group by domain
    groups = _group_by_domain(entries)
    print(f"  {len(groups)} domains: {', '.join(sorted(groups.keys()))}")

    # Process each domain
    all_assignments: dict[str, str] = {}
    for domain, domain_entries in sorted(groups.items()):
        if len(domain_entries) < 3:
            # Too few entries for sub-clustering — assign domain-level path
            for e in domain_entries:
                all_assignments[e.get("id", "")] = f"/{domain}/"
            print(f"  [{domain}] {len(domain_entries)} entries — too few, using domain-level path")
            continue

        prompt = _build_cluster_prompt(domain, domain_entries)
        print(f"  [{domain}] {len(domain_entries)} entries — requesting LLM clustering...")

        # The bootstrap script uses the FormicOS LLM endpoint if available,
        # or falls back to a simple domain-level assignment.
        try:
            # Try to call a simple LLM completion endpoint
            llm_resp = client.post("/api/v1/llm/complete", json={
                "prompt": prompt,
                "max_tokens": 1024,
            }, timeout=60.0)

            if llm_resp.status_code == 200:
                result_text = llm_resp.json().get("text", "[]")
                # Parse JSON from response
                try:
                    clusters = json.loads(result_text)
                except json.JSONDecodeError:
                    # Try to extract JSON array from response
                    match = re.search(r"\[.*\]", result_text, re.DOTALL)
                    clusters = json.loads(match.group()) if match else []

                assignments = _assign_hierarchy_paths(domain, domain_entries, clusters)
                all_assignments.update(assignments)
                topics = {v.split("/")[2] for v in assignments.values() if v.count("/") >= 3}
                print(f"    → {len(topics)} topics: {', '.join(sorted(topics))}")
            else:
                # Fallback: domain-level only
                for e in domain_entries:
                    all_assignments[e.get("id", "")] = f"/{domain}/"
                print(f"    → LLM unavailable ({llm_resp.status_code}), using domain-level path")
        except Exception as exc:
            for e in domain_entries:
                all_assignments[e.get("id", "")] = f"/{domain}/"
            print(f"    → LLM error ({exc}), using domain-level path")

    # Report
    print(f"\nTotal assignments: {len(all_assignments)}")
    unique_paths = sorted(set(all_assignments.values()))
    print(f"Unique paths ({len(unique_paths)}):")
    for p in unique_paths:
        count = sum(1 for v in all_assignments.values() if v == p)
        print(f"  {p} ({count} entries)")

    if args.dry_run:
        print("\n[DRY RUN] No changes applied.")
        return

    # Apply: update entries via REST API
    print("\nApplying hierarchy paths...")
    updated = 0
    for entry_id, path in all_assignments.items():
        if not entry_id:
            continue
        try:
            patch_resp = client.patch(
                f"/api/v1/workspaces/{args.workspace_id}/knowledge/{entry_id}",
                json={"hierarchy_path": path},
                timeout=10.0,
            )
            if patch_resp.status_code in (200, 204):
                updated += 1
            else:
                print(f"  Warning: failed to update {entry_id[:12]}: {patch_resp.status_code}")
        except Exception as exc:
            print(f"  Warning: error updating {entry_id[:12]}: {exc}")

    print(f"Done. Updated {updated}/{len(all_assignments)} entries.")


if __name__ == "__main__":
    main()
