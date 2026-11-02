# Cloud QA environment, 2026-10-30

Prepare an isolated Windows client/gateway on this PC, using synthetic fixtures only.
The existing user Claude installation and configuration remain separate.

1. Install Claude Code **2.1.312** under ignored `out/cloud-qa/claude` using the
   official versioned npm package, with lifecycle scripts disabled.
2. Install the official native **Bifrost HTTP v2.4.0** Windows x64 binary under
   `out/cloud-qa/bifrost`; record download source and executable SHA-256.
   The native binary removes the need for a running Docker VM.
3. Keep separate loopback profiles: mock gateway 18080, cloud gateway 18081,
   synthetic Anthropic-compatible upstream 18082. No capture drivers or local
   substitute language models are needed.
4. Use Bifrost's Anthropic provider against Alibaba Beijing's documented native
   endpoint `https://dashscope.aliyuncs.com/apps/anthropic`. The OpenAI provider's
   current Responses conversion is a different path and is not silently substituted.
   The client provider prefix is `anthropic/`; the upstream model is `qwen3.6-27b`.
5. Store only `env.UDPSIM_CLOUD_API_KEY` in generated configuration. Disable config
   and model-log persistence. Prompt for the actual key without echo, pass it only
   through the gateway process environment, and never pass it to the Claude child.
6. Before starting the cloud profile, require explicit confirmation of the account's
   remaining Beijing-model free quota and the provider's Free Quota Only setting.
   This flag records confirmation, not a programmatic account/billing check.
7. Exercise the real gateway with a deterministic local upstream: models, token
   count, text, native tool use and streamed tool arguments. Exercise the actual
   pinned Claude binary performing a synthetic fixture Read and returning its result.
8. Run positive/negative probe and lifecycle tests. Record transport success separately
   from model/Skill quality. No real 27B call is made until credentials are supplied.

Acceptance for this environment build: isolated binaries installed; generated cloud
configuration contains no literal credential; mock service binds only to loopback;
five real-Bifrost protocol checks and a real Claude native Read round trip pass;
missing-quota confirmation blocks cloud startup; usage/stop commands are documented.
Cloud model and internal-environment qualification remain NOT_RUN until actually run.

Official references:
- https://github.com/maximhq/bifrost/releases/tag/transports/v2.4.0
- https://github.com/maximhq/bifrost/blob/transports/v2.4.0/docs/providers/supported-providers/anthropic.mdx
- https://help.aliyun.com/en/model-studio/base-url
- https://help.aliyun.com/en/model-studio/new-free-quota
