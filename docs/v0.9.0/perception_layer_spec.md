# FormicOS v0.9.0 Perception Layer Spec

## 1. Architectural Vision
FormicOS v0.9.0 solves the "Context Rot" problem by abandoning traditional Euclidean text shredding (e.g., LangChain's recursive character splitters). Instead, the system introduces a **Topological Perception Layer** that understands documents as graphs of structural nodes (tables, lists, headers) and preserves these structures during embedding.

---

## 2. The Dockling Core: Topological Parsing (`dockling_parser.py`)

### The Problem with Euclidean Shredding
Traditional text splitters cut documents arbitrarily based on character counts. This destroys semantic layout—cutting a Markdown table in half or severing a list item from its parent header. For complex coding and architectural tasks, this structural loss causes catastrophic retrieval hallucination in RAG.

### The HybridChunker Solution
FormicOS v0.9.0 utilizes `docling` to parse documents (PDF, DOCX, HTML) directly into Markdown, maintaining structural trees. The `DocklingParser` then processes this Markdown via IBM's `HybridChunker`. 
- **Topology Preservation**: With `merge_peers=True`, the chunker ensures that sibling structural nodes (like adjacent table rows or nested list items) are kept together.
- **Embedding Alignment**: The chunker is initialized with a `HuggingFaceTokenizer` explicitly aligned to the BGE-M3 model. By setting `max_tokens=512`, the parser guarantees that every structural chunk fits perfectly into a single embedding window without truncation.

---

## 3. Async Integration & CUDA Semaphore (`perception.py`)

Document ingestion and embedding are highly CPU and GPU-intensive operations. Running these synchronously would lock the Orchestrator's event loop and block the FormicOS API.

### The Background Queue
The `AsyncDocumentIngestor` isolates all parsing and embedding into a strict `asyncio` background pipeline. When `POST /api/v1/ingestion` is called, the system returns a UUID task ID immediately, allowing the client to poll for completion.

### The CUDA Semaphore Contract
FormicOS operates on local gaming hardware (e.g., RTX 5090). The LLM Inference Engine (Qwen3) requires massive, near-instantaneous bursts of VRAM and CUDA cores. To prevent ingestion from starving the Orchestrator:
- `docling.DocumentConverter` is strictly isolated within `asyncio.to_thread()` to prevent GIL lockups.
- An `asyncio.Semaphore(max_concurrent=2)` globally throttles the ingestion pipeline. No more than two documents can be actively converting/embedding simultaneously, ensuring the RTX 5090 retains enough floating CUDA threads to service the agent swarms' live LLM requests.

---

## 4. The Root Architect: Context Window Enforcement (`root_architect.yaml` & `.md`)

Handling multi-million token codebases requires abandoning the concept of a single "context window." FormicOS v0.9.0 introduces the `root_architect` caste, specifically designed for dense repository analysis.

### The 8k Constriction
The `root_architect` is intentionally severely restricted to an **8,192 token** context window in `caste_recipes.yaml`. This acts as a cognitive forcing function. Because the agent cannot physically read a whole file, it must behave recursively.

### The Paging Primitives
The agent is provided with two powerful tools mapped to its Python REPL:
1. `formic_read_bytes(start, length)`: Allows the agent to memory-map read slices of the codebase (capped at 50,000 bytes per call).
2. `formic_subcall(task, data_slice, caste)`: Allows the agent to spawn dedicated worker agents (Coders/Reviewers) and supply them with only the specific byte-slice needed to perform a task.

### The Four Chunking Patterns
The system prompt explicitly trains the `root_architect` on how to navigate this constraint:
1. **Pattern A (Linear Scan)**: Using `for` loops to slide a chunked read window across hundreds of kilobytes looking for target offsets.
2. **Pattern B (Index + Targeted Read)**: Reading the first 4KB of a file to extract its TOC/imports, then jumping directly to the relevant byte offset.
3. **Pattern C (Chunk + Delegate)**: Reading a specific 3KB function and passing it to a `Coder` via `formic_subcall` for isolated refactoring.
4. **Pattern D (Multi-chunk Stitching)**: Safely extracting a 100KB segment by looping, reading, and concatenating strings within the sandbox before dispatching them.

By combining Topological RAG ingested via `docling` with the recursive, byte-strided execution of the `root_architect`, FormicOS achieves theoretically infinite context scaling on 32GB consumer hardware.
