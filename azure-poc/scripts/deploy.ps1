[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ResourceGroup,
    [Parameter(Mandatory)] [string] $ApimName,
    [Parameter(Mandatory)] [string] $BackendApp,
    [Parameter(Mandatory)] [string] $ApprovalApp,
    [switch] $ConfirmAzureChanges
)

if (-not $ConfirmAzureChanges) {
    throw "Azure mutations are blocked. Review COPILOT_RUNBOOK.md and rerun with -ConfirmAzureChanges after explicit user approval."
}

Write-Host "This helper intentionally stops before mutations."
Write-Host "Execute the reviewed runbook steps manually: preflight, Entra/app settings, zip deployment, OpenAPI import, then baseline policy."
Write-Host "Required APIM named values: tenant-id, gateway-client-id, agent-client-id, backend-client-id, approval-service-url, approval-verify-key, orchestrator-signing-key."
Write-Host "No secrets or Azure commands are emitted by this scaffold helper."
