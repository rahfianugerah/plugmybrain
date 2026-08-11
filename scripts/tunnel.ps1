# The laptop side of the link to the VM. One SSH session carries both ports and restarts if it
# drops. Uses gcloud and the built-in Windows OpenSSH client; nothing new is installed.
#
#   9000 -> the Cognee MCP server, what Claude Code and Codex connect to
#  15432 -> Postgres, what `pmb list` and `pmb digest` use
#
# 15432 rather than 5432 on purpose: the laptop may run its own Postgres on 5432, and a forward
# onto an occupied port fails in a way that reads as a database problem.
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

# ExitOnForwardFailure is the important one. Without it a failed forward leaves a live SSH
# session and a dead port, which looks like the brain being broken rather than the tunnel.
$sshArgs = @(
    "-N",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "-o", "ExitOnForwardFailure=yes",
    "-L", "9000:127.0.0.1:8000",
    "-L", "15432:127.0.0.1:5432"
)

Write-Output "tunnel to $Vm ($Zone): 9000 -> MCP, 15432 -> postgres. Ctrl+C to stop."

while ($true) {
    gcloud compute ssh $Vm --tunnel-through-iap --zone $Zone @projectArg -- @sshArgs
    Write-Output "tunnel dropped at $(Get-Date -Format o). Reconnecting in 5s."
    Start-Sleep -Seconds 5
}
