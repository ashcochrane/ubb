# The oldest jq a generated shell file runs with: jq 1.5, what Ubuntu 18.04
# and Debian 10 install as `jq` (#582). It is the first jq with `--argjson`
# and `--slurpfile`, which the file's programs use, and the file's preflight
# says so when it refuses an older one. A lifecycle is run here, so that
# claim is executed rather than remembered.
#
# The `shell` image with jq 1.5 in place of 1.7.1. jq 1.5 is published as a
# static binary and not as an image, so it is fetched from its release and
# held to the checksum below: the build fails rather than run another file.
FROM ghcr.io/tarampampam/curl:8.11.1@sha256:8f09f048304280e0e50cc82a1f4ead45971e6e0f260011ab143576e7bf982493 AS curl

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251
ADD --chmod=755 --checksum=sha256:c6b3a7d7d3e7b70c6f51b706a3b90bd01833846c54d32ca32f0027f00226ff6d \
    https://github.com/jqlang/jq/releases/download/jq-1.5/jq-linux64 /usr/local/bin/jq
COPY --from=curl /bin/curl /usr/local/bin/curl
