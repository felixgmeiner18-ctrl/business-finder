<#
.SYNOPSIS
  Approve letters in the Railway letters table (pending_review -> approved).

.DESCRIPTION
  Calls POST /api/letters/{id}/approve for each matching letter.
  Letters must already be in 'pending_review' status; anything else gets
  a 409 from the server and is reported as FAIL.

.PARAMETER All
  Approve every letter currently in 'pending_review'.

.PARAMETER Codes
  Comma-separated tracking codes to approve (e.g. "VB01,VB02,VB04").
  Mutually exclusive with -All.

.PARAMETER BaseUrl
  Railway base URL. Defaults to https://handwerkerweb.at.

.PARAMETER User
  Basic auth user. Defaults to "admin".

.PARAMETER Password
  Basic auth password. Defaults to env var AUTH_PASS.

.EXAMPLE
  $env:AUTH_PASS = "p3t5o1STv09bGJioKl6PJA"
  .\approve.ps1 -All

.EXAMPLE
  .\approve.ps1 VB01,VB02,VB04

.EXAMPLE
  .\approve.ps1 -Codes VB02 -Password "..."
#>
[CmdletBinding(DefaultParameterSetName='Codes')]
param(
    [Parameter(ParameterSetName='All', Mandatory=$true)]
    [switch]$All,

    [Parameter(ParameterSetName='Codes', Position=0)]
    [string]$Codes,

    [string]$BaseUrl = "https://handwerkerweb.at",
    [string]$User    = "admin",
    [string]$Password = $env:AUTH_PASS
)

# ─── Pre-flight ─────────────────────────────────────────────────────────────

if (-not $Password) {
    Write-Error "Set AUTH_PASS env var or pass -Password. e.g. `$env:AUTH_PASS = '...'"
    exit 2
}
if (-not $All -and -not $Codes) {
    Write-Error "Provide either -All or -Codes 'VB01,VB02'."
    exit 2
}

$cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${User}:${Password}"))
$headers = @{ Authorization = "Basic $cred" }

# ─── Fetch pending letters ──────────────────────────────────────────────────

try {
    $resp = Invoke-RestMethod -Uri "$BaseUrl/api/letters?status=pending_review" -Headers $headers
}
catch {
    Write-Error "Failed to list pending letters: $_"
    exit 1
}

Write-Host ("Found {0} letter(s) with status=pending_review at {1}" -f $resp.total, $BaseUrl)

if ($resp.total -eq 0) {
    Write-Host "Nothing to approve."
    exit 0
}

# ─── Pick targets ───────────────────────────────────────────────────────────

if ($All) {
    $targets = $resp.rows
}
else {
    $codeList = $Codes -split ',' | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ }
    $allCodes = $resp.rows | ForEach-Object { $_.tracking_code }
    $missing  = $codeList | Where-Object { $allCodes -notcontains $_ }
    if ($missing) {
        Write-Warning ("Code(s) not in pending_review: {0}" -f ($missing -join ', '))
    }
    $targets = $resp.rows | Where-Object { $codeList -contains $_.tracking_code }
}

if (-not $targets) {
    Write-Host "No matching letters to approve."
    exit 0
}

# ─── Approve each ───────────────────────────────────────────────────────────

Write-Host ""
$ok = 0
$fail = 0
foreach ($l in $targets) {
    try {
        $r = Invoke-RestMethod `
            -Uri "$BaseUrl/api/letters/$($l.id)/approve" `
            -Method POST `
            -Headers $headers
        Write-Host ("  OK    {0}  letter_id={1}" -f $l.tracking_code, $l.id)
        $ok += 1
    }
    catch {
        $msg = $_.Exception.Message
        if ($_.Exception.Response) {
            try {
                $body = (New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd()
                $msg = "$msg :: $body"
            } catch {}
        }
        Write-Host ("  FAIL  {0}  {1}" -f $l.tracking_code, $msg) -ForegroundColor Red
        $fail += 1
    }
}

Write-Host ""
Write-Host ("Summary: {0} approved, {1} failed." -f $ok, $fail)
if ($fail -gt 0) { exit 1 }
