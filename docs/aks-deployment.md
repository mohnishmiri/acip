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

The chart's `AzureKeyVaultSecret` (akv2k8s) syncs it into the Kubernetes Secret `<release>-db`
(key `DATABASE_URL`). Alternatively set `keyVault.enabled=false` and create that Secret yourself
(`database.secretName`).

### Key Vault → AKS sync with akv2k8s

Secrets and the ingress TLS certificate are synced by [akv2k8s](https://akv2k8s.io) (controller
only; the env injector is not used). Install it once per cluster:

```bash
helm repo add spv-charts https://charts.spvapi.no
helm upgrade --install akv2k8s spv-charts/akv2k8s -n akv2k8s --create-namespace \
  --set env_injector.enabled=false
```

The controller reads the vault with its own identity (by default the AKS kubelet identity; or Workload
Identity, see the akv2k8s docs). Grant that identity **Key Vault Secrets User** and **Key Vault
Certificate User** on the vault (RBAC), or `get` on secrets and certificates (access policies).

| Key Vault object | Value | Kubernetes Secret |
|---|---|---|
| secret `keyVault.databaseUrlSecretName` | `acip-database-url` | `<release>-db` (`DATABASE_URL`) |
| secret `keyVault.smtpPasswordSecretName` (optional) | — | `<release>-smtp` (`SMTP_PASSWORD`) |
| secret `keyVault.graphMailSecretName` (optional) | — | `<release>-graph-mail` (`GRAPH_MAIL_CLIENT_SECRET`) |
| certificate `keyVault.tlsCertificateName` | staging `attcc-acip-stage-tls` | `ingress.tls.secretName` (`kubernetes.io/tls`) |

The database `AzureKeyVaultSecret` is a `pre-install` hook so the Secret exists before the migration
hook on first install. Helm does not re-apply it on upgrade; after changing `keyVault.name` or
`keyVault.databaseUrlSecretName`, update it with `kubectl -n acip edit akvs acip-db`.
Check sync status with `kubectl -n acip get akvs`.

## 4. Workload Identity federation (no secret in the cluster)

```bash
./infrastructure/scripts/federate-workload-identity.sh --app-id <collector-app-client-id> \
  --resource-group rg-acip-prod --cluster <aksName> --namespace acip --release acip
```

This adds a federated credential on the **existing** app registration for
`system:serviceaccount:acip:acip` (API, worker, init job). The migration hook needs no Azure
identity. Equivalent manual command:

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
`keyVault.name`, `keyVault.tlsCertificateName`, `config.AZURE_STORAGE_ACCOUNT_URL`, `config.CORS_ORIGINS`,
`config.ENTRA_*`, `ingress.host`, `ingress.tls.secretName`, and optionally
`subscriptionsConfig` (JSON registered on start).

```bash
az aks get-credentials -g rg-acip-prod -n <aksName>
kubectl create namespace acip
helm upgrade --install acip infrastructure/helm/acip -n acip \
  -f infrastructure/helm/acip/values-prod.yaml -f my-prod.yaml --wait --timeout 15m
```

Order of operations:
1. **pre-install hook** `AzureKeyVaultSecret` `acip-db` (database URL), then **pre-install /
   pre-upgrade hook** `acip-migrate` (`python -m app.cli migrate`) with its own service account;
2. ConfigMap, ServiceAccount, `AzureKeyVaultSecret`s (TLS, email), Deployments (backend, worker,
   frontend), Services, Ingress, HPAs, PDBs, NetworkPolicies;
3. **post-install / post-upgrade hook** `acip-init` (`python -m app.cli init`: reference data,
   subscription registration; demo data only when `DEMO_MODE=true` — `false` in staging/prod).

## Ingress and TLS

Default class `webapprouting.kubernetes.azure.com` (AKS application routing add-on, enabled by the
Bicep). `/api` → backend:8000, `/` → frontend:3000. The TLS certificate is the Key Vault certificate
`keyVault.tlsCertificateName`, synced by akv2k8s into Secret `ingress.tls.secretName`; leave
`tlsCertificateName` empty to provide that Secret yourself (e.g. cert-manager).
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
| Pods `CreateContainerConfigError: secret "acip-db" not found` | akv2k8s has not synced it yet: `kubectl -n acip get akvs` / `describe akvs acip-db`, controller logs (`kubectl -n akv2k8s logs deploy/akv2k8s-controller`), the vault name, the secret `acip-database-url`, and the controller identity's Key Vault role. |
| Ingress serves the default certificate | `kubectl -n acip describe akvs acip-tls`: certificate name `keyVault.tlsCertificateName`, Key Vault Certificate User for the akv2k8s identity, Secret `ingress.tls.secretName` of type `kubernetes.io/tls`. |
| Connection test: auth failed `AADSTS700016/70021` | Workload Identity federation or `serviceAccount.workloadIdentity.clientId`. |
| Connection test: cost API 403 | Cost Management Reader missing on that subscription (`assign-roles.sh`). |
| Storage check failed (403) | Storage Blob Data Reader missing, or `AZURE_STORAGE_ACCOUNT_URL` / container / export root folder wrong. |
| Freshness "Awaiting export" | Exports not created or not run yet; check the storage container for `subscriptions/<id>/actual/acip-actual-daily/…`. |
| Export run `failed` "missing required column" / "rows rejected" | Data Management → Errors; confirm CSV format (not Parquet) and export type. |
| Backend not ready, `/health/ready` 503 | Database reachability (private DNS / firewall), `sslmode=require`, migration hook result. |
| Users get 403 "no ACIP role" | Assign an app role (ACIP.Viewer or higher) in the API enterprise application. |
