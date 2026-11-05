{{/* Chart name */}}
{{- define "acip.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully qualified app name */}}
{{- define "acip.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "acip.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "acip.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: acip
{{- end -}}

{{/* Selector labels for one component: include "acip.selectorLabels" (dict "ctx" . "component" "backend") */}}
{{- define "acip.selectorLabels" -}}
app.kubernetes.io/name: {{ include "acip.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "acip.image" -}}
{{- $img := index .ctx.Values.image .component -}}
{{- if .ctx.Values.global.imageRegistry -}}
{{- printf "%s/%s:%s" .ctx.Values.global.imageRegistry $img.repository $img.tag -}}
{{- else -}}
{{- printf "%s:%s" $img.repository $img.tag -}}
{{- end -}}
{{- end -}}

{{- define "acip.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "acip.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "acip.dbSecretName" -}}
{{- default (printf "%s-db" (include "acip.fullname" .)) .Values.database.secretName -}}
{{- end -}}

{{- define "acip.kvClientId" -}}
{{- default .Values.serviceAccount.workloadIdentity.clientId .Values.keyVault.clientId -}}
{{- end -}}

{{/* Pod labels for workloads that need Azure access through Workload Identity */}}
{{- define "acip.workloadIdentityLabel" -}}
{{- if .Values.serviceAccount.workloadIdentity.enabled }}
azure.workload.identity/use: "true"
{{- end }}
{{- end -}}

{{/* Environment shared by API, worker and jobs */}}
{{- define "acip.backendEnv" -}}
envFrom:
  - configMapRef:
      name: {{ include "acip.fullname" . }}-config
env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: {{ include "acip.dbSecretName" . }}
        key: {{ .Values.database.secretKey }}
  - name: PYTHONDONTWRITEBYTECODE
    value: "1"
  {{- if .Values.subscriptionsConfig.enabled }}
  - name: AZURE_SUBSCRIPTIONS_CONFIG
    value: /config/subscriptions.json
  {{- end }}
{{- end -}}

{{/* Volumes shared by backend-image pods */}}
{{- define "acip.backendVolumes" -}}
- name: tmp
  emptyDir: {}
- name: exports
  emptyDir:
    sizeLimit: {{ .Values.worker.scratchSizeLimit }}
{{- if .Values.subscriptionsConfig.enabled }}
- name: subscriptions-config
  configMap:
    name: {{ include "acip.fullname" . }}-subscriptions
{{- end }}
{{- if .Values.keyVault.enabled }}
- name: secrets-store
  csi:
    driver: secrets-store.csi.k8s.io
    readOnly: true
    volumeAttributes:
      secretProviderClass: {{ include "acip.fullname" . }}-kv
{{- end }}
{{- end -}}

{{- define "acip.backendVolumeMounts" -}}
- name: tmp
  mountPath: /tmp
- name: exports
  mountPath: /data/exports
{{- if .Values.subscriptionsConfig.enabled }}
- name: subscriptions-config
  mountPath: /config
  readOnly: true
{{- end }}
{{- if .Values.keyVault.enabled }}
- name: secrets-store
  mountPath: /mnt/secrets-store
  readOnly: true
{{- end }}
{{- end -}}
