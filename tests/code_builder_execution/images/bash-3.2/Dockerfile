# bash 3.2 — what macOS ships as `bash` and as `sh` — with jq 1.7.1 and curl
# 8.11.1 (#582; ADR-0017 leaves the standing matrix of shells to this suite).
#
# The oldest shell the generated file claims. It is also the one that decided
# how the file hands jq its programs: it reads a heredoc inside a command
# substitution as shell, so the form the renderer does not write fails here
# and the form it does write runs.
#
# Every layer is pinned by digest and nothing is installed by a package
# manager: jq and curl are the static binaries their projects publish.
FROM ghcr.io/jqlang/jq:1.7.1@sha256:096b83865ad59b5b02841f103f83f45c51318394331bf1995e187ea3be937432 AS jq
FROM ghcr.io/tarampampam/curl:8.11.1@sha256:8f09f048304280e0e50cc82a1f4ead45971e6e0f260011ab143576e7bf982493 AS curl

FROM bash:3.2@sha256:0fd7cb8499c63a3c9345e7088a9cd83bb69f6e895e83833859aff838a0312091
COPY --from=jq /jq /usr/local/bin/jq
COPY --from=curl /bin/curl /usr/local/bin/curl
