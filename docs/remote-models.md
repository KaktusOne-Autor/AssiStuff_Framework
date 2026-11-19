# Remote model APIs

> **Available:** AssiStuff supports OpenAI-compatible chat-completions
> endpoints. Provider-specific features beyond ordinary text and JSON-object
> responses are not currently exposed.

Remote models can be configured alongside local Ollama models. The endpoint is
selected in framework configuration, while each model manifest references that
named profile. Remote routing is explicit: there is no automatic local-to-
remote fallback.

## Configuration

Add an endpoint profile under `runtime.remote_endpoints` in
`config/framework.yaml`:

```yaml
runtime:
  remote_endpoints:
    work-provider:
      provider: openai_compatible
      base_url: https://api.example.com/v1
      api_key_env: ASSISTUFF_REMOTE_API_KEY
      connect_timeout_seconds: 10
      read_timeout_seconds: 90
      max_retries: 1
```

Reference it from a model manifest:

```yaml
id: remote-writer
version: 1.0.0
runtime:
  backend: remote_api
  provider: openai_compatible
  endpoint_profile: work-provider
  tag: provider-model-id
  max_tokens: 2048
```

Set the key in the process environment before launching AssiStuff, for example
`export ASSISTUFF_REMOTE_API_KEY=...`. Only the environment variable's name is
stored in configuration. Do not put credentials in manifests, screenshots,
logs, or commits. HTTP endpoints are rejected unless
`allow_insecure_http: true` is deliberately added to that endpoint profile;
even then, only loopback/private IPs and local hostnames are accepted.

## Privacy and reliability

Remote requests disclose their prompt and any attached context to the configured
provider. The Models tab identifies configured remote models and displays a
privacy notice. Only models explicitly configured with `backend: remote_api`
use the provider; failures are reported and never fall back to Ollama. Requests
use bounded timeouts, connection-only retries, TLS verification, and
credential-free error messages. HTTP status response bodies are intentionally
not shown because they may contain sensitive provider data.

The adapter supports text and JSON-object responses and logs provider/model
identity plus token counts when supplied by the endpoint. Streaming, remote
tool calls, schema-constrained JSON, OS credential-store integration, and
provider health indicators are not yet implemented. Provider quotas, retention,
terms, and cost are the user's responsibility.

See [ADR-0015](./adr/ADR-0015-remote-model-api-providers.md).
