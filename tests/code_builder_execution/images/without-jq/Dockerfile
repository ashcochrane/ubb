# Preflight fixture (#582): a machine with curl and no jq at all.
#
# The `shell` image with one layer left out, so the jq that is missing is the
# only thing that differs from where the generated file runs.
FROM ghcr.io/tarampampam/curl:8.11.1@sha256:8f09f048304280e0e50cc82a1f4ead45971e6e0f260011ab143576e7bf982493 AS curl

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251
COPY --from=curl /bin/curl /usr/local/bin/curl
