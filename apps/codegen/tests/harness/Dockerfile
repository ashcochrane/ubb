# Where the shell target's tests run on a machine that has no POSIX shell with
# jq and curl of its own: Windows, in particular, where a Git Bash and a native
# jq.exe are not the environment a generated shell file is run in.
#
#     docker build -t ubb-codegen-shell apps/codegen/tests/harness
#     UBB_CODEGEN_SHELL_IMAGE=ubb-codegen-shell pnpm --dir apps/codegen test
#
# CI does not use it: its runner has sh, bash, curl and jq, and the tests run
# the generated files there directly. This image is Debian stable, so between
# the two the suite sees two generations of each tool (jq 1.6 and curl 7.88
# here; jq 1.7 and curl 8 on the runner).
FROM python:3.13-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends jq curl \
    && rm -rf /var/lib/apt/lists/*
