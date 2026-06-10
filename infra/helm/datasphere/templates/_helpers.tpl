{{- define "datasphere.fullname" -}}
{{- .Release.Name }}-datasphere
{{- end }}

{{- define "datasphere.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{ include "datasphere.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "datasphere.selectorLabels" -}}
app.kubernetes.io/name: datasphere
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
