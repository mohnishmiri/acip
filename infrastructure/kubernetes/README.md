# Plain Kubernetes manifests

The Helm chart in `../helm/acip` is the supported deployment method. This directory holds
manifests **rendered from that chart** (`values-dev.yaml`) for teams that prefer
`kubectl apply` or a GitOps tool without Helm, and for reviewing exactly what is deployed.

Regenerate after changing the chart:

```bash
cd infrastructure
rm -rf kubernetes/dev && mkdir -p kubernetes/dev
helm template acip helm/acip -n acip -f helm/acip/values-dev.yaml --output-dir /tmp/acip-render
# copy /tmp/acip-render/acip/templates/*.yaml into kubernetes/dev/ (prefix 10- config, 20- jobs, 30- workloads)
```

Apply order (Helm hooks are **not** honoured by `kubectl apply`):

```bash
kubectl apply -f kubernetes/dev/00-namespace.yaml
kubectl apply -n acip -f kubernetes/dev/10-serviceaccount.yaml -f kubernetes/dev/10-configmap.yaml -f kubernetes/dev/10-secretproviderclass.yaml
# 20-jobs.yaml contains the migration job (and its service account / SecretProviderClass) and the init job.
# Apply it, wait for "acip-migrate" to complete, then the workloads; "acip-init" can run alongside.
kubectl apply -n acip -f kubernetes/dev/20-jobs.yaml
kubectl wait -n acip --for=condition=complete job/acip-migrate --timeout=15m
kubectl apply -n acip -f kubernetes/dev/30-backend.yaml -f kubernetes/dev/30-worker.yaml -f kubernetes/dev/30-frontend.yaml -f kubernetes/dev/30-ingress.yaml
```

Before applying, replace the placeholder values (client ids, tenant id, Key Vault name,
storage account URL, host names, image registry) -- they are rendered from
`values.yaml` / `values-dev.yaml`. See `docs/aks-deployment.md`.
