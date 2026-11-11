#!/usr/bin/env bash
# Build the backend (API + worker) and frontend images locally and push them to JFrog Artifactory.
#   ./build-and-push.sh <artifactory-docker-repo> <tag>
#   e.g. ./build-and-push.sh apm0014313-dkr-attcc-stage/com.att.attcc 1.0.0  ->  artifact.it.att.com/acip-docker/acip-backend:1.0.0
#
# Registry: artifact.it.att.com (override with JFROG_REGISTRY).
# Login: run `docker login artifact.it.att.com` beforehand, or export JFROG_USER and JFROG_TOKEN
#        (Artifactory identity/access token -- never commit it).
# Behind the TLS-inspecting proxy, certs/corporate-ca.pem (or CORPORATE_CA_FILE) is passed as the
# `corporate_ca` build secret so npm/pip can verify TLS.
set -euo pipefail
REPO="${1:?Artifactory Docker repository, e.g. acip-docker}" TAG="${2:?image tag}"
REGISTRY="${JFROG_REGISTRY:-artifact.it.att.com}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$REGISTRY/$REPO"

if [[ -n "${JFROG_USER:-}" && -n "${JFROG_TOKEN:-}" ]]; then
  printf '%s' "$JFROG_TOKEN" | docker login "$REGISTRY" -u "$JFROG_USER" --password-stdin
fi

SECRET_ARGS=()
CA="${CORPORATE_CA_FILE:-$ROOT/certs/corporate-ca.pem}"
if [[ -s "$CA" ]]; then
  # docker.exe on Windows (Git Bash) needs a Windows path inside the --secret value
  command -v cygpath >/dev/null && CA="$(cygpath -m "$CA")"
  SECRET_ARGS=(--secret "id=corporate_ca,src=$CA")
fi

build_push() { # image-name context-dir
  local image="$PREFIX/$1:$TAG"
  DOCKER_BUILDKIT=1 docker build --platform linux/amd64 ${SECRET_ARGS[@]+"${SECRET_ARGS[@]}"} -t "$image" "$2"
  docker push "$image"
}

build_push acip-backend "$ROOT/backend"
build_push acip-frontend "$ROOT/frontend"
echo "Pushed $PREFIX/acip-backend:$TAG and $PREFIX/acip-frontend:$TAG"
echo "Helm: global.imageRegistry=$PREFIX, image.backend.tag=$TAG, image.frontend.tag=$TAG"
