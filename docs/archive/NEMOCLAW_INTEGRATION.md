# NemoClaw External Specialist Integration

FormicOS can call external NemoClaw-compatible specialist services through the
existing `query_service` tool-level seam. This is **Pattern 1** (tool-level
bridge): the external service is a callable resource, not a model participant.

## What Pattern 1 Is

The colony or Queen calls the external specialist like any other service query.
The call flows through `ServiceRouter`, emitting `ServiceQuerySent` and
`ServiceQueryResolved` events for full traceability. The external specialist
processes the request and returns a text result.

FormicOS remains the colony. The external service is an external resource.
No colony state is hidden inside the external service.

## What Pattern 2 Is Not (Yet)

Pattern 2 would wrap the external agent as an `LLMPort` adapter, making it
assignable to castes at any tier via `tier_models`. Pattern 2 is not
implemented in Wave 38. It is planned for Wave 39+.

## Setup

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEMOCLAW_ENDPOINT` | Yes | (none) | Base URL of the NemoClaw-compatible service |
| `NEMOCLAW_API_KEY` | No | (none) | Bearer token for authentication (optional for local deploys) |

### Example Configuration

```bash
export NEMOCLAW_ENDPOINT="http://localhost:9090"
export NEMOCLAW_API_KEY="sk-your-key-here"
```

If `NEMOCLAW_ENDPOINT` is not set, the specialist handlers are not registered
and FormicOS operates without external specialists. This is the default.

## Specialist Types

Three specialist types are registered when the endpoint is configured:

| Service Name | Specialist Type | Description |
|-------------|-----------------|-------------|
| `service:external:nemoclaw:secure_coder` | `secure_coder` | Security-aware code generation |
| `service:external:nemoclaw:security_review` | `security_review` | Code security review and analysis |
| `service:external:nemoclaw:sandbox_analysis` | `sandbox_analysis` | Sandboxed code execution and analysis |

## HTTP Protocol

The client sends requests to:

```
POST {NEMOCLAW_ENDPOINT}/v1/specialist/{specialist_type}
Content-Type: application/json
Authorization: Bearer {NEMOCLAW_API_KEY}  (if set)

{
  "task": "Review this code for SQL injection vulnerabilities: ..."
}
```

Expected response (200):

```json
{
  "result": "Analysis complete. Found 2 potential SQL injection points..."
}
```

The client also accepts plain text responses and JSON with an `output` field.

## Using Specialists

### From the Queen

The Queen can call specialists via the `query_service` tool:

```
Tool: query_service
Args: {
  "service_type": "service:external:nemoclaw:security_review",
  "query": "Review this authentication module for vulnerabilities..."
}
```

### From Colonies

Colonies with the `query_service` tool in their caste recipe can call
specialists the same way.

## Traceability

Every specialist call emits:

1. `ServiceQuerySent` — records request_id, service_type, query preview
2. `ServiceQueryResolved` — records response preview, latency

These events are visible in the normal event stream, colony transcripts,
and the operator UI. There is no hidden side channel.

## Timeout Behavior

Default timeout is 30 seconds. The Queen can set a custom timeout up to 60
seconds via the `timeout` parameter on `query_service`. Transport timeouts
return an error message rather than raising to the colony.

## Deployment Posture

### Local-only (default)

NemoClaw runs on the same machine or local network. No authentication needed.

```bash
export NEMOCLAW_ENDPOINT="http://localhost:9090"
```

### Externally exposed

If NemoClaw runs on a remote server, set the API key:

```bash
export NEMOCLAW_ENDPOINT="https://nemoclaw.example.com"
export NEMOCLAW_API_KEY="sk-production-key"
```

FormicOS itself should not be exposed externally without a reverse proxy
and authentication layer. NemoClaw calls are outbound from FormicOS.

## Security Considerations

- The specialist receives the raw query text. Do not send credentials or
  secrets to the external service.
- FormicOS redacts credentials from colony transcripts, but the external
  specialist may not have the same protections.
- API keys are read from environment variables, not stored in config files
  or event streams.
- The external specialist cannot modify FormicOS colony state. It only
  returns text results.
