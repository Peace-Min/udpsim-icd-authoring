# Standalone extraction plan

Source: Peace-Min/peace-skillbank commit fe485f2a113221a6ba574dfaa939ac7af6fad381.

Verified locally: 193 Python checks, 25 Core/payload checks, eight scripted MCP/tool cases,
manifest/Skill validation, and extracted package layout/Core/payload tests. No external models invoked.

1. Copy only this Skill, its entrypoints, deterministic tools, synthetic fixtures and QA documentation.
   Preserve the runtime contract and copyright; exclude other skills, local runtimes and model I/O.
2. Add one-plugin marketplace metadata, clone-time entrypoint and standalone installation instructions.
3. Adapt transfer packaging paths and document historical-versus-new QA provenance.
4. Validate Skill/plugin manifests, 189 inherited plus 4 standalone regression tests, actual Core/payload tool cases, local links,
   package allowlist and byte-exact PDF fixtures. Do not call external models or infer Qwen acceptance.
5. Commit locally, then create the authorized public Peace-Min/udpsim-icd-authoring repository and push main.
   Keep the original skill-bank compatible; do not remove its existing Skill registration.
