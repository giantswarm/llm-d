# Multi-stage build for the llm-d router endpoint picker (EPP, the inference
# scheduler KServe's LLMInferenceService scheduler preset deploys).
# Fetches upstream source at the pinned version and cross-compiles for the
# target platform, following upstream's Dockerfile.epp.
# renovate: datasource=github-releases depName=llm-d/llm-d-inference-scheduler
ARG LLM_D_ROUTER_VERSION=v0.10.0

FROM --platform=$BUILDPLATFORM golang:1.27.1 AS builder

ARG LLM_D_ROUTER_VERSION
ARG TARGETOS
ARG TARGETARCH

WORKDIR /workspace

RUN git clone --depth 1 --branch ${LLM_D_ROUTER_VERSION} https://github.com/llm-d/llm-d-inference-scheduler.git .

RUN go mod download

RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build \
    -ldflags="-s -w -X github.com/llm-d/llm-d-router/version.CommitSHA=$(git rev-parse HEAD) -X github.com/llm-d/llm-d-router/version.BuildRef=${LLM_D_ROUTER_VERSION}" \
    -o bin/epp ./cmd/epp

FROM gcr.io/distroless/static:nonroot

WORKDIR /

COPY --from=builder /workspace/bin/epp /app/epp

USER 65532:65532

# gRPC ext-proc, health, metrics, and the KV-events ZMQ SUB socket.
EXPOSE 9002 9003 9090 5557

ENTRYPOINT ["/app/epp"]
