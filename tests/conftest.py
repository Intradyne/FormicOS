"""Shared test fixtures for FormicOS v0.7.9."""

import pytest
from unittest.mock import MagicMock

# ── Conditional imports for optional test dependencies ───────────────────

try:
    import respx
    HAS_RESPX = True
except ImportError:
    HAS_RESPX = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


# ── Core fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def sample_config_path(tmp_path):
    """Create a minimal valid formicos.yaml for testing."""
    config = tmp_path / "formicos.yaml"
    config.write_text('''
schema_version: "0.6.0"
identity:
  name: FormicOS
  version: "0.6.0"
hardware:
  gpu: test
  vram_gb: 32
  vram_alert_threshold_gb: 28
inference:
  endpoint: http://localhost:8080/v1
  model: test-model
  model_alias: gpt-4
  max_tokens_per_agent: 5000
  temperature: 0
  timeout_seconds: 120
  context_size: 32768
  intent_model: null
  intent_max_tokens: 512
embedding:
  model: test-embed
  endpoint: http://localhost:8081/v1
  dimensions: 1024
  max_tokens: 8192
  batch_size: 32
  routing_model: all-MiniLM-L6-v2
routing:
  tau: 0.35
  k_in: 3
  broadcast_fallback: true
convergence:
  similarity_threshold: 0.95
  rounds_before_force_halt: 2
  path_diversity_warning_after: 3
summarization:
  epoch_window: 5
  max_epoch_tokens: 400
  max_agent_summary_tokens: 200
  tree_sitter_languages: [python]
temporal:
  episodic_ttl_hours: 72
  stall_repeat_threshold: 3
  stall_window_minutes: 20
  tkg_max_tuples: 5000
castes:
  manager:
    system_prompt_file: manager.md
    tools: []
    model_override: null
persistence:
  session_dir: .formicos/sessions
  autosave_interval_seconds: 30
approval_required: []
qdrant:
  host: localhost
  port: 6333
  grpc_port: 6334
  collections:
    project_docs:
      embedding: bge-m3
      dimensions: 1024
    swarm_memory:
      embedding: bge-m3
      dimensions: 1024
mcp_gateway:
  enabled: false
  transport: stdio
  command: docker
  args: ["mcp", "gateway", "run"]
  docker_fallback_endpoint: http://localhost:8811
  sse_retry_attempts: 5
  sse_retry_delay_seconds: 3
model_registry:
  test/model:
    type: autoregressive
    backend: llama_cpp
    endpoint: http://localhost:8080/v1
    context_length: 32768
    vram_gb: 25.6
    supports_tools: true
    supports_streaming: true
skill_bank:
  storage_file: .formicos/skill_bank.json
  retrieval_top_k: 3
  dedup_threshold: 0.85
  evolution_interval: 5
  prune_zero_hit_after: 10
subcaste_map:
  heavy:
    primary: test/model
  balanced:
    primary: test/model
  light:
    primary: test/model
teams:
  max_teams_per_colony: 4
  team_summary_max_tokens: 200
  allow_dynamic_spawn: true
colonies: {}
''')
    return config


@pytest.fixture
def mock_config(sample_config_path):
    """Load and return a FormicOSConfig from the sample config."""
    from src.models import load_config
    import os
    os.environ["FORMICOS_CONFIG"] = str(sample_config_path)
    try:
        return load_config(str(sample_config_path))
    finally:
        os.environ.pop("FORMICOS_CONFIG", None)


@pytest.fixture
async def async_client(mock_config):
    """Async HTTP test client wrapping the FastAPI app.

    Uses httpx.AsyncClient for async endpoint testing without
    spawning a real server. Manages app lifespan.
    """
    if not HAS_HTTPX:
        pytest.skip("httpx not installed")

    from src.server import create_app
    app = create_app(mock_config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
def mock_llm():
    """Mock LLM API responses to prevent real billing during tests.

    Uses respx to intercept outbound HTTP calls to OpenAI/Anthropic
    and return deterministic JSON responses.
    """
    if not HAS_RESPX:
        pytest.skip("respx not installed")

    with respx.mock(assert_all_called=False) as mock:
        # OpenAI completions
        mock.post("https://api.openai.com/v1/chat/completions").respond(
            200,
            json={
                "choices": [{
                    "message": {"content": "mocked response", "role": "assistant"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )
        # Anthropic messages
        mock.post("https://api.anthropic.com/v1/messages").respond(
            200,
            json={
                "content": [{"type": "text", "text": "mocked response"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )
        yield mock


@pytest.fixture
def mock_colony_manager():
    """Mock ColonyManager for unit testing routes without real colonies."""
    from src.colony_manager import ColonyManager, ColonyInfo

    cm = MagicMock(spec=ColonyManager)
    cm.get_all.return_value = [
        ColonyInfo(colony_id="test-colony", task="test task"),
    ]
    cm.get_info.return_value = ColonyInfo(
        colony_id="test-colony", task="test task",
    )
    cm.get_context.return_value = MagicMock()
    return cm
