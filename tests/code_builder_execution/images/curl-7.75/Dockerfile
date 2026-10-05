# Preflight fixture (#582): a curl without `--fail-with-body`, which curl
# added in 7.76.0. This is curl 7.75.0, the last release before it, in the
# curl project's own image; jq 1.7.1 is copied in so the curl is the only
# thing missing.
#
# Every layer is pinned by digest and nothing is installed by a package
# manager.
FROM ghcr.io/jqlang/jq:1.7.1@sha256:096b83865ad59b5b02841f103f83f45c51318394331bf1995e187ea3be937432 AS jq

FROM curlimages/curl:7.75.0@sha256:28ec2dae8001949f657dbb36141508d65572f382dbd587f868289e2ceb0d47dd
COPY --from=jq /jq /usr/local/bin/jq
