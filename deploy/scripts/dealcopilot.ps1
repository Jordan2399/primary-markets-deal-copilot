<#
 Build the images and deploy Deal Copilot to a Kubernetes cluster (Windows PowerShell).
 The same commands exist for macOS/Linux/CI in dealcopilot.sh.

 Run from the repository root:
   powershell -ExecutionPolicy Bypass -File deploy\scripts\dealcopilot.ps1 -Command <command> [options]

 Commands
   build     build the two Docker images (api, frontend)
   push      push the images to -Registry (log in first: docker login ...)
   load      load the images into a local kind cluster (no registry needed)
   secrets   create or update the Kubernetes Secret from deploy\k8s\secrets.env
   deploy    secrets + apply the manifests + wait until everything is running
   seed      load the synthetic data (run once after the first deploy)
   status    show pods, services and the ingress
   logs      follow the API log
   render    print the final manifests without touching the cluster
   delete    remove the application (the Neo4j disk is kept; see the guide)

 Options
   -Registry     image registry path, e.g. ghcr.io/your-name or myregistry.azurecr.io
   -Tag          image tag; default: short git commit id
   -Overlay      local (default) or production
   -Domain       public host name for production, e.g. deals.example.com (sets Ingress, TLS, CORS)
   -KindCluster  kind cluster name for "load"; default: kind
   -DryRun       print the commands instead of running them
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("build", "push", "load", "secrets", "deploy", "seed", "status", "logs", "render", "delete")]
    [string]$Command,
    [string]$Registry = "",
    [string]$Tag = "",
    [ValidateSet("local", "production")]
    [string]$Overlay = "local",
    [string]$Domain = "",
    [string]$KindCluster = "kind",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$K8s = Join-Path $Root "deploy\k8s"
$Ns = "dealcopilot"

if (-not $Tag) {
    $Tag = (git -C $Root rev-parse --short HEAD 2>$null)
    if (-not $Tag) { $Tag = "latest" }
}
$Prefix = if ($Registry) { "$Registry/" } else { "" }
$ApiImage = "${Prefix}dealcopilot-api:${Tag}"
$WebImage = "${Prefix}dealcopilot-frontend:${Tag}"

# Print a command and run it (or only print it with -DryRun). Stops on the first failure.
function Run {
    param([string]$Exe, [string[]]$Arguments)
    Write-Host ("+ $Exe " + ($Arguments -join " ")) -ForegroundColor DarkGray
    if (-not $DryRun) {
        & $Exe @Arguments
        if ($LASTEXITCODE -ne 0) { throw "$Exe failed with exit code $LASTEXITCODE" }
    }
}

function Need([string]$Tool) {
    if (-not (Get-Command $Tool -ErrorAction SilentlyContinue)) { throw "Missing tool: $Tool" }
}

# Write .generated\<name>\kustomization.yaml: the chosen overlay plus the real image names, tag
# and (for production) the domain. The files in deploy\k8s never need editing for this.
function New-Overlay([string]$Name, [string]$Target) {
    $dir = Join-Path $K8s ".generated\$Name"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $yaml = @"
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../$Target
images:
  - {name: dealcopilot-api, newName: ${Prefix}dealcopilot-api, newTag: "$Tag"}
  - {name: dealcopilot-frontend, newName: ${Prefix}dealcopilot-frontend, newTag: "$Tag"}

"@
    if ($Domain -and $Overlay -eq "production" -and $Name -eq "app") {
        $yaml += @"
patches:
  - target: {kind: ConfigMap, name: dealcopilot-config}
    patch: |-
      - {op: replace, path: /data/CORS_ORIGINS, value: "https://$Domain"}
  - target: {kind: Ingress, name: dealcopilot}
    patch: |-
      - {op: replace, path: /spec/rules/0/host, value: "$Domain"}
      - {op: replace, path: /spec/tls/0/hosts/0, value: "$Domain"}

"@
    }
    # kustomize needs LF line endings and no byte-order mark.
    [System.IO.File]::WriteAllText((Join-Path $dir "kustomization.yaml"), ($yaml -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
    return $dir
}

function Do-Secrets {
    Need kubectl
    $file = Join-Path $K8s "secrets.env"
    if (-not (Test-Path $file)) { throw "Missing $file. Copy secrets.env.example to secrets.env and fill it in." }
    Write-Host "+ kubectl create namespace $Ns | kubectl apply" -ForegroundColor DarkGray
    Write-Host "+ kubectl -n $Ns create secret generic dealcopilot-secrets --from-env-file=$file | kubectl apply" -ForegroundColor DarkGray
    if (-not $DryRun) {
        kubectl create namespace $Ns --dry-run=client -o yaml | kubectl apply -f -
        if ($LASTEXITCODE -ne 0) { throw "creating the namespace failed" }
        # --from-env-file reads KEY=value lines (comments are ignored). The Secret never touches git.
        kubectl -n $Ns create secret generic dealcopilot-secrets "--from-env-file=$file" --dry-run=client -o yaml | kubectl apply -f -
        if ($LASTEXITCODE -ne 0) { throw "creating the secret failed" }
    }
}

switch ($Command) {
    "build" {
        Need docker
        Run docker @("build", "-t", $ApiImage, (Join-Path $Root "backend"))
        Run docker @("build", "-t", $WebImage, (Join-Path $Root "frontend"))
    }
    "push" {
        Need docker
        if (-not $Registry) { throw "Set -Registry first, e.g. -Registry ghcr.io/your-name" }
        Run docker @("push", $ApiImage)
        Run docker @("push", $WebImage)
    }
    "load" {
        Need kind
        Run kind @("load", "docker-image", $ApiImage, "--name", $KindCluster)
        Run kind @("load", "docker-image", $WebImage, "--name", $KindCluster)
    }
    "secrets" { Do-Secrets }
    "deploy" {
        Need kubectl
        Do-Secrets
        $dir = New-Overlay "app" "overlays/$Overlay"
        Run kubectl @("apply", "-k", $dir)
        Run kubectl @("-n", $Ns, "rollout", "status", "statefulset/neo4j", "--timeout=300s")
        Run kubectl @("-n", $Ns, "rollout", "status", "deployment/api", "--timeout=300s")
        Run kubectl @("-n", $Ns, "rollout", "status", "deployment/frontend", "--timeout=300s")
        Write-Host "Deployed. Run with -Command status to see the address. First time? Run -Command seed next." -ForegroundColor Green
    }
    "seed" {
        Need kubectl
        $dir = New-Overlay "seed" "jobs/seed"
        # A finished Job cannot be changed, so the old one is removed before the new run.
        Run kubectl @("-n", $Ns, "delete", "job", "seed", "--ignore-not-found")
        Run kubectl @("apply", "-k", $dir)
        Run kubectl @("-n", $Ns, "wait", "--for=condition=complete", "job/seed", "--timeout=300s")
        Run kubectl @("-n", $Ns, "logs", "job/seed", "--tail=20")
    }
    "status" {
        Need kubectl
        Run kubectl @("-n", $Ns, "get", "pods,svc,ingress,pvc")
    }
    "logs" {
        Need kubectl
        Run kubectl @("-n", $Ns, "logs", "deployment/api", "--follow", "--tail=100")
    }
    "render" {
        Need kubectl
        $dir = New-Overlay "app" "overlays/$Overlay"
        kubectl kustomize $dir
    }
    "delete" {
        Need kubectl
        $dir = New-Overlay "app" "overlays/$Overlay"
        Run kubectl @("delete", "-k", $dir, "--ignore-not-found")
        Write-Host "The Neo4j disk (PVC data-neo4j-0) and the Secret were kept so no data is lost by accident."
        Write-Host "To remove everything including data:  kubectl delete namespace $Ns"
    }
}
