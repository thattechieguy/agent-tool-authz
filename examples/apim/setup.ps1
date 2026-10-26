param(
    [Parameter(Mandatory = $true)] [string] $ResourceGroup,
    [Parameter(Mandatory = $true)] [string] $Location,
    [Parameter(Mandatory = $true)] [string] $ApimName,
    [Parameter(Mandatory = $true)] [string] $PublisherEmail
)

$ErrorActionPreference = "Stop"

az group create --name $ResourceGroup --location $Location --output none
az deployment group create `
  --resource-group $ResourceGroup `
  --template-file examples/apim/main.bicep `
  --parameters apimName=$ApimName publisherEmail=$PublisherEmail `
  --output none

Write-Host "APIM deployed: $ApimName in $ResourceGroup"
