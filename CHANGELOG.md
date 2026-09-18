# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `llm-d-cpu:v0.8.0`, the CPU build of the llm-d release the worker presets pin, mirrored
  digest-identically next to `llm-d-cuda` (and copied under `llm-d-fast/`): the runtime a node without
  an accelerator serves a small model on through the same well-known llmisvc templates.

### Fixed

- The latency-predictor `v0.8.0` preset pins are mirror-list entries again (held, like the other preset
  pins), so they exist under the `llm-d-fast/` prefix too and every preset-pinned image resolves there.

### Added

- A fast-to-pull variant set under `gsoci.azurecr.io/giantswarm/llm-d-fast/`: `llm-d-cuda` repacked
  (`scripts/relayer.py`, CircleCI job `fast-image`) from its 5.8 GB gzip layer into 14 zstd layers of at
  most 1.2 GB uncompressed with the same filesystem and image config, every other mirrored image copied
  digest-identically under the same prefix (`mirror-image` `fast-copy`). Pointing the presets' registry
  prefix at `llm-d-fast/` swaps the variant in without touching a tag.
