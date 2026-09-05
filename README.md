# llm-d

Giant Swarm packaging of [llm-d](https://github.com/llm-d) — the generative
data plane KServe's `LLMInferenceService` deploys (llm-d is KServe's llmisvc
backend since KServe v0.17). This repo builds/mirrors the llm-d container
images into `gsoci.azurecr.io` so airgapped and registry-constrained
deployments can consume them, the same role
[giantswarm/kserve](https://github.com/giantswarm/kserve) plays for the KServe
controller and [giantswarm/vllm](https://github.com/giantswarm/vllm) for vLLM.

The mirror set covers exactly the image tags the shipped
[giantswarm/kserve](https://github.com/giantswarm/kserve) llmisvc well-known
presets (`charts/kserve-runtime-configs`, `files/llmisvcconfigs`) pin, so a
registry-only override of the presets to `gsoci.azurecr.io/giantswarm/`
resolves every referenced image.

## Artifacts on `gsoci.azurecr.io/giantswarm/`

| Image | Role in the llmisvc presets | How it is produced |
|---|---|---|
| `llm-d-router-endpoint-picker` | Endpoint picker (EPP), a.k.a. the inference scheduler: prefix-cache-aware, load-aware routing across model replicas | Built from [llm-d/llm-d-inference-scheduler](https://github.com/llm-d/llm-d-inference-scheduler) source ([`Dockerfile`](./Dockerfile), multi-arch amd64+arm64), plus a byte-identical mirror of the preset-pinned upstream tag |
| `llm-d-router-disagg-sidecar` | P/D routing sidecar: routes requests between disaggregated prefill and decode workers | Built from [llm-d/llm-d-inference-scheduler](https://github.com/llm-d/llm-d-inference-scheduler) source ([`Dockerfile.sidecar`](./Dockerfile.sidecar), multi-arch amd64+arm64), plus a byte-identical mirror of the preset-pinned upstream tag |
| `llm-d-cuda` | vLLM-based CUDA model server used by the llmisvc worker presets | Byte-identical mirrors of the pinned upstream tags (multi-hour CUDA build, not practically rebuildable) |
| `llm-d-uds-tokenizer` | Tokenizer sidecar in the scheduler preset pod; the EPP talks to it over a Unix domain socket | Byte-identical mirror of the preset-pinned upstream tag |
| `llm-d-latency-predictor-training-server` | Opt-in latency-predicted scheduling: training server | Byte-identical mirror of the pinned upstream tag |
| `llm-d-latency-predictor-prediction-server` | Opt-in latency-predicted scheduling: prediction server | Byte-identical mirror of the pinned upstream tag |

Mirrors are produced with `skopeo copy --all --preserve-digests` (see
[`.circleci/custom.yml`](./.circleci/custom.yml)) and are digest-identical to
their `ghcr.io/llm-d/` counterparts. Mirrored tags are never deleted:
previously mirrored tags stay on gsoci after a pin moves on.

### Tag map

Source builds are tagged with this repo's release version; mirrors keep the
upstream tag verbatim. Current tag set:

| gsoci tag | Upstream (`ghcr.io/llm-d/`) counterpart | Kind |
|---|---|---|
| `llm-d-router-endpoint-picker:<repo release>` | built from `llm-d-inference-scheduler` source at `LLM_D_ROUTER_VERSION` | source build |
| `llm-d-router-endpoint-picker:v0.9.0` | `llm-d-router-endpoint-picker:v0.9.0` | mirror (llmisvc preset pin) |
| `llm-d-router-disagg-sidecar:<repo release>` | built from `llm-d-inference-scheduler` source at `LLM_D_ROUTER_VERSION` | source build |
| `llm-d-router-disagg-sidecar:v0.9.0` | `llm-d-router-disagg-sidecar:v0.9.0` | mirror (llmisvc preset pin) |
| `llm-d-cuda:v0.9.0` | `llm-d-cuda:v0.9.0` | mirror (current, Renovate-tracked) |
| `llm-d-cuda:v0.8.0` | `llm-d-cuda:v0.8.0` | mirror (llmisvc preset pin) |
| `llm-d-uds-tokenizer:vllm-v0.19.1` | `llm-d-uds-tokenizer:vllm-v0.19.1` | mirror (llmisvc preset pin) |
| `llm-d-latency-predictor-training-server:0.9.0` | `llm-d-latency-predictor-training-server:0.9.0` | mirror (current, Renovate-tracked) |
| `llm-d-latency-predictor-training-server:v0.8.0` | `llm-d-latency-predictor-training-server:v0.8.0` | mirror (llmisvc preset pin) |
| `llm-d-latency-predictor-prediction-server:0.9.0` | `llm-d-latency-predictor-prediction-server:0.9.0` | mirror (current, Renovate-tracked) |
| `llm-d-latency-predictor-prediction-server:v0.8.0` | `llm-d-latency-predictor-prediction-server:v0.8.0` | mirror (llmisvc preset pin) |

Every repo release rebuilds the two router images from upstream source at the
pinned `LLM_D_ROUTER_VERSION`, so the source-built gsoci tags map to upstream
releases via that pin: gsoci `0.1.0` (and every later repo release until the
pin moves) was built from upstream `v0.10.0`. The source-built images and the
`v0.9.0` mirrors complement each other — the mirrors exist because the shipped
presets reference the upstream router tags verbatim.

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
is mirrored digest-identically instead, as are the other preset-pinned images.

## Updating

Renovate tracks the semver pins:

- `LLM_D_ROUTER_VERSION` in both Dockerfiles
  (`llm-d/llm-d-inference-scheduler` GitHub releases).
- The mirror-list entries in `.circleci/custom.yml` that carry a
  `# registry:` hint above their `version:` line (org-wide regex manager,
  docker datasource): the current `llm-d-cuda` pin and the two
  latency-predictor pins. Each pin is the upstream tag verbatim, `v` prefix
  included or not: the hint manager rewrites only the digits and leaves a
  literal `v` in the pin alone, so the pin's shape has to match the
  registry's. `llm-d-cuda` is tagged `v0.9.0` upstream and its pin keeps the
  `v`; the latency-predictor images are tagged bare (`0.9.0`) and their pins
  carry the bare tag.

The remaining mirror-list entries are held manually at exactly what the
shipped kserve llmisvc presets reference and only move when
giantswarm/kserve re-vendors the presets: the router `v0.9.0` pins (newer
upstream router releases are already covered by the source builds) and
`llm-d-uds-tokenizer` (upstream tags track the bundled vLLM version,
`vllm-v*`, which is not semver and thus not parseable by the org-wide
Renovate hint manager).

Releases are automatic: every merge to `main` is tagged with the next semver
computed from Conventional Commits, and the tag pipeline builds and pushes the
two router images and runs every mirror-list entry. Already-mirrored tags are
skipped by digest comparison, so re-runs are cheap.

## Local build

```bash
docker build -f Dockerfile -t llm-d-router-endpoint-picker:dev .
docker build -f Dockerfile.sidecar -t llm-d-router-disagg-sidecar:dev .
```
