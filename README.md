# llm-d

Giant Swarm packaging of [llm-d](https://github.com/llm-d) — the generative
data plane KServe's `LLMInferenceService` deploys (llm-d is KServe's llmisvc
backend since KServe v0.17). This repo builds/mirrors the llm-d container
images into `gsoci.azurecr.io` so airgapped and registry-constrained
deployments can consume them, the same role
[giantswarm/kserve](https://github.com/giantswarm/kserve) plays for the KServe
controller and [giantswarm/vllm](https://github.com/giantswarm/vllm) for vLLM.

## Artifacts on `gsoci.azurecr.io/giantswarm/`

| Image | Source | How it is produced |
|---|---|---|
| `llm-d-router-endpoint-picker` | [llm-d/llm-d-inference-scheduler](https://github.com/llm-d/llm-d-inference-scheduler) | Built from upstream source at the pinned tag ([`Dockerfile`](./Dockerfile), multi-arch amd64+arm64) |
| `llm-d-router-disagg-sidecar` | [llm-d/llm-d-inference-scheduler](https://github.com/llm-d/llm-d-inference-scheduler) | Built from upstream source at the pinned tag ([`Dockerfile.sidecar`](./Dockerfile.sidecar), multi-arch amd64+arm64) |
| `llm-d-cuda` | [ghcr.io/llm-d/llm-d-cuda](https://github.com/orgs/llm-d/packages/container/package/llm-d-cuda) | Byte-identical mirror of the pinned upstream tag (`skopeo copy --all --preserve-digests`, see [`.circleci/custom.yml`](./.circleci/custom.yml)) |

These are the three images KServe's `LLMInferenceService` well-known presets
(`charts/kserve-runtime-configs`, `files/llmisvcconfigs`) reference:

- **endpoint picker (EPP)** — the Gateway API Inference Extension endpoint
  picker, a.k.a. the inference scheduler: prefix-cache-aware, load-aware
  routing across model replicas.
- **P/D routing sidecar** — routes requests between disaggregated prefill and
  decode workers.
- **llm-d-cuda** — the vLLM-based CUDA model-server image used by the llmisvc
  worker presets. Built by upstream from a large CUDA toolchain, so it is
  mirrored rather than rebuilt.

Note on upstream naming: the llm-d project renamed its router images. The old
`ghcr.io/llm-d/llm-d-routing-sidecar` and `ghcr.io/llm-d/llm-d-inference-scheduler`
image repositories were removed upstream; the current names (mirrored here)
are `llm-d-router-disagg-sidecar` and `llm-d-router-endpoint-picker`, both
built from the `llm-d-inference-scheduler` git repository (Go module
`github.com/llm-d/llm-d-router`).

## How the router images are built

The two Go router images follow the giantswarm/kserve controller pattern: the
Dockerfile clones the upstream repository at the pinned release tag
(`LLM_D_ROUTER_VERSION`) and cross-compiles a static binary for each target
platform, replicating upstream's own `Dockerfile.epp` / `Dockerfile.sidecar`
build (distroless static base, nonroot). Building from source rather than
mirroring gives the images Giant Swarm provenance: cosign signature, SLSA
provenance, and SBOM via the architect orb defaults.

`llm-d-cuda` cannot practically be rebuilt (multi-hour CUDA/vLLM build), so it
is mirrored digest-identically instead.

## Updating

Renovate tracks all pins:

- `LLM_D_ROUTER_VERSION` in both Dockerfiles
  (`llm-d/llm-d-inference-scheduler` GitHub releases).
- The `llm-d-cuda` tag in `.circleci/custom.yml` (via the org-wide
  `# registry:` hint, docker datasource).

Releases are automatic: every merge to `main` is tagged with the next semver
computed from Conventional Commits, and the tag pipeline builds and pushes the
two router images and runs the `llm-d-cuda` mirror. Previously mirrored tags
stay on gsoci.

## Local build

```bash
docker build -f Dockerfile -t llm-d-router-endpoint-picker:dev .
docker build -f Dockerfile.sidecar -t llm-d-router-disagg-sidecar:dev .
```
