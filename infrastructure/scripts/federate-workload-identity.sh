#!/usr/bin/env bash
# Federate the EXISTING collection app registration with the ACIP Kubernetes service accounts
# (Microsoft Entra Workload Identity). After this, pods obtain Azure tokens without any
# client secret stored in the cluster.
#
#   ./federate-workload-identity.sh --app-id <client-id> --resource-group <rg> --cluster <aks> \
#       [--namespace acip] [--release acip]
#
# Creates a federated credential for:
#   system:serviceaccount:<ns>:<release>          (API, worker, init job)
# The migration hook needs no Azure identity: Key Vault secrets reach it through akv2k8s.
# Requires permission to update the app registration (Application Administrator or app owner).
set -euo pipefail

APP_ID="" RG="" CLUSTER="" NS="acip" RELEASE="acip"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id) APP_ID="$2"; shift 2 ;;
    --resource-group) RG="$2"; shift 2 ;;
    --cluster) CLUSTER="$2"; shift 2 ;;
    --namespace) NS="$2"; shift 2 ;;
    --release) RELEASE="$2"; shift 2 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "Unknown argument $1" >&2; exit 1 ;;
  esac
done
[[ -z "$APP_ID" || -z "$RG" || -z "$CLUSTER" ]] && { echo "--app-id, --resource-group and --cluster are required" >&2; exit 1; }

ISSUER=$(az aks show -g "$RG" -n "$CLUSTER" --query oidcIssuerProfile.issuerUrl -o tsv)
[[ -z "$ISSUER" ]] && { echo "OIDC issuer not enabled on $CLUSTER" >&2; exit 1; }
echo "OIDC issuer: $ISSUER"

for SA in "$RELEASE"; do
  NAME="acip-${CLUSTER}-${NS}-${SA}"
  if az ad app federated-credential show --id "$APP_ID" --federated-credential-id "$NAME" -o none 2>/dev/null; then
    echo "  = $NAME already exists"
    continue
  fi
  az ad app federated-credential create --id "$APP_ID" --parameters "{
    \"name\": \"$NAME\",
    \"issuer\": \"$ISSUER\",
    \"subject\": \"system:serviceaccount:$NS:$SA\",
    \"audiences\": [\"api://AzureADTokenExchange\"],
    \"description\": \"ACIP $SA on $CLUSTER\"
  }" -o none
  echo "  ✓ $NAME -> system:serviceaccount:$NS:$SA"
done
