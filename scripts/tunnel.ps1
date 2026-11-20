# The laptop side of the link to Postgres on the VM. One SSH session, restarted if it drops.
# The MCP server stays on the laptop, where the folders it digests are.
#
#   25432 > Postgres on the VM; set PMB_DB_HOST=host.docker.internal and PMB_DB_PORT=25432
#   25432, not 15432: the laptop stack publishes its own Postgres there
param(
    [string]$Vm      = $env:PMB_VM,
    [string]$Zone    = $env:PMB_ZONE,
    [string]$Project = $env:PMB_PROJECT
)

if (-not $Vm -or -not $Zone) {
    Write-Error "set PMB_VM and PMB_ZONE, or pass -Vm and -Zone"
    exit 1
}

$projectArg = if ($Project) { @("--project", $Project) } else { @() }

# ExitOnForwardFailure: a failed forward otherwise leaves a live session and a dead port
$sshArgs = @(
    "-N",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "-o", "ExitOnForwardFailure=yes",
    "-L", "25432:127.0.0.1:5432"
)

Write-Output "tunnel to $Vm ($Zone): 25432 > postgres. Ctrl+C to stop."

while ($true) {
    gcloud compute ssh $Vm --tunnel-through-iap --zone $Zone @projectArg -- @sshArgs
    Write-Output "tunnel dropped at $(Get-Date -Format o). Reconnecting in 5s."
    Start-Sleep -Seconds 5
}
