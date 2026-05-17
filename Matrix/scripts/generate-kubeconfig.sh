#!/usr/bin/env bash
# Generate a read-only kubeconfig for the OpenClaw ServiceAccount.
set -euo pipefail

namespace="saasphere-system"
secret_name="openclaw-reader-token"
server="https://192.168.1.202:6443"
output_path="${1:-}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required but was not found in PATH" >&2
  exit 1
fi

token="$(
  kubectl -n "${namespace}" get secret "${secret_name}" \
    -o jsonpath='{.data.token}' | base64 --decode
)"

ca_data="$(
  kubectl config view --raw \
    -o jsonpath='{.clusters[?(@.name=="default")].cluster.certificate-authority-data}'
)"

if [[ -z "${ca_data}" ]]; then
  ca_data="$(
    kubectl config view --raw \
      -o jsonpath='{.clusters[0].cluster.certificate-authority-data}'
  )"
fi

if [[ -z "${ca_data}" ]]; then
  echo "could not find certificate-authority-data in the current kubeconfig" >&2
  exit 1
fi

kubeconfig="$(
  cat <<EOF
apiVersion: v1
kind: Config
clusters:
  - name: saasphere
    cluster:
      certificate-authority-data: ${ca_data}
      server: ${server}
users:
  - name: openclaw-reader
    user:
      token: ${token}
contexts:
  - name: openclaw-reader@saasphere
    context:
      cluster: saasphere
      user: openclaw-reader
current-context: openclaw-reader@saasphere
EOF
)"

if [[ -n "${output_path}" ]]; then
  printf '%s\n' "${kubeconfig}" > "${output_path}"
  chmod 600 "${output_path}"
  verify_path="${output_path}"
else
  printf '%s\n' "${kubeconfig}"
  verify_path="<output>"
fi

cat >&2 <<EOF
Recommended verification:
kubectl --kubeconfig=${verify_path} auth can-i delete pods -n default   # debe devolver no
kubectl --kubeconfig=${verify_path} auth can-i list pods --all-namespaces  # debe devolver yes
EOF
