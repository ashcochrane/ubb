# Where a generated shell file is run against the real application (#582):
# Debian's `sh` (dash) and `bash` (5.2), with jq 1.7.1 and curl 8.11.1.
#
# Every layer is pinned by digest and nothing is installed by a package
# manager, so the same image is built on every machine, every time: jq and
# curl are the static binaries their projects publish as images, copied in.
FROM ghcr.io/jqlang/jq:1.7.1@sha256:096b83865ad59b5b02841f103f83f45c51318394331bf1995e187ea3be937432 AS jq
FROM ghcr.io/tarampampam/curl:8.11.1@sha256:8f09f048304280e0e50cc82a1f4ead45971e6e0f260011ab143576e7bf982493 AS curl

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251
COPY --from=jq /jq /usr/local/bin/jq
COPY --from=curl /bin/curl /usr/local/bin/curl
