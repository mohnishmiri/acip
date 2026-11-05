#!/usr/bin/env bash
# Build the backend (API + worker) and frontend images in ACR (no local Docker needed).
#   ./build-and-push.sh <acr-name> <tag>
set -euo pipefail
ACR="${1:?acr name}" TAG="${2:?image tag}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
az acr build -r "$ACR" -t "acip-backend:$TAG" "$ROOT/backend"
az acr build -r "$ACR" -t "acip-frontend:$TAG" "$ROOT/frontend"
echo "Pushed $ACR.azurecr.io/acip-backend:$TAG and $ACR.azurecr.io/acip-frontend:$TAG"
