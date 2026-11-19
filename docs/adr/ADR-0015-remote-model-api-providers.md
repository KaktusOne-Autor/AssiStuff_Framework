# ADR-0015: Remote model API providers

- **Status:** Accepted
- **Date:** 2026-11-19

## Context

AssiStuff currently targets locally hosted inference backends. Users also need
to route selected capabilities to models hosted by remote providers through
their HTTP APIs, while keeping local inference available and preserving
provider-independent model manifests.

## Decision

- Add a provider adapter boundary to model runtime configuration. A model
  manifest identifies the provider, API endpoint or configured endpoint
  profile, provider model/deployment ID, and supported request features.
- Initially support a documented OpenAI-compatible chat-completions protocol.
  Treat this as a widely used compatibility profile, not a formal
  standards-body protocol. Provider-specific adapters may be added when
  required; do not make provider quirks part of the capability bus or router.
- Keep secrets out of YAML manifests, source control, logs, traces, and GUI
  exports. Resolve API credentials from explicitly configured environment
  variable names or the operating system credential store.
- Use HTTPS for remote endpoints by default. Allow non-TLS endpoints only for
  explicitly configured trusted local/private networks.
- Apply explicit connect/read timeouts and bounded retries only for safe
  transient failures. Surface authentication, quota, provider, and malformed
  response errors without returning a success-shaped fallback.
- Expose remote/local status, provider/model identity, and request usage where
  the provider makes it available. Avoid logging prompt or response contents by
  default.
- Allow routing policy to prefer local or remote models and to exclude remote
  models for privacy-sensitive capabilities.

## Security and privacy

- Remote inference sends request content to the configured provider. The UI
  must make that boundary discoverable and must not silently reroute local
  requests to a remote endpoint.
- TLS certificate validation remains enabled.
- Credentials are redacted from errors and telemetry.
- Provider endpoints are configuration, not arbitrary model-supplied URLs.

## Consequences

- Model runtime schemas and adapters need provider-aware settings and tests
  using mock HTTP endpoints.
- Routing and availability checks must distinguish remote endpoint
  reachability from local Ollama model installation.
- Token limits, tool calling, streaming, structured output, and usage reporting
  are provider capabilities and must be negotiated rather than assumed.
- Costs, data retention, and provider terms remain the user's responsibility.

## Implementation status

The first provider adapter is implemented for OpenAI-compatible chat
completions. Manifests select a named endpoint profile; credentials are read
from an environment variable at request time. HTTPS is required unless an
endpoint explicitly opts into HTTP. Connection retries are bounded, response
bodies are not included in errors, and remote models bypass Ollama residency.
See [remote-models.md](../remote-models.md) for configuration and limitations.
