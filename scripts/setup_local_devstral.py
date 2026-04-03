"""Prepare local Devstral Small 2 settings for FormicOS.

Downloads the recommended Q4_K_M GGUF into ``.models`` using
``huggingface_hub`` and writes ``.env.devstral`` with a conservative
32 GB GPU configuration. Existing unrelated settings are preserved.
"""

from __future__ import annotations

from pathlib import Path

from huggingface_hub import hf_hub_download


REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / ".models"
ENV_PATH = REPO_ROOT / ".env.devstral"
BASE_ENV = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

DEVSTRAL_REPO = "bartowski/mistralai_Devstral-Small-2-24B-Instruct-2512-GGUF"
DEVSTRAL_FILE = "mistralai_Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf"
EMBED_REPO = "Qwen/Qwen3-Embedding-0.6B-GGUF"
EMBED_FILE = "Qwen3-Embedding-0.6B-Q8_0.gguf"

UPDATES = {
    "COMPOSE_PROFILES": "local-gpu",
    "QUEEN_MODEL": "llama-cpp/devstral-small-2-24b",
    "CODER_MODEL": "llama-cpp/devstral-small-2-24b",
    "REVIEWER_MODEL": "llama-cpp/devstral-small-2-24b",
    "RESEARCHER_MODEL": "llama-cpp/devstral-small-2-24b",
    "ARCHIVIST_MODEL": "llama-cpp/devstral-small-2-24b",
    "FORMICOS_ENV_FILE": ".env.devstral",
    "LLM_HOST": "http://llm:8080",
    "EMBED_URL": "http://formicos-embed:8200",
    "LLM_MODEL_FILE": DEVSTRAL_FILE,
    "LLM_MODEL_ALIAS": "devstral-small-2-24b",
    "LLM_CHAT_TEMPLATE_ARGS": "",
    "LLM_FLASH_ATTN": "off",
    "LLM_CACHE_TYPE_K": "f16",
    "LLM_CACHE_TYPE_V": "f16",
    "LLM_BATCH_SIZE": "4096",
    "LLM_UBATCH_SIZE": "2048",
    "LLM_CACHE_RAM": "0",
    "LLM_CONTEXT_SIZE": "32768",
    "LLM_SLOTS": "3",
}


def _download(repo_id: str, filename: str) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target = MODELS_DIR / filename
    if target.exists():
        print(f"present: {target.name}")
        return
    print(f"downloading: {repo_id}/{filename}")
    hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(MODELS_DIR),
    )


def _load_env_lines() -> list[str]:
    if BASE_ENV.exists():
        return BASE_ENV.read_text(encoding="utf-8").splitlines()
    if ENV_PATH.exists():
        return ENV_PATH.read_text(encoding="utf-8").splitlines()
    return ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()


def _write_env(lines: list[str]) -> None:
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _upsert_env(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    replaced = False
    updated: list[str] = []
    for line in lines:
        stripped = line.lstrip("#").strip()
        if stripped.startswith(prefix):
            updated.append(f"{key}={value}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(f"{key}={value}")
    return updated


def main() -> None:
    _download(DEVSTRAL_REPO, DEVSTRAL_FILE)
    _download(EMBED_REPO, EMBED_FILE)

    lines = _load_env_lines()
    for key, value in UPDATES.items():
        lines = _upsert_env(lines, key, value)
    _write_env(lines)

    print("updated: .env.devstral")
    print("next: docker compose --env-file .env.devstral up -d llm formicos-embed")
    print("then: docker compose --env-file .env.devstral up -d formicos")


if __name__ == "__main__":
    main()
