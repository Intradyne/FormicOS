# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main (HEAD) | Yes |
| Tagged releases | Latest only |

FormicOS is pre-1.0. Security fixes are applied to `main` and the latest
tagged release only.

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Instead, please report vulnerabilities via one of these channels:

1. **GitHub Security Advisories** (preferred):
   Navigate to the repository's **Security** tab and click
   **Report a vulnerability**. This creates a private advisory that only
   maintainers can see.

2. **Email**: Send details to the maintainers listed in `GOVERNANCE.md`.
   Include "SECURITY" in the subject line.

### What to include

- Description of the vulnerability
- Steps to reproduce (or proof of concept)
- Affected component (core, engine, adapters, surface, frontend, Docker)
- Impact assessment (what an attacker could achieve)

### Response expectations

- **Acknowledgment**: within 72 hours
- **Initial assessment**: within 7 days
- **Fix timeline**: depends on severity, but we aim for:
  - Critical: patch within 7 days
  - High: patch within 14 days
  - Medium/Low: next planned release

We will credit reporters in the advisory unless they prefer to remain
anonymous.

## Security Architecture

FormicOS has several security-relevant design properties:

- **Event sourcing**: all state changes are append-only events, providing a
  full audit trail
- **Knowledge security scanning**: 5-axis scanning on ingested knowledge
  (prompt injection, data exfiltration, credential leakage, code safety,
  credential detection via detect-secrets). Credential values in tool outputs
  are redacted as `[REDACTED:type]`.
- **Sandboxed code execution**: the `code_execute` tool runs code inside
  disposable Docker containers with `--network=none`, `--memory=256m`,
  `--read-only`, and a small `tmpfs`. These provide basic isolation for
  code execution tasks.
- **Bayesian trust**: federation peers are scored via Bayesian trust with
  10th-percentile penalization of uncertainty. Foreign knowledge is
  discounted by hop count and capped so federated entries never outrank
  strong local verified knowledge.
- **Layer isolation**: strict 4-layer architecture enforced by CI prevents
  unauthorized cross-layer access

### Execution model — current posture

FormicOS uses two execution paths:

1. **Sandbox execution** (`code_execute` tool) — runs inside disposable
   Docker containers with network isolation and memory limits. This is the
   safer path.

2. **Workspace execution** (repo-backed commands like `git`, test runners,
   build tools) — currently runs via `asyncio.create_subprocess_shell` on
   the backend host process **without container isolation**. This is the
   largest remaining security gap.

### Docker socket access

Docker API access is routed through a socket proxy
(`tecnativa/docker-socket-proxy`) that restricts operations to container
lifecycle only (CONTAINERS=1, POST=1; all other API categories blocked).
The raw Docker socket is mounted read-only into the proxy, not into FormicOS.

Mitigations:

- Set `SANDBOX_ENABLED=false` to disable sandbox spawning entirely
- The socket proxy is the default deployment path — FormicOS connects via
  `DOCKER_HOST=tcp://docker-proxy:2375`

For stronger isolation, consider Sysbox or gVisor-based runtimes where
nested containers do not require host socket access. This is not yet a
shipped configuration.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full deployment
security posture and the distinction between enforced controls and planned
improvements.

## Scope

The following are in scope for security reports:

- Remote code execution
- Authentication/authorization bypass
- Prompt injection leading to unauthorized actions
- Knowledge poisoning that bypasses trust scoring
- Credential leakage through knowledge entries or logs
- Sandbox escape
- Federation protocol abuse
- Denial of service via event store or knowledge ingestion

## Out of Scope

- Attacks requiring physical access to the host
- Social engineering of operators
- Issues in third-party dependencies (report to the upstream project, but
  let us know so we can assess exposure)
