#!/usr/bin/env bash
# Grant the EXISTING collection service principal the least-privilege roles ACIP needs.
# Run as a user who can create role assignments (Owner / User Access Administrator) on the scopes.
#
#   ./assign-roles.sh --app-id <client-id> --subscriptions "<sub1> <sub2> ..." \
#       --storage-id <storage-account-resource-id> [--key-vault-id <vault-id>] [--reader]
#
# Roles:
#   Cost Management Reader   on each subscription  -> cost query probe, list exports, Cost Details API
#   Storage Blob Data Reader on the export storage -> read export files
#   Key Vault Secrets User   on the vault          -> only when this principal is also the akv2k8s
#                                                     controller identity (it syncs Key Vault -> AKS)
#   Reader (optional --reader) on each subscription -> Azure Advisor recommendations, Activity Log evidence
# Never grant Owner or Contributor for reading billing data.
set -euo pipefail
# Git Bash on Windows would otherwise rewrite /subscriptions/... arguments into C:/Program Files/Git/...
export MSYS_NO_PATHCONV=1

APP_ID="" SUBS="" STORAGE_ID="" KV_ID="" READER=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id) APP_ID="$2"; shift 2 ;;
    --subscriptions) SUBS="$2"; shift 2 ;;
    --storage-id) STORAGE_ID="$2"; shift 2 ;;
    --key-vault-id) KV_ID="$2"; shift 2 ;;
    --reader) READER=1; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Unknown argument $1" >&2; exit 1 ;;
  esac
done
[[ -z "$APP_ID" || -z "$SUBS" ]] && { echo "--app-id and --subscriptions are required" >&2; exit 1; }

OBJECT_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
echo "Service principal object id: $OBJECT_ID"

assign() { # role scope
  az role assignment create --assignee-object-id "$OBJECT_ID" --assignee-principal-type ServicePrincipal \
    --role "$1" --scope "$2" --only-show-errors -o none && echo "  ✓ $1 on $2"
}

for s in $SUBS; do
  assign "Cost Management Reader" "/subscriptions/$s"
  [[ $READER -eq 1 ]] && assign "Reader" "/subscriptions/$s"
done
[[ -n "$STORAGE_ID" ]] && assign "Storage Blob Data Reader" "$STORAGE_ID"
[[ -n "$KV_ID" ]] && assign "Key Vault Secrets User" "$KV_ID"
echo "Done. Validate with: Administration -> Azure Connections -> Test all connections"
