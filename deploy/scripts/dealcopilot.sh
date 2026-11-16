#!/usr/bin/env bash
# Build the images and deploy Deal Copilot to a Kubernetes cluster (macOS, Linux, CI, WSL).
# Windows users: use scripts/dealcopilot.ps1, which does the same.
#
#   ./deploy/scripts/dealcopilot.sh <command>
#
# Commands
#   build     build the two Docker images (api, frontend)
#   push      push the images to REGISTRY (log in first: docker login ...)
#   load      load the images into a local kind cluster (no registry needed)
#   secrets   create or update the Kubernetes Secret from deploy/k8s/secrets.env
#   deploy    secrets + apply the manifests + wait until everything is running
#   seed      load the synthetic data (run once after the first deploy)
#   status    show pods, services and the ingress
#   logs      follow the API log
#   render    print the final manifests without touching the cluster
#   delete    remove the application (the Neo4j disk is kept; see the guide)
#
# Settings (environment variables)
#   REGISTRY  image registry path, e.g. ghcr.io/your-name or myregistry.azurecr.io
#   TAG       image tag; default: short git commit id
#   OVERLAY   local (default) or production
#   DOMAIN    public host name for production, e.g. deals.example.com (sets Ingress, TLS, CORS)
#   KIND_CLUSTER  kind cluster name for "load"; default: kind
#   DRY_RUN=1 print the commands instead of running them
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
K8S="$ROOT/deploy/k8s"
NS="dealcopilot"
OVERLAY="${OVERLAY:-local}"
REGISTRY="${REGISTRY:-}"
TAG="${TAG:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo latest)}"
DOMAIN="${DOMAIN:-}"
KIND_CLUSTER="${KIND_CLUSTER:-kind}"
PREFIX="${REGISTRY:+$REGISTRY/}"
API_IMAGE="${PREFIX}dealcopilot-api:${TAG}"
WEB_IMAGE="${PREFIX}dealcopilot-frontend:${TAG}"

# Print a command and run it (or only print it when DRY_RUN=1).
run() {
  echo "+ $*" >&2
  if [ "${DRY_RUN:-0}" != "1" ]; then "$@"; fi
}

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing tool: $1" >&2; exit 1; }; }

# Write .generated/<name>/kustomization.yaml: the chosen overlay plus the real image names, tag
# and (for production) the domain. The files in deploy/k8s never need editing for this.
generate() {
  local name="$1" target="$2" dir="$K8S/.generated/$1"
  mkdir -p "$dir"
  {
    echo "apiVersion: kustomize.config.k8s.io/v1beta1"
    echo "kind: Kustomization"
    echo "resources:"
    echo "  - ../../$target"
    echo "images:"
    echo "  - {name: dealcopilot-api, newName: ${PREFIX}dealcopilot-api, newTag: \"$TAG\"}"
    echo "  - {name: dealcopilot-frontend, newName: ${PREFIX}dealcopilot-frontend, newTag: \"$TAG\"}"
    if [ -n "$DOMAIN" ] && [ "$OVERLAY" = "production" ] && [ "$name" = "app" ]; then
      cat <<YAML
patches:
  - target: {kind: ConfigMap, name: dealcopilot-config}
    patch: |-
      - {op: replace, path: /data/CORS_ORIGINS, value: "https://$DOMAIN"}
  - target: {kind: Ingress, name: dealcopilot}
    patch: |-
      - {op: replace, path: /spec/rules/0/host, value: "$DOMAIN"}
      - {op: replace, path: /spec/tls/0/hosts/0, value: "$DOMAIN"}
YAML
    fi
  } > "$dir/kustomization.yaml"
}

cmd_build() {
  need docker
  run docker build -t "$API_IMAGE" "$ROOT/backend"
  run docker build -t "$WEB_IMAGE" "$ROOT/frontend"
}

cmd_push() {
  need docker
  [ -n "$REGISTRY" ] || { echo "Set REGISTRY first, e.g. REGISTRY=ghcr.io/your-name" >&2; exit 1; }
  run docker push "$API_IMAGE"
  run docker push "$WEB_IMAGE"
}

cmd_load() {
  need kind
  run kind load docker-image "$API_IMAGE" --name "$KIND_CLUSTER"
  run kind load docker-image "$WEB_IMAGE" --name "$KIND_CLUSTER"
}

cmd_secrets() {
  need kubectl
  local file="$K8S/secrets.env"
  [ -f "$file" ] || { echo "Missing $file. Copy secrets.env.example to secrets.env and fill it in." >&2; exit 1; }
  run kubectl create namespace "$NS" --dry-run=client -o yaml | run kubectl apply -f -
  # --from-env-file reads KEY=value lines (comments are ignored). The Secret never touches git.
  echo "+ kubectl -n $NS create secret generic dealcopilot-secrets --from-env-file=$file | kubectl apply -f -" >&2
  if [ "${DRY_RUN:-0}" != "1" ]; then
    kubectl -n "$NS" create secret generic dealcopilot-secrets --from-env-file="$file" \
      --dry-run=client -o yaml | kubectl apply -f -
  fi
}

cmd_deploy() {
  need kubectl
  cmd_secrets
  generate app "overlays/$OVERLAY"
  run kubectl apply -k "$K8S/.generated/app"
  run kubectl -n "$NS" rollout status statefulset/neo4j --timeout=300s
  run kubectl -n "$NS" rollout status deployment/api --timeout=300s
  run kubectl -n "$NS" rollout status deployment/frontend --timeout=300s
  echo "Deployed. Run '$0 status' to see the address. First time? Run '$0 seed' next."
}

cmd_seed() {
  need kubectl
  generate seed "jobs/seed"
  # A finished Job cannot be changed, so the old one is removed before the new run.
  run kubectl -n "$NS" delete job seed --ignore-not-found
  run kubectl apply -k "$K8S/.generated/seed"
  run kubectl -n "$NS" wait --for=condition=complete job/seed --timeout=300s
  run kubectl -n "$NS" logs job/seed --tail=20
}

cmd_status() {
  need kubectl
  run kubectl -n "$NS" get pods,svc,ingress,pvc
}

cmd_logs() {
  need kubectl
  run kubectl -n "$NS" logs deployment/api --follow --tail=100
}

cmd_render() {
  need kubectl
  generate app "overlays/$OVERLAY"
  kubectl kustomize "$K8S/.generated/app"
}

cmd_delete() {
  need kubectl
  generate app "overlays/$OVERLAY"
  run kubectl delete -k "$K8S/.generated/app" --ignore-not-found
  echo "The Neo4j disk (PVC data-neo4j-0) and the Secret were kept so no data is lost by accident."
  echo "To remove everything including data:  kubectl delete namespace $NS"
}

case "${1:-help}" in
  build) cmd_build ;;
  push) cmd_push ;;
  load) cmd_load ;;
  secrets) cmd_secrets ;;
  deploy) cmd_deploy ;;
  seed) cmd_seed ;;
  status) cmd_status ;;
  logs) cmd_logs ;;
  render) cmd_render ;;
  delete) cmd_delete ;;
  *) sed -n '2,29p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
esac
