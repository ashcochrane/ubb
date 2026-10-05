# Preflight fixture (#582): a jq that cannot run the programs the generated
# file hands it — jq 1.4, what Debian 8 installed as `jq`.
#
# It reads a program from standard input and accepts `#` comments, so a
# probe of only those two passes on it. It has no `--argjson` and no
# `--slurpfile`, which the file's programs pass values with, so without a
# probe that asks for them it would start a unit of work and then fail at its
# first record (this image is how that was found).
#
# The `shell` image with jq 1.4 in place of 1.7.1. jq 1.4 is published as a
# static binary and not as an image, so it is fetched from its release and
# held to the checksum below: the build fails rather than run another file.
FROM ghcr.io/tarampampam/curl:8.11.1@sha256:8f09f048304280e0e50cc82a1f4ead45971e6e0f260011ab143576e7bf982493 AS curl

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251
ADD --chmod=755 --checksum=sha256:b9b63aa4b3cc85df8bdca884effb69d66e9ebd717454a9e212d9423ffe3e955f \
    https://github.com/jqlang/jq/releases/download/jq-1.4/jq-linux-x86_64 /usr/local/bin/jq
COPY --from=curl /bin/curl /usr/local/bin/curl
