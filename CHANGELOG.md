# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A fast-to-pull variant set under `gsoci.azurecr.io/giantswarm/llm-d-fast/`: `llm-d-cuda` repacked
  (`scripts/relayer.py`, CircleCI job `fast-image`) from its 5.8 GB gzip layer into 14 zstd layers of at
  most 1.2 GB uncompressed with the same filesystem and image config, every other mirrored image copied
  digest-identically under the same prefix (`mirror-image` `fast-copy`). Pointing the presets' registry
  prefix at `llm-d-fast/` swaps the variant in without touching a tag.
