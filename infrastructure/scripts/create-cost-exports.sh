#!/usr/bin/env bash
# Create the Cost Management exports ACIP ingests (run ONCE per subscription by an administrator).
# ACIP itself only READS exports -- it never creates or changes them.
#
#   ./create-cost-exports.sh --storage-id <storage-account-resource-id> --subscriptions "<sub1> <sub2> ..." \
#       [--container cost-exports] [--location eastus]
#
# For each subscription this creates (Exports API 2023-07-01-preview, "exports v2" with manifest.json):
#   acip-actual-daily          ActualCost     MonthToDate  daily   -> subscriptions/<sub>/actual
#   acip-amortized-daily       AmortizedCost  MonthToDate  daily   -> subscriptions/<sub>/amortized
#   acip-actual-lastmonth      ActualCost     TheLastMonth monthly -> subscriptions/<sub>/actual
#   acip-amortized-lastmonth   AmortizedCost  TheLastMonth monthly -> subscriptions/<sub>/amortized
# These names / folders match the default export definitions ACIP registers for a subscription
# (backend/app/services/subscription_service.py: default_exports). Register the *-lastmonth
# definitions as well (Administration -> Subscriptions, or config/subscriptions.json) so final
# invoiced revisions of the previous month are ingested.
#
# Permissions for the person running this script (NOT needed by ACIP):
#   - Cost Management Contributor on each subscription (create exports)
#   - The export uses a system-assigned managed identity that needs "Storage Blob Data Contributor"
#     on the storage account; this script grants it (requires User Access Administrator / Owner there).
# Verify the API version and body against current Microsoft documentation before production use.
set -euo pipefail

STORAGE_ID="" SUBS="" CONTAINER="cost-exports" LOCATION="eastus" API="2023-07-01-preview"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --storage-id) STORAGE_ID="$2"; shift 2 ;;
    --subscriptions) SUBS="$2"; shift 2 ;;
    --container) CONTAINER="$2"; shift 2 ;;
    --location) LOCATION="$2"; shift 2 ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "Unknown argument $1" >&2; exit 1 ;;
  esac
done
[[ -z "$STORAGE_ID" || -z "$SUBS" ]] && { echo "--storage-id and --subscriptions are required" >&2; exit 1; }

FROM=$(date -u +%Y-%m-%dT00:00:00Z)
TO="2030-12-31T00:00:00Z"

create_export() { # sub name type timeframe recurrence folder
  local sub="$1" name="$2" type="$3" timeframe="$4" recurrence="$5" folder="$6"
  local url="https://management.azure.com/subscriptions/$sub/providers/Microsoft.CostManagement/exports/$name?api-version=$API"
  local body
  body=$(cat <<JSON
{
  "identity": { "type": "SystemAssigned" },
  "location": "$LOCATION",
  "properties": {
    "schedule": { "status": "Active", "recurrence": "$recurrence", "recurrencePeriod": { "from": "$FROM", "to": "$TO" } },
    "format": "Csv",
    "partitionData": true,
    "dataOverwriteBehavior": "CreateNewReport",
    "compressionMode": "None",
    "deliveryInfo": { "destination": { "type": "AzureBlob", "resourceId": "$STORAGE_ID", "container": "$CONTAINER", "rootFolderPath": "$folder" } },
    "definition": { "type": "$type", "timeframe": "$timeframe", "dataSet": { "granularity": "Daily" } }
  }
}
JSON
)
  local principal
  principal=$(az rest --method PUT --url "$url" --body "$body" --query identity.principalId -o tsv)
  echo "  ✓ $name ($type, $timeframe, $recurrence) -> $CONTAINER/$folder"
  if [[ -n "$principal" ]]; then
    az role assignment create --assignee-object-id "$principal" --assignee-principal-type ServicePrincipal \
      --role "Storage Blob Data Contributor" --scope "$STORAGE_ID" --only-show-errors -o none || true
  fi
}

for s in $SUBS; do
  echo "Subscription $s"
  create_export "$s" acip-actual-daily ActualCost MonthToDate Daily "subscriptions/$s/actual"
  create_export "$s" acip-amortized-daily AmortizedCost MonthToDate Daily "subscriptions/$s/amortized"
  create_export "$s" acip-actual-lastmonth ActualCost TheLastMonth Monthly "subscriptions/$s/actual"
  create_export "$s" acip-amortized-lastmonth AmortizedCost TheLastMonth Monthly "subscriptions/$s/amortized"
done
echo "Exports created. Optional backfill: Data Management -> Backfill (Cost Details API), or run each export once from the portal."
