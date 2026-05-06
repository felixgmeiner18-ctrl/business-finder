<#
.SYNOPSIS
  Reject a letter in the Railway letters table (pending_review -> rejected).

.DESCRIPTION
  Calls POST /api/letters/{id}/reject for each matching letter, with the
  required -Reason logged to the row for audit.
  Letter must be in 'pending_review' — any other status returns 409 from
  the server and is reported as FAIL.

.PARAMETER Codes
  Comma-separated tracking codes to reject (e.g. "VB03").

.PARAMETER Reason
  Required. Free-text explanation logged to the rejection_reason column.
  Keep it concrete: "street number wrong", "Kategorie mis-tagged", etc.

.PARAMETER BaseUrl
  Railway base URL. Defaults to https://handwerkerweb.at.

.PARAMETER User
  Basic auth user. Defaults to "admin".

.PARAMETER Password
  Basic auth password. Defaults to env var AUTH_PASS.

.EXAMPLE
  $env:AUTH_PASS = "p3t5o1STv09bGJioKl6PJA"
  .\reject.ps1 VB03 -Reason "street number wrong"

.EXAMPLE
  .\reject.ps1 -Codes VB03,VB07 -Reason "address parser mis-split city name"
#>
param(
    [Parameter(Position=0, Mandatory=$true)]
    [string]$Codes,

    [Parameter(Mandatory=$true)]
    [string]$Reason,

    [string]$BaseUrl = "https://handwerkerweb.at",
    [string]$User    = "admin",
    [string]$Password = $env:AUTH_PASS
)

# ─── Pre-flight ─────────────────────────────────────────────────────────────

if (-not $Password) {
    Write-Error "Set AUTH_PASS env var or pass -Password. e.g. `$env:AUTH_PASS = '...'"
    exit 2
}

$Reason = $Reason.Trim()
if (-not $Reason) {
    Write-Error "-Reason cannot be empty. Be concrete: 'street number wrong', etc."
    exit 2
}

$cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${User}:${Password}"))
$headers = @{ Authorization = "Basic $cred" }

# ─── Resolve codes to letter_ids ────────────────────────────────────────────

try {
    $resp = Invoke-RestMethod -Uri "$BaseUrl/api/letters?status=pending_review" -Headers $headers
}
catch {
    Write-Error "Failed to list pending letters: $_"
    exit 1
}

$codeList = $Codes -split ',' | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ }
$allCodes = $resp.rows | ForEach-Object { $_.tracking_code }
$missing  = $codeList | Where-Object { $allCodes -notcontains $_ }
if ($missing) {
    Write-Warning ("Code(s) not in pending_review: {0}" -f ($missing -join ', '))
}
$targets = $resp.rows | Where-Object { $codeList -contains $_.tracking_code }

if (-not $targets) {
    Write-Host "No matching letters to reject."
    exit 0
}

# ─── Confirm before rejecting ───────────────────────────────────────────────

Write-Host ""
Write-Host ("About to REJECT {0} letter(s) with reason: '{1}'" -f $targets.Count, $Reason) -ForegroundColor Yellow
$targets | ForEach-Object { Write-Host ("  - {0}  letter_id={1}" -f $_.tracking_code, $_.id) }
Write-Host ""
$confirm = Read-Host "Type 'reject' to confirm, anything else to cancel"
if ($confirm -ne 'reject') {
    Write-Host "Cancelled."
    exit 0
}

# ─── Reject each ────────────────────────────────────────────────────────────

Write-Host ""
$ok = 0
$fail = 0
$body = @{ reason = $Reason } | ConvertTo-Json
foreach ($l in $targets) {
    try {
        $r = Invoke-RestMethod `
            -Uri "$BaseUrl/api/letters/$($l.id)/reject" `
            -Method POST `
            -Headers $headers `
            -ContentType "application/json" `
            -Body $body
        Write-Host ("  OK    {0}  letter_id={1}" -f $l.tracking_code, $l.id)
        $ok += 1
    }
    catch {
        $msg = $_.Exception.Message
        if ($_.Exception.Response) {
            try {
                $errBody = (New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd()
                $msg = "$msg :: $errBody"
            } catch {}
        }
        Write-Host ("  FAIL  {0}  {1}" -f $l.tracking_code, $msg) -ForegroundColor Red
        $fail += 1
    }
}

Write-Host ""
Write-Host ("Summary: {0} rejected, {1} failed." -f $ok, $fail)
if ($fail -gt 0) { exit 1 }
