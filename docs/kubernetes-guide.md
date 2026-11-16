# Kubernetes deployment

This adds a way to run the whole application on any Kubernetes cluster (a laptop cluster, Azure AKS,
AWS EKS, Google GKE or your own) without changing the code. Docker Compose stays the way to develop;
Kubernetes is for running it for real.

**Status:** the manifests are rendered and checked against the Kubernetes schemas (locally and in CI),
and both scripts were run against a stand-in for `kubectl`. They have **not yet been run on a real
cluster**. Treat the first deployment as a test and expect to fix small things.

## What is in the repository

```
deploy/
  k8s/
    base/              the application: Neo4j, API, web app, ingress, network rules
    components/ollama/ optional: Ollama inside the cluster (CPU) with a job that downloads the models
    jobs/seed/         the one-off job that loads the synthetic data
    overlays/local/    laptop cluster: one copy of everything, no TLS
    overlays/production/ two copies of API and web, HTTPS, bigger disks, availability budgets
    secrets.env.example  template for the passwords (copy to secrets.env, never commit)
    kind-config.yaml   a local test cluster for kind
  scripts/
    dealcopilot.ps1    build, push, deploy, seed ... for Windows
    dealcopilot.sh     the same for macOS, Linux and CI
.github/workflows/images.yml   builds and publishes the images when you push a version tag
```

How the pieces fit (all in the namespace `dealcopilot`):

| Object | What it is | Notes |
|---|---|---|
| `neo4j` StatefulSet + disk | the database | one copy only (Community edition cannot cluster); data lives on a 10-20 GB disk |
| `api` Deployment + Service | FastAPI backend | stateless, so production runs two copies; only reachable from the web app |
| `frontend` Deployment + Service | Next.js web app | also forwards `/api/*` to the API |
| `dealcopilot` Ingress | the public address | the only thing exposed; allows 6 MB uploads |
| `ollama` (optional) | the language model server | CPU by default; GPU notes are in `ollama.yaml` |
| `dealcopilot-config` ConfigMap | settings | same names as in `docker-compose.yml` |
| `dealcopilot-secrets` Secret | passwords and signing key | created from `deploy/k8s/secrets.env` by the script |

## Try it on your laptop first (Windows)

You need Docker Desktop, `kubectl` and `kind` (`winget install Kubernetes.kubectl Kubernetes.kind`).
Run everything from the repository root.

```powershell
# 1. A local cluster and its web entrance (ingress controller)
kind create cluster --config deploy\k8s\kind-config.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=180s

# 2. Passwords (edit the new file: set NEO4J_PASSWORD and JWT_SECRET)
copy deploy\k8s\secrets.env.example deploy\k8s\secrets.env

# 3. Build the images, put them into the cluster, deploy, load the sample data
powershell -ExecutionPolicy Bypass -File deploy\scripts\dealcopilot.ps1 -Command build
powershell -ExecutionPolicy Bypass -File deploy\scripts\dealcopilot.ps1 -Command load
powershell -ExecutionPolicy Bypass -File deploy\scripts\dealcopilot.ps1 -Command deploy
powershell -ExecutionPolicy Bypass -File deploy\scripts\dealcopilot.ps1 -Command seed
```

Open <http://dealcopilot.localtest.me> (that name always points to your own computer).
Ollama keeps running on your machine as before; the pods reach it through `host.docker.internal`.
If the Copilot cannot reach it, start Ollama with `OLLAMA_HOST=0.0.0.0`.
Check with `-Command status`, read the API log with `-Command logs`.
Remove the test cluster with `kind delete cluster`.

## Deploy to a cloud cluster

1. **A cluster** with an ingress controller (`ingress-nginx` is assumed; for another one change
   `ingressClassName` in `base/ingress.yaml`) and, for HTTPS, [cert-manager](https://cert-manager.io)
   with a `ClusterIssuer`. Point your domain name at the ingress controller's public address.
2. **A registry** and a login: `az acr login -n NAME`, `aws ecr get-login-password | docker login ...`,
   `gcloud auth configure-docker REGION-docker.pkg.dev` or `docker login ghcr.io`.
   Let the cluster pull from it (AKS: attach the ACR; EKS/GKE: the default node roles work). For a
   private GitHub registry create a pull secret and add `imagePullSecrets` to the two Deployments.
3. **Passwords:** copy `deploy/k8s/secrets.env.example` to `secrets.env` with strong values.
4. **Deploy:**

```powershell
$env:REGISTRY = "ghcr.io/your-name"        # or myregistry.azurecr.io
powershell -ExecutionPolicy Bypass -File deploy\scripts\dealcopilot.ps1 -Command build -Registry $env:REGISTRY
powershell -ExecutionPolicy Bypass -File deploy\scripts\dealcopilot.ps1 -Command push  -Registry $env:REGISTRY
powershell -ExecutionPolicy Bypass -File deploy\scripts\dealcopilot.ps1 -Command deploy -Registry $env:REGISTRY -Overlay production -Domain deals.example.com
powershell -ExecutionPolicy Bypass -File deploy\scripts\dealcopilot.ps1 -Command seed   -Registry $env:REGISTRY
```

On macOS/Linux: `REGISTRY=... OVERLAY=production DOMAIN=... ./deploy/scripts/dealcopilot.sh deploy`.
Instead of building on your computer, push a tag (`git tag v1.0.0; git push --tags`) and
`images.yml` publishes both images to `ghcr.io/<owner>/dealcopilot-api` and `...-frontend`; then use
`-Tag v1.0.0` in the deploy command.

Things to check in `overlays/production/kustomization.yaml`: the ClusterIssuer name, disk sizes, and
whether to keep the `ollama` component. A language model on CPU is slow; for real use either add a GPU
node pool (see `components/ollama/ollama.yaml`) or run Ollama elsewhere, remove the component and set
`OLLAMA_BASE_URL` in the overlay.

## Day-to-day

| Task | How |
|---|---|
| New version | build, push, deploy with a new `-Tag`; pods are replaced one at a time |
| Roll back | `kubectl -n dealcopilot rollout undo deployment/api` (and `frontend`) |
| More copies | change `replicas` in the overlay (the database stays at one) |
| Change a setting | edit `base/configmap.yaml` or patch in the overlay, deploy again |
| Change a password | edit `secrets.env`, run `-Command secrets`, then `kubectl -n dealcopilot rollout restart deployment/api statefulset/neo4j` (changing `NEO4J_PASSWORD` after the first start also needs the password changed inside Neo4j) |
| Remove the app | `-Command delete` keeps the data disk; `kubectl delete namespace dealcopilot` removes everything |

**Backups:** the data is on the Neo4j disk. Use your cloud's volume snapshots (schedule them), or stop
Neo4j (`kubectl -n dealcopilot scale statefulset/neo4j --replicas=0`) and run `neo4j-admin database dump`
in a job that mounts the same disk. Practise a restore before you rely on it.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `ImagePullBackOff` | wrong `-Registry` or `-Tag`, not logged in, or the cluster cannot pull from the registry |
| Pod `Pending` with "unbound PersistentVolumeClaim" | no default storage class; set `storageClassName` in the overlay |
| 413 on a term sheet upload | another proxy in front of the ingress limits the body size; allow 6 MB |
| 502 or 503 right after deploy | pods still starting; Neo4j can take two minutes. `-Command status` |
| Sign-in loops on HTTPS | `COOKIE_SECURE` is `true` but the site is opened over plain `http`, or the reverse |
| API restarts | read `-Command logs`; a wrong `NEO4J_PASSWORD` after the database was first created is the usual cause |

## Not covered yet

- Real-cluster testing (see the status at the top).
- Secret management beyond a Kubernetes Secret: for a bank, use External Secrets or Sealed Secrets with
  the cloud's key vault.
- Autoscaling, resource tuning from real load, monitoring and alerts (Prometheus/Grafana), log shipping.
- A highly available database (needs Neo4j Enterprise or a managed service such as AuraDB).
- Read-only root file systems and pod security admission in `restricted` mode (the containers already
  run as non-root, without privilege escalation and with all capabilities dropped).
