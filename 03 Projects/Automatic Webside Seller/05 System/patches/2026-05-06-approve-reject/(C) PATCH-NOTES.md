# Patch 2026-05-06 — approve.ps1 + reject.ps1 (sub-step 4 of 5)

## Goal

Give Felix a one-line PowerShell command for the Stage 2 review step in `(C) Letter Send Pipeline.md`. Render PDFs (sub-step 3) → review in File Explorer → **approve or reject by tracking code** (this patch) → Letterxpress send (sub-step 5).

## Files added (2)

- **`approve.ps1`** — repo root. ~100 lines. Calls `POST /api/letters/{id}/approve` for each matching letter.
- **`reject.ps1`** — repo root. ~100 lines. Calls `POST /api/letters/{id}/reject` with required `-Reason` for each matching letter. Includes a `Read-Host` confirmation prompt before submitting (rejection is destructive — letter goes back to "must regenerate" if you want to recover it).

No code changes to `main.py` or `database.py` — both endpoints already exist from sub-step 3.

## What changed

### `approve.ps1`

Two modes:

```powershell
# Approve everything currently in pending_review
$env:AUTH_PASS = "p3t5o1STv09bGJioKl6PJA"
.\approve.ps1 -All

# Approve specific tracking codes only
.\approve.ps1 VB01,VB02,VB04,VB05,VB07,VB08
```

Pipeline:
1. `GET /api/letters?status=pending_review` → list of `{id, tracking_code, …}`.
2. Filter to `-All` or to the comma-list provided.
3. For each, `POST /api/letters/{id}/approve`. Print `OK` / `FAIL` per letter.
4. Summary line at the end. Exit code 0 on full success, 1 if any failed.

If a code in the comma-list isn't in `pending_review` (already approved, rejected, or doesn't exist), it's reported as a warning but doesn't fail the run.

### `reject.ps1`

```powershell
$env:AUTH_PASS = "p3t5o1STv09bGJioKl6PJA"
.\reject.ps1 VB03 -Reason "street number wrong"

# Multiple at once with the same reason
.\reject.ps1 VB03,VB07 -Reason "address parser mis-split city name"
```

Pipeline:
1. Same lookup as approve.ps1.
2. Lists what's about to be rejected, asks the user to **type `reject` to confirm**. Anything else cancels.
3. For each confirmed lead, `POST /api/letters/{id}/reject` with `{reason: "..."}` body.
4. Summary line.

Why the confirmation step: rejection is a one-way state transition for that letter row. Recovering means re-running `generate-letters.py` (which will fail with 409 because the tracking_code is still in the row — the row stays `rejected` for audit). The Read-Host gate prevents a typo (`.\reject.ps1 VB07` when you meant `.\approve.ps1 VB07`) from torching a good letter.

## Auth

Both scripts read `AUTH_PASS` from env by default. Override with `-Password` if you want. Username defaults to `admin`. Base URL defaults to `https://handwerkerweb.at`.

## Smoke tests

Need to be run AFTER sub-step 3 has populated the letters table with `pending_review` rows.

### Approve a single code

```powershell
$env:AUTH_PASS = "p3t5o1STv09bGJioKl6PJA"

# Generate one letter to have something to approve:
python generate-letters.py --codes VB02

# Approve it:
.\approve.ps1 VB02
# Expected:
#   Found 1 letter(s) with status=pending_review at https://handwerkerweb.at
#   OK    VB02  letter_id=N
#   Summary: 1 approved, 0 failed.

# Verify:
$cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:p3t5o1STv09bGJioKl6PJA"))
Invoke-RestMethod -Uri "https://handwerkerweb.at/api/letters?status=approved" `
    -Headers @{Authorization="Basic $cred"}
# Expected: row with tracking_code=VB02, status=approved
```

### Reject a code (dry test on a generated letter)

```powershell
python generate-letters.py --codes VB03
.\reject.ps1 VB03 -Reason "smoke-test rejection"
# Type "reject" at the prompt
```

### Approve everything in one go

```powershell
python generate-letters.py            # generate all 8
.\approve.ps1 -All
# Expected: Summary: N approved, 0 failed.
```

## Backwards compatibility

- No DB changes.
- No API changes (uses sub-step 3 endpoints).
- Adding new files only — no edits to existing files.

## How to deploy

These are local scripts — they don't need to ship to Railway. Just commit and push so the canonical repo has them.

```powershell
cd C:\Users\Felix\Desktop\business-finder
git add approve.ps1 reject.ps1
git add "Felix AI Brain/03 Projects/Automatic Webside Seller/05 System/patches/2026-05-06-approve-reject/"
git commit -m "feat: approve.ps1 + reject.ps1 (sub-step 4/5)"
git push
```

(Railway redeploys but nothing changes runtime-wise — the scripts run on Felix's PC, not on Railway.)

## What this does NOT do

- **Does not undo a rejection.** Once `letter_status='rejected'`, it stays. To resend that lead, regenerate it under a NEW tracking code (e.g. VB09, VB10) — the old row stays as audit trail.
- **Does not send anything.** Approval just moves the row to `approved` so `send-approved.py` (sub-step 5) will pick it up. Mailing is sub-step 5.
- **Does not edit the PDF.** If you find a typo during review, you fix the renderer/template, regenerate the PDF, then approve. The DB row's `pdf_bytes` BLOB is the immutable record of what got mailed.

## Rollback

Delete `approve.ps1` and `reject.ps1`. Or `git revert HEAD && git push`. Existing data unaffected — these scripts only read/transition state, they don't write anything irreversible.

## What comes next — sub-step 5 (Letterxpress send)

`send-approved.py`:
- Reads every `status='approved'` row from the `letters` table.
- For each: pulls the PDF blob, looks up the recipient address from the linked business, POSTs `setJob` to Letterxpress.
- Records the Letterxpress `job_id` in `letters.transaction_id`, transitions `status='sent'`.
- `--dry-run` prints what would be sent without calling the API.

After sub-step 5, you can mail the first batch.
