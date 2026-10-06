# Preflight fixture (#582): a machine with jq and no curl at all.
#
# The `shell` image with one layer left out, so the curl that is missing is
# the only thing that differs from where the generated file runs.
FROM ghcr.io/jqlang/jq:1.7.1@sha256:096b83865ad59b5b02841f103f83f45c51318394331bf1995e187ea3be937432 AS jq

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251
COPY --from=jq /jq /usr/local/bin/jq
