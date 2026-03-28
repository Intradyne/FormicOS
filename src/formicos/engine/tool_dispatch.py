"""Tool specification registry and permission checking.

Extracted from runner.py for navigability.
Contains tool specs, category mappings, caste policies, and permission checks.
"""

from __future__ import annotations

from formicos.core.types import (
    CasteToolPolicy,
    LLMToolSpec,
    ToolCategory,
)

# ---------------------------------------------------------------------------
# Tool spec registry (ADR-007, algorithms.md §1.1)
# ---------------------------------------------------------------------------

TOOL_SPECS: dict[str, LLMToolSpec] = {
    "memory_search": {
        "name": "memory_search",
        "description": (
            "Search colony scratch memory, workspace library, and skill bank "
            "for relevant knowledge. Returns up to top_k results ranked by similarity."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum results to return (1-10)",
                    "default": 5,
                },
                "detail": {
                    "type": "string",
                    "enum": ["auto", "summary", "standard", "full"],
                    "description": (
                        "Retrieval detail level. auto (default) starts "
                        "cheap and escalates. summary (~15 tokens/result)"
                        ", standard (~75), full (~200+)."
                    ),
                    "default": "auto",
                },
            },
            "required": ["query"],
        },
    },
    "memory_write": {
        "name": "memory_write",
        "description": (
            "Store a piece of knowledge in this colony's private scratch memory. "
            "Use for findings, decisions, and reusable patterns."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The knowledge to store. Be specific and self-contained.",
                },
                "metadata_type": {
                    "type": "string",
                    "description": "Category: finding, decision, pattern, or note",
                    "enum": ["finding", "decision", "pattern", "note"],
                },
            },
            "required": ["content"],
        },
    },
    "code_execute": {
        "name": "code_execute",
        "description": (
            "Execute Python code in a sandboxed container. "
            "Returns stdout, stderr, and exit code. "
            "Only standard library and pre-installed packages available."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python source code to execute.",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Execution timeout in seconds (max 30).",
                    "default": 10,
                },
            },
            "required": ["code"],
        },
    },
    "query_service": {
        "name": "query_service",
        "description": (
            "Query a service colony. Service colonies are completed colonies "
            "activated as persistent services that retain their tools and knowledge."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service_type": {
                    "type": "string",
                    "description": "Service type to query (e.g. research, review, docs).",
                },
                "query": {
                    "type": "string",
                    "description": "The query text.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 30, max 60).",
                    "default": 30,
                },
            },
            "required": ["service_type", "query"],
        },
    },
    "http_fetch": {
        "name": "http_fetch",
        "description": (
            "Fetch content from a URL. Returns text. Respects domain allowlist."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch",
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "Max response bytes (default 50000)",
                },
            },
            "required": ["url"],
        },
    },
    "file_read": {
        "name": "file_read",
        "description": "Read a file from the workspace library by name.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "File name to read",
                },
            },
            "required": ["filename"],
        },
    },
    "file_write": {
        "name": "file_write",
        "description": (
            "Write a named file to the workspace. "
            "Extension whitelist and size cap enforced."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "File name, e.g. 'output.py'",
                },
                "content": {
                    "type": "string",
                    "description": "File content",
                },
            },
            "required": ["filename", "content"],
        },
    },
    "knowledge_detail": {
        "name": "knowledge_detail",
        "description": (
            "Retrieve the full content of a knowledge item by its ID. "
            "The [Available Knowledge] section in your context lists relevant "
            "entries with their IDs. Call this tool when an entry looks "
            "relevant to your current task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": (
                        "Knowledge item ID (e.g., mem-abc-s-0)"
                    ),
                },
            },
            "required": ["item_id"],
        },
    },
    "transcript_search": {
        "name": "transcript_search",
        "description": (
            "Search past colony transcripts for relevant approaches and patterns. "
            "Returns colony IDs and snippets -- use artifact_inspect to see full details. "
            "Do NOT use this tool for the current colony's data (use memory_search instead) "
            "or for general knowledge queries (use knowledge_detail instead)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (keywords work best)",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max results (1-5)",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
    "knowledge_feedback": {
        "name": "knowledge_feedback",
        "description": (
            "Report whether a retrieved knowledge entry was useful. "
            "Positive feedback strengthens confidence. Negative feedback "
            "signals staleness. Use when an entry was notably helpful or wrong."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entry_id": {
                    "type": "string",
                    "description": "The knowledge entry ID",
                },
                "helpful": {
                    "type": "boolean",
                    "description": "True if useful, false if wrong/outdated",
                },
                "reason": {
                    "type": "string",
                    "description": "Brief explanation (optional)",
                },
            },
            "required": ["entry_id", "helpful"],
        },
    },
    "artifact_inspect": {
        "name": "artifact_inspect",
        "description": (
            "Inspect the content of a specific artifact produced by a "
            "prior colony. Useful for reviewing code, documents, or "
            "other outputs from predecessor work."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "colony_id": {
                    "type": "string",
                    "description": "Colony that produced the artifact",
                },
                "artifact_id": {
                    "type": "string",
                    "description": (
                        "Artifact ID (e.g., art-colony-agent-r3-0)"
                    ),
                },
            },
            "required": ["colony_id", "artifact_id"],
        },
    },
    "workspace_execute": {
        "name": "workspace_execute",
        "description": (
            "Execute a shell command in the workspace directory. "
            "Use for running tests, linters, build tools, or other "
            "repo-backed operations. Returns structured output with "
            "parsed test results when applicable. "
            "Not for arbitrary code execution — use code_execute for that."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "Shell command to execute (e.g., 'python -m pytest tests/', "
                        "'npm test', 'cargo test', 'go test ./...')"
                    ),
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Execution timeout in seconds (max 120).",
                    "default": 60,
                },
            },
            "required": ["command"],
        },
    },
    "list_workspace_files": {
        "name": "list_workspace_files",
        "description": (
            "List files in the workspace directory, optionally filtered by "
            "glob pattern. Returns file paths relative to workspace root."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": (
                        "Glob pattern to filter files (e.g., '**/*.py', 'src/**/*.ts'). "
                        "Defaults to listing all files."
                    ),
                    "default": "**/*",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of files to return.",
                    "default": 50,
                },
            },
        },
    },
    "read_workspace_file": {
        "name": "read_workspace_file",
        "description": (
            "Read a file from the workspace directory by its relative path. "
            "Returns the file content. For large files, use offset and limit."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from workspace root.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (0-based).",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to return.",
                    "default": 200,
                },
            },
            "required": ["path"],
        },
    },
    "write_workspace_file": {
        "name": "write_workspace_file",
        "description": (
            "Write content to a file in the workspace directory. "
            "Creates parent directories if needed. Use for code changes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from workspace root.",
                },
                "content": {
                    "type": "string",
                    "description": "Full file content to write.",
                },
            },
            "required": ["path", "content"],
        },
    },
    "patch_file": {
        "name": "patch_file",
        "description": (
            "Apply surgical text replacements to a workspace file. "
            "Each operation specifies an exact search string and its replacement. "
            "Operations apply sequentially against an in-memory buffer. "
            "The file is written only if ALL operations succeed. "
            "Empty 'replace' means deletion. Prefer this over write_workspace_file "
            "for targeted edits — it saves tokens and avoids copy errors."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from workspace root.",
                },
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "search": {
                                "type": "string",
                                "description": "Exact text to find in the file.",
                            },
                            "replace": {
                                "type": "string",
                                "description": (
                                    "Replacement text. Empty string means delete the match."
                                ),
                            },
                        },
                        "required": ["search", "replace"],
                    },
                    "description": (
                        "Ordered list of search/replace operations. "
                        "Applied sequentially against the updated buffer."
                    ),
                },
            },
            "required": ["path", "operations"],
        },
    },
    "git_status": {
        "name": "git_status",
        "description": (
            "Show the working tree status of the workspace git repository. "
            "Returns staged, unstaged, and untracked file lists."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    "git_diff": {
        "name": "git_diff",
        "description": (
            "Show changes in the workspace git repository. "
            "Returns unified diff output, optionally filtered to a specific path."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Optional relative path to diff. "
                        "Omit to diff the entire workspace."
                    ),
                },
                "staged": {
                    "type": "boolean",
                    "description": "If true, show staged (cached) changes only.",
                    "default": False,
                },
            },
        },
    },
    "git_commit": {
        "name": "git_commit",
        "description": (
            "Stage all changes and commit to the workspace git repository. "
            "No remote push. Returns the commit hash and summary."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message.",
                },
            },
            "required": ["message"],
        },
    },
    "git_log": {
        "name": "git_log",
        "description": (
            "Show recent commit history of the workspace git repository. "
            "Returns commit hashes, authors, dates, and messages."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "n": {
                    "type": "integer",
                    "description": "Number of commits to show (default 10, max 50).",
                    "default": 10,
                },
            },
        },
    },
    "request_forage": {
        "name": "request_forage",
        "description": (
            "Request fresh information on a topic via the Forager service. "
            "The Forager searches the web, fetches content, and admits "
            "relevant knowledge entries through the standard admission pipeline. "
            "Returns a summary of findings with source provenance. "
            "Prefer this over raw http_fetch for research — it respects domain "
            "trust/distrust policy and credibility scoring."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic or question to research.",
                },
                "context": {
                    "type": "string",
                    "description": (
                        "Optional context to improve search quality "
                        "(e.g. the domain, project, or specific gap)."
                    ),
                    "default": "",
                },
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional domain hints to scope the search "
                        "(e.g. ['python', 'testing'])."
                    ),
                    "default": [],
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum entries to admit (1-10).",
                    "default": 5,
                },
            },
            "required": ["topic"],
        },
    },
}

TOOL_OUTPUT_CAP = 2000  # chars per tool result

# Legacy constant — now per-caste via CasteRecipe.max_iterations (Wave 14)
MAX_TOOL_ITERATIONS = 5


# ---------------------------------------------------------------------------
# Tool category mapping (ADR-023)
# ---------------------------------------------------------------------------

TOOL_CATEGORY_MAP: dict[str, ToolCategory] = {
    "memory_search": ToolCategory.vector_query,
    "memory_write": ToolCategory.vector_query,
    "code_execute": ToolCategory.exec_code,
    "spawn_colony": ToolCategory.delegate,
    "get_status": ToolCategory.read_fs,
    "kill_colony": ToolCategory.delegate,
    "search_web": ToolCategory.search_web,
    "query_service": ToolCategory.delegate,
    "http_fetch": ToolCategory.network_out,
    "file_read": ToolCategory.read_fs,
    "file_write": ToolCategory.write_fs,
    "knowledge_detail": ToolCategory.vector_query,
    "transcript_search": ToolCategory.vector_query,
    "artifact_inspect": ToolCategory.read_fs,
    "knowledge_feedback": ToolCategory.vector_query,
    "workspace_execute": ToolCategory.exec_code,
    "list_workspace_files": ToolCategory.read_fs,
    "read_workspace_file": ToolCategory.read_fs,
    "write_workspace_file": ToolCategory.write_fs,
    "patch_file": ToolCategory.write_fs,
    "git_status": ToolCategory.read_fs,
    "git_diff": ToolCategory.read_fs,
    "git_commit": ToolCategory.write_fs,
    "git_log": ToolCategory.read_fs,
    "request_forage": ToolCategory.search_web,
}

# Hardcoded caste policies (ADR-023 — Wave 14 simplicity)
CASTE_TOOL_POLICIES: dict[str, CasteToolPolicy] = {
    "queen": CasteToolPolicy(
        caste="queen",
        allowed_categories=frozenset({
            ToolCategory.delegate, ToolCategory.read_fs, ToolCategory.vector_query,
        }),
        denied_tools=frozenset({"code_execute"}),
    ),
    "coder": CasteToolPolicy(
        caste="coder",
        allowed_categories=frozenset({
            ToolCategory.exec_code, ToolCategory.vector_query,
            ToolCategory.read_fs, ToolCategory.write_fs,
            ToolCategory.network_out,
        }),
    ),
    "reviewer": CasteToolPolicy(
        caste="reviewer",
        allowed_categories=frozenset({
            ToolCategory.vector_query, ToolCategory.read_fs,
        }),
        denied_tools=frozenset({"code_execute"}),
    ),
    "researcher": CasteToolPolicy(
        caste="researcher",
        allowed_categories=frozenset({
            ToolCategory.vector_query, ToolCategory.search_web,
            ToolCategory.read_fs, ToolCategory.network_out,
        }),
        denied_tools=frozenset({"code_execute"}),
    ),
    "archivist": CasteToolPolicy(
        caste="archivist",
        allowed_categories=frozenset({
            ToolCategory.vector_query, ToolCategory.read_fs,
            ToolCategory.write_fs,
        }),
        denied_tools=frozenset({"code_execute"}),
    ),
    "forager": CasteToolPolicy(
        caste="forager",
        allowed_categories=frozenset({
            ToolCategory.vector_query, ToolCategory.search_web,
            ToolCategory.network_out,
        }),
        denied_tools=frozenset({"code_execute"}),
    ),
}


def check_tool_permission(
    caste: str,
    tool_name: str,
    iteration_tool_count: int,
    effective_tool_limit: int | None = None,
) -> str | None:
    """Check if a caste is allowed to call a tool. Returns denial reason or None.

    Deny-by-default (ADR-023): unknown tools, unknown castes, and tools
    outside permitted categories are all denied.

    ``effective_tool_limit`` overrides the hardcoded policy limit when
    provided (model policy x caste base).
    """
    policy = CASTE_TOOL_POLICIES.get(caste)
    if policy is None:
        return f"Unknown caste '{caste}' — tool call denied."

    # Explicit deny list overrides category allow
    if tool_name in policy.denied_tools:
        return f"Tool '{tool_name}' is explicitly denied for caste '{caste}'."

    # Check category
    category = TOOL_CATEGORY_MAP.get(tool_name)
    if category is None:
        return f"Unknown tool '{tool_name}' — denied by default."
    if category not in policy.allowed_categories:
        return f"Tool '{tool_name}' (category: {category}) not permitted for caste '{caste}'."

    # Per-iteration tool call limit (model-policy-derived when available)
    limit = (
        effective_tool_limit
        if effective_tool_limit is not None
        else policy.max_tool_calls_per_iteration
    )
    if iteration_tool_count >= limit:
        return f"Tool call limit ({limit}) reached for this iteration."

    return None
