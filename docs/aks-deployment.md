# AKS deployment

The same images and code run locally and in Azure Kubernetes Service. Production uses managed
services: Azure Container Registry, AKS, Azure Database for PostgreSQL Flexible Server, Blob
Storage, Key Vault and Azure Monitor. The database is never run inside an application pod.

Artifacts:

| Path | Purpose |
|---|---|
| `infrastructure/bicep/` | Platform resources (ACR, AKS with OIDC + Workload Identity + Key Vault CSI + Container Insights + app routing, Log Analytics, PostgreSQL Flexible Server, Storage + `cost-exports` container, Key Vault, role assignments) |
| `infrastructure/helm/acip/` | Helm chart (`values.yaml`, `values-dev.yaml`, `values-staging.yaml`, `values-prod.yaml`) |
| `infrastructure/kubernetes/` | Plain manifests rendered from the chart (dev) |
| `infrastructure/scripts/` | `assign-roles.sh`, `federate-workload-identity.sh`, `create-cost-exports.sh`, `build-and-push.sh` |

## 1. Provision Azure resources

```bash
az group create -n rg-acip-prod -l eastus
# object id of the EXISTING collection service principal (enterprise application object id)
SP_OBJECT_ID=$(az ad sp show --id <collector-app-client-id> --query id -o tsv)
az deployment group create -g rg-acip-prod -f infrastructure/bicep/main.bicep \
  -p environmentName=prod collectorPrincipalObjectId=$SP_OBJECT_ID \
     postgresAdminPassword=<from-a-vault> postgresHighAvailability=true privateNetworking=true
az deployment group show -g rg-acip-prod -n main --query properties.outputs
```

Outputs: `acrLoginServer`, `aksName`, `aksOidcIssuerUrl`, `storageAccountUrl`, `storageAccountId`,
`keyVaultName`, `postgresFqdn`. The Bicep grants the collector **Storage Blob Data Reader** on the
storage account and **Key Vault Secrets User** on the vault, and AKS kubelet **AcrPull** on ACR.

## 2. Subscription roles and exports

```bash
./infrastructure/scripts/assign-roles.sh --app-id <collector-app-client-id> \
  --subscriptions "<sub1> <sub2> <sub3> <sub4> <sub5> <sub6>" \
  --storage-id <storageAccountId> [--reader]          # --reader enables Advisor / Activity Log evidence
# by an administrator (needs Cost Management Contributor; ACIP itself never creates exports)
./infrastructure/scripts/create-cost-exports.sh --storage-id <storageAccountId> \
  --subscriptions "<sub1> … <sub6>" --location eastus
```

## 3. Database and Key Vault secret

Create an application login (do not use the admin login at runtime):

```sql
CREATE ROLE acip_app LOGIN PASSWORD '<strong-password>';
GRANT ALL PRIVILEGES ON DATABASE acip TO acip_app;
\c acip
GRANT ALL ON SCHEMA public TO acip_app;
```

Store the SQLAlchemy URL in Key Vault (TLS required):

```bash
az keyvault secret set --vault-name <keyVaultName> -n acip-database-url \
  --value "postgresql+psycopg://acip_app:<password>@<postgresFqdn>:5432/acip?sslmode=require"
```

The chart's `SecretProviderClass` syncs it into the Kubernetes Secret `<release>-db`
(key `DATABASE_URL`). Alternatively set `keyVault.enabled=false` and create that Secret yourself
(`database.secretName`).

## 4. Workload Identity federation (no secret in the cluster)

```bash
./infrastructure/scripts/federate-workload-identity.sh --app-id <collector-app-client-id> \
  --resource-group rg-acip-prod --cluster <aksName> --namespace acip --release acip
```

This adds federated credentials on the **existing** app registration for
`system:serviceaccount:acip:acip` (API, worker, init job) and
`system:serviceaccount:acip:acip-migrate` (migration hook). Equivalent manual command:

```bash
az ad app federated-credential create --id <collector-app-client-id> --parameters '{
  "name": "acip-<cluster>-acip-acip",
  "issuer": "<aksOidcIssuerUrl>",
  "subject": "system:serviceaccount:acip:acip",
  "audiences": ["api://AzureADTokenExchange"] }'
```

Pods carry the label `azure.workload.identity/use: "true"`; the service account is annotated with
`azure.workload.identity/client-id`. The worker and API use `AZURE_AUTH_MODE=workload_identity`.

## 5. Application sign-in

Create the SPA and API app registrations and app roles as described in
`docs/authentication.md`; set `config.ENTRA_*` in the values file. Add the redirect URI
`https://<host>` to the SPA registration.

## 6. Build and push images

```bash
./infrastructure/scripts/build-and-push.sh <acr-name> 1.0.0
```

## 7. Install / upgrade

Create a values file for your environment (e.g. `my-prod.yaml`) overriding at least:
`global.imageRegistry`, `image.*.tag`, `serviceAccount.workloadIdentity.clientId/tenantId`,
`keyVault.name/tenantId`, `config.AZURE_STORAGE_ACCOUNT_URL`, `config.CORS_ORIGINS`,
`config.ENTRA_*`, `ingress.host`, `ingress.tls.secretName`, and optionally
`subscriptionsConfig` (JSON registered on start).

```bash
az aks get-credentials -g rg-acip-prod -n <aksName>
kubectl create namespace acip
helm upgrade --install acip infrastructure/helm/acip -n acip \
  -f infrastructure/helm/acip/values-prod.yaml -f my-prod.yaml --wait --timeout 15m
```

Order of operations:
1. **pre-install / pre-upgrade hook** `acip-migrate` (`python -m app.cli migrate`) with its own
   service account and SecretProviderClass;
2. ConfigMap, ServiceAccount, SecretProviderClass, Deployments (backend, worker, frontend),
   Services, Ingress, HPAs, PDBs, NetworkPolicies;
3. **post-install / post-upgrade hook** `acip-init` (`python -m app.cli init`: reference data,
   subscription registration; demo data only when `DEMO_MODE=true` — `false` in staging/prod).

## Ingress and TLS

Default class `webapprouting.kubernetes.azure.com` (AKS application routing add-on, enabled by the
Bicep). `/api` → backend:8000, `/` → frontend:3000. Provide the TLS certificate as Secret
`ingress.tls.secretName` (e.g. Key Vault certificate via the app routing add-on, or cert-manager).
`ingress.className: nginx` works with ingress-nginx.

## Scaling

- Backend and frontend: HPAs on CPU (prod: backend 3–8, frontend 2–6) with PDBs.
- Worker: any number of replicas safely claim jobs (`SKIP LOCKED`); one is elected scheduler.
  Increase `worker.replicas` for parallel subscription syncs; `worker.scratchSizeLimit` bounds temp
  space for downloaded export files.
- PostgreSQL: scale the Flexible Server SKU; enable zone-redundant HA in prod.

## Health verification

```bash
kubectl -n acip get pods,jobs
kubectl -n acip logs job/acip-migrate          # while the hook exists
kubectl -n acip logs deploy/acip-worker --tail=100
kubectl -n acip port-forward svc/acip-backend 8000:8000 &
curl -s localhost:8000/health/ready            # {"status":"ok","schema_revision":"0001",...}
```

Then in the UI: header freshness indicator, Administration → Azure Connections → *Test all*,
Data Management → job history. Container logs are JSON (`LOG_FORMAT=json`) and flow to Log
Analytics through Container Insights (`ContainerLogV2`); filter on `request_id`, `job_id`,
`subscription_id`.

## Rollback

```bash
helm history acip -n acip
helm rollback acip <revision> -n acip
```

Migrations are forward-only; roll back the application only when the previous version is
compatible with the current schema (additive migrations), otherwise restore PostgreSQL from a
point-in-time backup.

## Troubleshooting

| Symptom | Check |
|---|---|
| Pods `CreateContainerConfigError: secret "acip-db" not found` | The CSI driver creates the Secret when a pod mounts the volume: check `kubectl describe pod` events for `secrets-store` mount errors, the vault name, the secret `acip-database-url`, Key Vault Secrets User role, and the federated credential. |
| Migration hook fails with Key Vault 403 / AADSTS70021 | Federated credential missing for `system:serviceaccount:acip:acip-migrate`, or wrong issuer. |
| Connection test: auth failed `AADSTS700016/70021` | Workload Identity federation or `serviceAccount.workloadIdentity.clientId`. |
| Connection test: cost API 403 | Cost Management Reader missing on that subscription (`assign-roles.sh`). |
| Storage check failed (403) | Storage Blob Data Reader missing, or `AZURE_STORAGE_ACCOUNT_URL` / container / export root folder wrong. |
| Freshness "Awaiting export" | Exports not created or not run yet; check the storage container for `subscriptions/<id>/actual/acip-actual-daily/…`. |
| Export run `failed` "missing required column" / "rows rejected" | Data Management → Errors; confirm CSV format (not Parquet) and export type. |
| Backend not ready, `/health/ready` 503 | Database reachability (private DNS / firewall), `sslmode=require`, migration hook result. |
| Users get 403 "no ACIP role" | Assign an app role (ACIP.Viewer or higher) in the API enterprise application. |
