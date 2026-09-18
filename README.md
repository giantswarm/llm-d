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
resolves every referenced image. The same set exists once more under
`gsoci.azurecr.io/giantswarm/llm-d-fast/`, with the model-server image
repacked into small zstd layers so a GPU node pulls it in a fraction of the
time — see [the fast-to-pull variant set](#the-fast-to-pull-variant-set-llm-d-fast).

## Artifacts on `gsoci.azurecr.io/giantswarm/`

| Image | Role in the llmisvc presets | How it is produced |
|---|---|---|
| `llm-d-router-endpoint-picker` | Endpoint picker (EPP), a.k.a. the inference scheduler: prefix-cache-aware, load-aware routing across model replicas | Built from [llm-d/llm-d-inference-scheduler](https://github.com/llm-d/llm-d-inference-scheduler) source ([`Dockerfile`](./Dockerfile), multi-arch amd64+arm64), plus a byte-identical mirror of the preset-pinned upstream tag |
| `llm-d-router-disagg-sidecar` | P/D routing sidecar: routes requests between disaggregated prefill and decode workers | Built from [llm-d/llm-d-inference-scheduler](https://github.com/llm-d/llm-d-inference-scheduler) source ([`Dockerfile.sidecar`](./Dockerfile.sidecar), multi-arch amd64+arm64), plus a byte-identical mirror of the preset-pinned upstream tag |
| `llm-d-cuda` | vLLM-based CUDA model server used by the llmisvc worker presets | Byte-identical mirrors of the pinned upstream tags (multi-hour CUDA build, not practically rebuildable) |
| `llm-d-cpu` | The CPU build of the same vLLM-based model server, for a node without an accelerator (a lab, a small model on CPU capacity) through the same llmisvc templates | Byte-identical mirror of the preset-pinned upstream tag (amd64 only, as upstream publishes it) |
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
| `llm-d-cpu:v0.8.0` | `llm-d-cpu:v0.8.0` | mirror (llmisvc preset pin, CPU build) |
| `llm-d-uds-tokenizer:vllm-v0.19.1` | `llm-d-uds-tokenizer:vllm-v0.19.1` | mirror (llmisvc preset pin) |
| `llm-d-latency-predictor-training-server:0.9.0` | `llm-d-latency-predictor-training-server:0.9.0` | mirror (current, Renovate-tracked) |
| `llm-d-latency-predictor-training-server:v0.8.0` | `llm-d-latency-predictor-training-server:v0.8.0` | mirror (llmisvc preset pin) |
| `llm-d-latency-predictor-prediction-server:0.9.0` | `llm-d-latency-predictor-prediction-server:0.9.0` | mirror (current, Renovate-tracked) |
| `llm-d-latency-predictor-prediction-server:v0.8.0` | `llm-d-latency-predictor-prediction-server:v0.8.0` | mirror (llmisvc preset pin) |
| `llm-d-fast/llm-d-cuda:v0.9.0` | `llm-d-cuda:v0.9.0`, linux/amd64 manifest `sha256:e3a83aa57397c4d5d6a3318e4bcb236bb98a636b053e84989d005fae9ace0b9a` | repacked variant (current, Renovate-tracked) |
| `llm-d-fast/llm-d-cuda:v0.8.0` | `llm-d-cuda:v0.8.0`, linux/amd64 manifest `sha256:3bfec54270e3cb58891a0fa8fc4e88108408615a2ad9f1725ead172d8dbd6e0f` | repacked variant (llmisvc preset pin) |
| `llm-d-fast/<every other mirror row>` | as above | digest-identical copy of the mirror |

A repacked variant's own digest changes with the compressor that built it;
the source it was repacked from is recorded in its manifest as
`org.opencontainers.image.base.digest` (the digests listed above) and
`org.opencontainers.image.base.name`, readable with
`crane manifest gsoci.azurecr.io/giantswarm/llm-d-fast/llm-d-cuda:v0.8.0 | jq .annotations`.

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

## The fast-to-pull variant set: `llm-d-fast/`

`llm-d-cuda:v0.8.0` (linux/amd64) is 8.8 GB of gzip-compressed layers, and
5.8 GB of that is a single layer. A container runtime pulls every layer on
one HTTPS stream and gunzips it on one core, so that layer alone is a
single-stream download of at least a minute (one stream from the registry to
a node measures about 95 MB/s where four streams in parallel sum to about
300 MB/s) followed by a single-core gunzip of 15 GB. A GPU node pulls the
image in 130–150 s, and every small image pulled beside it slows down
several-fold — which delays the GPU operator's operands and with them the
GPU becoming schedulable.

`gsoci.azurecr.io/giantswarm/llm-d-fast/llm-d-cuda:<tag>` is the same image
— the same files with the same owners, modes, mtimes, symlinks, hardlinks
and extended attributes, and the same image config (ENV, ENTRYPOINT, USER,
WORKDIR, labels) — repacked into 14 layers of at most 1.2 GB uncompressed
(0.09–0.82 GB compressed) and zstd-compressed
(`application/vnd.oci.image.layer.v1.tar+zstd`). containerd's parallel layer
downloads (three at a time by default) now work on the bulk of the image,
zstd decompresses three to five times faster than gzip per core, and the
whole image is 6.6 GB on the wire instead of 8.8 GB. The variant is
single-platform (linux/amd64, the platform of GPU nodes); the multi-platform
byte-identical mirror stays at `gsoci.azurecr.io/giantswarm/llm-d-cuda:<tag>`.

Every other image of the mirror set is copied digest-identically under the
same prefix, so the whole preset set resolves there: in the
`kserve-runtime-configs` chart, `kserve.llmisvcConfigs.imageRegistry:
gsoci.azurecr.io/giantswarm/llm-d-fast/` swaps the variant in without
touching a tag.

### How it is built

[`scripts/relayer.py`](./scripts/relayer.py) (standard-library Python plus
the `zstd` CLI) makes two passes over the flattened filesystem of the source
image as `crane export` writes it — one tar stream with every file exactly
once, whiteouts already applied — so the 15 GB filesystem is never stored:

1. `plan` sizes every directory and cuts the tree into items: whole subtrees
   where they fit under the cap, otherwise a directory's own entry with its
   direct files and its subdirectories as items of their own (a directory
   whose direct files alone exceed the cap is cut file by file). The items
   are bin-packed first-fit-decreasing. Hardlinks are always placed in their
   target's layer — an OCI hardlink is only valid within one layer — so
   nothing is copied and the repacked filesystem is byte-for-byte the input.
2. `split` streams every entry into its layer (one `zstd` per layer, the
   uncompressed digest hashed on the way), emits each layer's ancestor
   directories with the source's metadata so every layer applies cleanly on
   its own, and writes an OCI image layout whose config is the source config
   with only `rootfs.diff_ids` and `history` replaced. The manifest records
   the source in `org.opencontainers.image.base.name` and `.base.digest`.

The CircleCI job `fast-image` ([`.circleci/custom.yml`](./.circleci/custom.yml))
runs on every release tag for each pinned `llm-d-cuda` tag, pulling the
source from `ghcr.io/llm-d/` (the same digest the mirror carries). Before
anything is published it verifies the result against the source: the sorted
`tar -tv` listing of the source filesystem equals the union of the layers'
listings (108,032 entries for v0.8.0 — sizes, modes, owners, mtimes and link
targets), the config minus `rootfs`/`history` is identical, every layer is
within the cap, and the image runs — pushed to a local registry, pulled by
Docker and started through its own entrypoint with `python3 -c 'import vllm,
torch'`. It then publishes with `crane push` and checks that the registry
holds exactly the manifest it built. The job is idempotent: it halts when the
destination's `base.digest` annotation already names the current source
platform manifest. On branches the same job runs with `push: false`, so
every PR — including the Renovate PR that moves the pin — proves the
mechanism on the real image.

### Layers of `llm-d-fast/llm-d-cuda:v0.8.0` (linux/amd64)

Source: 50 gzip layers, 8.80 GB compressed, largest 5.81 GB (then 1.51 GB,
1.08 GB and 47 small ones). Repacked with `zstd -9` (level 12 costs 60 % more
CPU for the same size; level 19 eleven times the CPU for 12 % fewer bytes):
14 layers, 6.62 GB compressed for 15.63 GB of filesystem, largest 0.82 GB.

| Layer | Compressed | Uncompressed | Entries | Contents |
|---|---|---|---|---|
| 0 | 0.09 GB | 1.18 GB | 8636 | `site-packages/flashinfer_cubin/…/fmha/trtllm-gen` (8635 files) |
| 1 | 0.79 GB | 1.18 GB | 16 | `site-packages/nvidia/cu13/lib` (10 files), `site-packages/multipart` |
| 2 | 0.82 GB | 1.18 GB | 58 | `/usr/local/cuda-13.0/targets/x86_64-linux/lib` (47 files), `/afs` and 1 more |
| 3 | 0.45 GB | 1.18 GB | 12323 | `site-packages/torch`, `site-packages/cupy_backends` and 1 more |
| 4 | 0.47 GB | 1.18 GB | 130 | `/usr/local/cuda-13.0/targets/x86_64-linux/lib` (24 files), `/usr/local/cuda-13.0/compat`, `/opt/vllm/bin` and 2 more |
| 5 | 0.64 GB | 1.18 GB | 122 | `site-packages/nvidia/cu13/lib` (16 files), `site-packages/nvidia/cudnn`, `site-packages/aiohttp` and 1 more |
| 6 | 0.19 GB | 1.18 GB | 6187 | `site-packages/triton`, `site-packages/flashinfer_cubin/…` (4818 files), `site-packages/pycountry` and 2 more |
| 7 | 0.52 GB | 1.18 GB | 11892 | `/opt/vllm-source`, `/usr/lib64`, `site-packages/xgrammar` and 2 more |
| 8 | 0.57 GB | 1.18 GB | 737 | `site-packages/tokenspeed_triton`, `site-packages/nvidia/cu13/bin`, `site-packages/nvidia/cusparselt` and 6 more |
| 9 | 0.38 GB | 1.18 GB | 12012 | `site-packages/tilelang`, two `flashinfer_jit_cache` kernels and 7 more |
| 10 | 0.36 GB | 1.18 GB | 22423 | `/usr/local/cuda-13.0/bin`, `site-packages/nixl_cu12.libs` and 13 more |
| 11 | 0.47 GB | 1.18 GB | 17417 | `/usr/bin`, `/usr/local/bin` and 46 more |
| 12 | 0.77 GB | 1.18 GB | 10294 | `/opt/vllm/include`, `flashinfer_jit_cache` prefill kernels and 305 more |
| 13 | 0.10 GB | 0.25 GB | 5785 | `site-packages/rpds` and 951 small directories |

(`site-packages` is `/opt/vllm/lib/python3.12/site-packages`.) The job's
`layers.md` artifact carries the table of every build.

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
- The mirror-list and fast-image entries in `.circleci/custom.yml` that carry
  a `# registry:` hint above their `version:` line (org-wide regex manager,
  docker datasource): the current `llm-d-cuda` pin (its mirror and its
  fast-image entries move together) and the two latency-predictor pins. Each
  pin is the upstream tag verbatim, `v` prefix included or not: the hint
  manager rewrites only the digits and leaves a literal `v` in the pin alone,
  so the pin's shape has to match the registry's. `llm-d-cuda` is tagged
  `v0.9.0` upstream and its pin keeps the `v`; the latency-predictor images
  are tagged bare (`0.9.0`) and their pins carry the bare tag.

The remaining mirror-list entries are held manually at exactly what the
shipped kserve llmisvc presets reference and only move when
giantswarm/kserve re-vendors the presets: the router `v0.9.0` pins (newer
upstream router releases are already covered by the source builds),
`llm-d-uds-tokenizer` (upstream tags track the bundled vLLM version,
`vllm-v*`, which is not semver and thus not parseable by the org-wide
Renovate hint manager) and the `llm-d-cuda:v0.8.0` mirror and fast-image
entries.

Releases are automatic: every merge to `main` is tagged with the next semver
computed from Conventional Commits, and the tag pipeline builds and pushes the
two router images, runs every mirror-list entry and repacks every pinned
`llm-d-cuda` tag into the fast variant. Already-mirrored tags are skipped by
digest comparison and already-repacked ones by their recorded source digest,
so re-runs are cheap.

## Local build

```bash
docker build -f Dockerfile -t llm-d-router-endpoint-picker:dev .
docker build -f Dockerfile.sidecar -t llm-d-router-disagg-sidecar:dev .
```

Repacking an image locally takes the same steps as the CI job (`crane`,
`zstd`, `python3`):

```bash
crane pull --platform linux/amd64 ghcr.io/llm-d/llm-d-cuda:v0.8.0 src.tar
crane config --platform linux/amd64 ghcr.io/llm-d/llm-d-cuda:v0.8.0 > config.json
crane export - - < src.tar | python3 scripts/relayer.py plan -o plan.json
crane export - - < src.tar | python3 scripts/relayer.py split --plan plan.json --config config.json \
  --source-ref ghcr.io/llm-d/llm-d-cuda:v0.8.0 \
  --source-digest "$(crane digest --platform linux/amd64 ghcr.io/llm-d/llm-d-cuda:v0.8.0)" \
  --out layout --report report.json
crane push layout <registry>/llm-d-fast/llm-d-cuda:v0.8.0
```
