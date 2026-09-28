# Provision and configure the EDIM worker VM (undphq220vm001).
#
# The worker is the ONLY place the model solver stack runs. It consumes the
# Service Bus execution queue, runs the Calliope/MRIO model, uploads artifacts
# to Blob Storage, and reports progress + completion back on the completion
# queue. It has no database access.
#
# Cost posture: the VM is intended to be STOPPED when no model runs are needed.
# Start/stop is a deliberate manual action (see -Start / -Stop), not something
# this script does implicitly, because it is the single biggest cost lever.
#
# Usage:
#   powershell -File scripts/deploy_azure_worker_vm.ps1 -Plan          # show what would happen
#   powershell -File scripts/deploy_azure_worker_vm.ps1 -Create        # create VM + configure
#   powershell -File scripts/deploy_azure_worker_vm.ps1 -Status        # show state
#   powershell -File scripts/deploy_azure_worker_vm.ps1 -Start         # power on
#   powershell -File scripts/deploy_azure_worker_vm.ps1 -Stop          # deallocate (stops billing)
#   powershell -File scripts/deploy_azure_worker_vm.ps1 -UpdateImage   # rebuild the container on the VM
#
# IMPORTANT: this script never assigns Azure roles. Role assignments require
# elevated permissions (Microsoft.Authorization/roleAssignments/write). The
# required assignments are printed by -Plan and -Create.

[CmdletBinding(DefaultParameterSetName = "Plan")]
param(
    [Parameter(ParameterSetName = "Plan")][switch]$Plan,
    [Parameter(ParameterSetName = "Create")][switch]$Create,
    [Parameter(ParameterSetName = "Status")][switch]$Status,
    [Parameter(ParameterSetName = "Start")][switch]$Start,
    [Parameter(ParameterSetName = "Stop")][switch]$Stop,
    [Parameter(ParameterSetName = "UpdateImage")][switch]$UpdateImage,

    [string]$VmName = "undphq220vm001",
    [string]$VmSize = "Standard_B4s_v2",
    [int]$OsDiskGb = 64,
    [string]$Location = "westeurope",
    [string]$AdminUser = "edimadmin",
    [string]$GitRepo = "https://github.com/Ben-Keller/energy-development-modeling.git",
    [string]$GitBranch = "develop",
    # Optional: restrict inbound SSH to a single source CIDR (e.g. your office IP).
    # Leave empty for NO inbound management access at all - the UNDP
    # "Block management port access from the Internet" policy denies an NSG that
    # allows 22/3389 from Internet/*/any. Admin access is then via
    # `az vm run-command invoke`, which needs no inbound port.
    [string]$SshSourceIp = "",
    [switch]$SkipConfirmation
)

$ErrorActionPreference = "Stop"

# --- Fixed target (per project constraints) ---------------------------------
$ResourceGroup = "undphq220rg03"
$Subscription  = "72ccc0bc-4fb9-4b1d-95c0-a897f6e4ff74"

# Azure resources the worker talks to.
$ServiceBusNamespace = "undphq220sb001.servicebus.windows.net"
$StorageAccount      = "undphq220st02"
$BlobAccountUrl      = "https://undphq220st02.blob.core.windows.net/"

# Worker runtime configuration (must match the API's expectations).
#
# SIZING: Standard_B4s_v2 = 4 vCPU / 16 GB, matching the model manifest's
# declared resource_requirements {cpu: 4, memory_gb: 16}. The earlier B2s_v2
# candidate (2 vCPU / 8 GB) was half of that and would OOM on real runs.
#
# NO SWAP: verified via `az vm list-skus` that the whole Bsv2 series reports
# MaxResourceVolumeMB=0 and EphemeralOSDiskSupported=False - there is no local
# temp disk. On an OS-disk-backed swap a memory-hungry solver thrashes instead
# of failing fast, and this VM is disposable (artifacts go to Blob). Size the
# VM rather than adding swap.
#
# AUTH MODE: Path B uses shared-key connection strings. That is required while
# the operator account cannot create role assignments (Contributor excludes
# Microsoft.Authorization/*/Write). The code prefers a connection string over
# namespace/account-url, so these values win; the identity-based keys are kept
# as documentation of the intended end state. Rotate the keys once managed
# identity can be authorised, then delete the two CONNECTION_STRING entries.
$WorkerEnv = [ordered]@{
    "EDIM_SERVICEBUS_NAMESPACE"                   = $ServiceBusNamespace
    "EDIM_SERVICEBUS_QUEUE_NAME"                  = "execution-queue"
    "EDIM_SERVICEBUS_CANCELLATION_QUEUE_NAME"     = "cancellation-queue"
    "EDIM_SERVICEBUS_COMPLETION_QUEUE_NAME"       = "completion-queue"
    "EDIM_BLOB_ACCOUNT_URL"                       = $BlobAccountUrl
    "EDIM_BLOB_CONTAINER_PREFIX"                  = "stg-"
    "EDIM_SOLVER"                                 = "highs"
    "EDIM_DEVELOPMENT_ENGINE"                     = "mario"
    "EDIM_MARIO_TIMEOUT_SECONDS"                  = "120"
    "EDIM_MARIO_FAIL_ON_ERROR"                    = "false"
    # Matches the manifest's timeout_seconds (14400 = 4h). The previous value of
    # 3600 would have killed legitimate long analysis runs an hour in.
    "EDIM_WORKER_MAX_RUN_SECONDS"                 = "14400"
    "EDIM_WORKER_LOCK_RENEWAL_SECONDS"            = "60"
}

function Get-WorkerSecrets {
    # Fetch the two shared-key connection strings (Path B auth).
    #
    # Values are returned in-memory and written only to git-ignored files; they
    # are never printed to the console.
    $sb = az servicebus namespace authorization-rule keys list `
        -g $ResourceGroup --namespace-name "undphq220sb001" `
        --name RootManageSharedAccessKey --query "primaryConnectionString" -o tsv
    if (-not $sb) { throw "Could not read the Service Bus connection string." }

    $st = az storage account show-connection-string `
        -g $ResourceGroup -n $StorageAccount --query "connectionString" -o tsv
    if (-not $st) { throw "Could not read the storage connection string." }

    return @{ ServiceBus = $sb.Trim(); Storage = $st.Trim() }
}

function Write-Utf8NoBom {
    # Write a text file WITHOUT a UTF-8 byte-order mark.
    #
    # PowerShell 5.1's `Set-Content -Encoding utf8` emits a BOM (EF BB BF).
    # cloud-init rejects a user-data file that starts with a BOM, reporting:
    #   "Unhandled non-multipart (text/x-not-multipart) userdata:
    #    'b'\ufeff#cloud-config'...'"
    # and then silently runs nothing - no Docker, no clone, no image build.
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [System.IO.File]::WriteAllText($Path, $Content, (New-Object System.Text.UTF8Encoding($false)))
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$KeyDir   = Join-Path $RepoRoot ".local\worker-vm"
$SshKey   = Join-Path $KeyDir "id_edim_worker"
$NsgName  = "$VmName-nsg"

Write-Host "EDIM worker VM" -ForegroundColor Cyan
Write-Host "  resource group : $ResourceGroup"
Write-Host "  subscription   : $Subscription"
Write-Host "  vm             : $VmName ($VmSize, $Location)"
Write-Host "  repo           : $GitRepo @ $GitBranch"
Write-Host ""

function Get-Vm {
    # az writes "ResourceNotFound" to stderr when the VM is absent. With
    # $ErrorActionPreference = 'Stop' PowerShell turns that into a terminating
    # error, so relax the preference around this probe and rely on the exit code.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $json = az vm show -g $ResourceGroup -n $VmName -o json 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $json) { return $null }
        return ($json | Out-String) | ConvertFrom-Json
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Show-RequiredRoles {
    param([string]$PrincipalId)
    # With Path B (shared-key connection strings, set via --env-file) the worker
    # needs NO Azure role assignments: authentication is by key, not identity.
    # These assignments are only required to switch to managed identity later.
    Write-Host ""
    Write-Host "OPTIONAL: managed-identity roles (NOT required while Path B is in use)." -ForegroundColor DarkGray
    Write-Host "Assign these only when migrating off connection strings:" -ForegroundColor DarkGray
    $stgScope = "/subscriptions/$Subscription/resourceGroups/$ResourceGroup/providers/Microsoft.Storage/storageAccounts/$StorageAccount"
    $sbScope  = "/subscriptions/$Subscription/resourceGroups/$ResourceGroup/providers/Microsoft.ServiceBus/namespaces/undphq220sb001"
    Write-Host ""
    Write-Host "  az role assignment create --assignee-object-id $PrincipalId ``"
    Write-Host "    --assignee-principal-type ServicePrincipal ``"
    Write-Host "    --role `"Storage Blob Data Contributor`" --scope `"$stgScope`""
    Write-Host ""
    Write-Host "  az role assignment create --assignee-object-id $PrincipalId ``"
    Write-Host "    --assignee-principal-type ServicePrincipal ``"
    Write-Host "    --role `"Azure Service Bus Data Owner`" --scope `"$sbScope`""
    Write-Host ""
}

# ---------------------------------------------------------------------------
# -Plan
# ---------------------------------------------------------------------------
if ($Plan -or (-not $Create -and -not $Status -and -not $Start -and -not $Stop -and -not $UpdateImage)) {
    $existing = Get-Vm
    if ($existing) {
        Write-Host "VM already exists (state: $($existing.powerState))" -ForegroundColor Green
        Write-Host "  principal id: $($existing.identity.principalId)"
        Show-RequiredRoles -PrincipalId $existing.identity.principalId
    } else {
        Write-Host "VM does not exist yet. -Create would:" -ForegroundColor Yellow
        Write-Host "  1. Generate an SSH keypair at .local\worker-vm\ (git-ignored)"
        Write-Host "  2. Create $VmName ($VmSize, ${OsDiskGb}GB OS disk, Ubuntu 22.04, SSH-key auth only)"
        Write-Host "     with a system-assigned managed identity and a static public IP"
        Write-Host "     Sizing matches the model manifest requirement (4 vCPU / 16 GB)."
        Write-Host "  3. Create NSG '$NsgName' with no internet-facing management port"
        Write-Host "  4. Install Docker via cloud-init, clone the repo, build the worker image"
        Write-Host "  5. Install a systemd unit so the worker container restarts on boot"
        Write-Host ""
        Write-Host "No swap is configured: the Bsv2 series has no local temp disk, and on" -ForegroundColor DarkGray
        Write-Host "an OS-disk-backed swap a memory-hungry solver thrashes instead of failing." -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "Worker environment that will be configured:" -ForegroundColor Cyan
        $WorkerEnv.GetEnumerator() | ForEach-Object { "  {0,-44} = {1}" -f $_.Key, $_.Value }
        Write-Host ""
        Write-Host "The VM stays STOPPED until you run -Start (cost lever)." -ForegroundColor Yellow
        Show-RequiredRoles -PrincipalId "<principal-id shown after -Create>"
    }
    exit 0
}

# ---------------------------------------------------------------------------
# -Status
# ---------------------------------------------------------------------------
if ($Status) {
    $existing = Get-Vm
    if (-not $existing) { Write-Host "VM '$VmName' does not exist."; exit 0 }
    $view = az vm get-instance-view -g $ResourceGroup -n $VmName --query "{name:name,power:instanceView.statuses[?starts_with(code,'PowerState')].displayStatus | [0],ip:publicIps,size:hardwareProfile.vmSize,principal:identity.principalId}" -o json | ConvertFrom-Json
    $view | ConvertTo-Json
    exit 0
}

# ---------------------------------------------------------------------------
# -Start / -Stop
# ---------------------------------------------------------------------------
if ($Start) {
    az vm start -g $ResourceGroup -n $VmName -o none
    Write-Host "VM started. It bills while running - remember to -Stop when idle." -ForegroundColor Yellow
    exit 0
}

if ($Stop) {
    az vm deallocate -g $ResourceGroup -n $VmName -o none
    Write-Host "VM deallocated. Compute billing stopped (disk + IP still bill)." -ForegroundColor Green
    exit 0
}

# ---------------------------------------------------------------------------
# -UpdateImage : rebuild the worker container on the VM
# ---------------------------------------------------------------------------
if ($UpdateImage) {
    $existing = Get-Vm
    if (-not $existing) { throw "VM '$VmName' does not exist. Run -Create first." }
    Write-Host "Rebuilding the worker image on the VM (git pull + docker build)..." -ForegroundColor Cyan
    $script = @"
set -euo pipefail
cd /opt/edim
git fetch --all
git checkout $GitBranch
git pull --ff-only origin $GitBranch
docker build -f worker/Dockerfile -t edim-worker:latest .
systemctl restart edim-worker
sleep 5
systemctl --no-pager status edim-worker || true
"@
    # `az vm run-command invoke --command-id RunShellScript` executes the given
    # text with /bin/sh, which on Ubuntu is dash. Dash rejects bashisms, so the
    # `set -euo pipefail` above aborted the whole script on line 1 with
    # "set: Illegal option -o pipefail" and nothing was rebuilt.
    #
    # Ship the script as one line of base64 (quoting-safe ASCII, immune to
    # PowerShell expansion and to the run-command shell) and decode it into a
    # file that is then executed with bash explicitly.
    $script = $script -replace "`r`n", "`n"
    $payload = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($script))
    $command = "echo '$payload' | base64 -d > /tmp/edim-update-image.sh && bash /tmp/edim-update-image.sh"
    az vm run-command invoke -g $ResourceGroup -n $VmName --command-id RunShellScript --scripts $command --query "value[0].message" -o tsv
    exit 0
}

# ---------------------------------------------------------------------------
# -Create
# ---------------------------------------------------------------------------
if ($Create) {
    $existing = Get-Vm
    if ($existing) {
        Write-Host "VM '$VmName' already exists - nothing to create." -ForegroundColor Yellow
        Show-RequiredRoles -PrincipalId $existing.identity.principalId
        exit 0
    }

    if (-not $SkipConfirmation) {
        Write-Host "This creates a billable VM in $ResourceGroup." -ForegroundColor Yellow
        Write-Host "Size $VmSize. Keep it stopped when idle to minimise cost." -ForegroundColor Yellow
        $answer = Read-Host "Type 'create' to proceed"
        if ($answer -ne "create") { Write-Host "Aborted."; exit 1 }
    }

    # 1. SSH keypair (generated locally, git-ignored, never printed).
    #
    # Use ssh-keygen via cmd.exe rather than `az sshkey create`: the latter
    # requires an existing public key file (chicken-and-egg) and rejected the
    # path with "The value of parameter publicKey is invalid".
    #
    # cmd /c is used because Windows PowerShell 5.1 drops empty-string
    # arguments to native commands, which makes `-N ""` (empty passphrase)
    # impossible to express directly. The nested quoting below passes a
    # genuinely empty passphrase so the key is usable unattended.
    if (-not (Test-Path $KeyDir)) { New-Item -ItemType Directory -Path $KeyDir -Force | Out-Null }
    if (-not (Test-Path $SshKey)) {
        Write-Host "[1/5] Generating SSH keypair at .local\worker-vm\ ..."
        cmd /c "ssh-keygen -t rsa -b 4096 -f `"$SshKey`" -N `"`" -C edim-worker -q"
        if ($LASTEXITCODE -ne 0) { throw "ssh-keygen failed (exit $LASTEXITCODE)." }
    } else {
        Write-Host "[1/5] Reusing existing SSH keypair."
    }
    if (-not (Test-Path "$SshKey.pub")) { throw "SSH public key not found at $SshKey.pub" }

    # 2. Fetch credentials (Path B) and build the worker environment.
    Write-Host "[2/5] Reading connection strings (values not displayed)..."
    $secrets = Get-WorkerSecrets
    $workerEnv = [ordered]@{}
    foreach ($k in $WorkerEnv.Keys) { $workerEnv[$k] = $WorkerEnv[$k] }
    $workerEnv["EDIM_SERVICEBUS_CONNECTION_STRING"] = $secrets.ServiceBus
    $workerEnv["EDIM_BLOB_CONNECTION_STRING"] = $secrets.Storage
    Write-Host "      service bus: $($secrets.ServiceBus.Length) chars, storage: $($secrets.Storage.Length) chars"

    # Persist locally for the operator (git-ignored). Must be BOM-free so
    # tooling that reads it does not see a stray \ufeff prefix.
    $secretFile = Join-Path $KeyDir "worker-secrets.md"
    $secretContent = @"
# Worker VM credentials (git-ignored)

## EDIM_SERVICEBUS_CONNECTION_STRING
``````
$($secrets.ServiceBus)
``````

## EDIM_BLOB_CONNECTION_STRING
``````
$($secrets.Storage)
``````
"@
    Write-Utf8NoBom -Path $secretFile -Content $secretContent
    Write-Host "      written to .local\worker-vm\worker-secrets.md"

    # 3. cloud-init: Docker + repo clone + image build + systemd unit.
    Write-Host "[3/5] Preparing cloud-init (Docker, repo clone, image build)..."
    $envLines = ($workerEnv.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "`n"
    $cloudInit = @"
#cloud-config
package_update: true
packages:
  - docker.io
  - git
  - ca-certificates
runcmd:
  - systemctl enable --now docker
  - mkdir -p /opt/edim
  - git clone --branch $GitBranch $GitRepo /opt/edim
  - |
    cat > /opt/edim/.env.worker <<'ENVEOF'
$envLines
ENVEOF
  - cd /opt/edim && docker build -f worker/Dockerfile -t edim-worker:latest .
  - |
    cat > /etc/systemd/system/edim-worker.service <<'UNITEOF'
[Unit]
Description=EDIM worker (isolated model execution)
After=docker.service network-online.target
Requires=docker.service

[Service]
Restart=always
RestartSec=10
ExecStartPre=-/usr/bin/docker rm -f edim-worker
ExecStart=/usr/bin/docker run --rm --name edim-worker --env-file /opt/edim/.env.worker -v /opt/edim/outputs:/app/outputs edim-worker:latest
ExecStop=/usr/bin/docker stop -t 30 edim-worker

[Install]
WantedBy=multi-user.target
UNITEOF
  - systemctl daemon-reload
  - systemctl enable --now edim-worker
"@
    # cloud-init MUST be written without a BOM: Azure rejects user-data that
    # starts with EF BB BF and the VM silently never runs any of these steps.
    $cloudInitPath = Join-Path $KeyDir "cloud-init.yaml"
    Write-Utf8NoBom -Path $cloudInitPath -Content $cloudInit
    Write-Host "      cloud-init written (BOM-free, $((Get-Item $cloudInitPath).Length) bytes)"

    # 4. NSG. Required by the UNDP "Block management port access from the
    #    Internet" policy: an NSG whose rules allow inbound 22/3389 from
    #    Internet/*/any is DENIED. We therefore create the NSG up front with no
    #    internet-facing management rule and hand it to `az vm create`, which
    #    would otherwise auto-create a permissive NSG and fail the deployment.
    Write-Host "[4/5] Creating network security group '$NsgName'..."
    if ($SshSourceIp) {
        Write-Host "      inbound SSH restricted to $SshSourceIp"
    } else {
        Write-Host "      no inbound management access (admin via 'az vm run-command invoke')"
    }
    az network nsg create -g $ResourceGroup -n $NsgName -l $Location -o none
    if ($LASTEXITCODE -ne 0) { throw "Failed to create NSG '$NsgName'." }

    if ($SshSourceIp) {
        az network nsg rule create `
            -g $ResourceGroup --nsg-name $NsgName `
            -n AllowSshFromRestrictedSource --priority 1000 `
            --direction Inbound --access Allow --protocol Tcp `
            --source-address-prefixes $SshSourceIp `
            --destination-port-ranges 22 `
            -o none
        if ($LASTEXITCODE -ne 0) { throw "Failed to create the SSH NSG rule." }
    }

    # 5. Create the VM.
    #    --encryption-at-host is MANDATORY: the UNDP policy "Virtual machines
    #    and virtual machine scale sets should have encryption at host enabled"
    #    (Deny) blocks any VM without properties.securityProfile.encryptionAtHost.
    #    Verified prerequisites: the Microsoft.Compute/EncryptionAtHost feature
    #    is Registered, and Standard_B4s_v2 advertises EncryptionAtHostSupported.
    Write-Host "[5/5] Creating VM (this takes a few minutes)..."
    az vm create `
        --resource-group $ResourceGroup `
        --name $VmName `
        --location $Location `
        --image "Ubuntu2204" `
        --size $VmSize `
        --admin-username $AdminUser `
        --ssh-key-values "$SshKey.pub" `
        --os-disk-size-gb $OsDiskGb `
        --storage-sku Standard_LRS `
        --public-ip-sku Standard `
        --nsg $NsgName `
        --encryption-at-host `
        --assign-identity `
        --custom-data $cloudInitPath `
        --output none
    if ($LASTEXITCODE -ne 0) { throw "VM creation failed (exit $LASTEXITCODE)." }

    $vm = Get-Vm
    if (-not $vm) { throw "VM creation reported success but the VM was not found." }
    Write-Host "[5/5] VM created." -ForegroundColor Green
    Write-Host "  public IP    : $($vm.publicIps)"
    Write-Host "  principal id : $($vm.identity.principalId)"
    if ($SshSourceIp) {
        Write-Host "  ssh          : ssh -i .local/worker-vm/id_edim_worker $AdminUser@$($vm.publicIps)"
    } else {
        Write-Host "  shell        : az vm run-command invoke -g $ResourceGroup -n $VmName --command-id RunShellScript --scripts '<cmd>'"
    }
    Write-Host ""
    Write-Host "The worker container will start automatically once cloud-init finishes." -ForegroundColor Cyan
    Write-Host "Authentication uses Path B connection strings - no roles needed." -ForegroundColor Green
    Show-RequiredRoles -PrincipalId $vm.identity.principalId
    exit 0
}
