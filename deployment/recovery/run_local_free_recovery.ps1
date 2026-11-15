#requires -Version 5.1
<#
Local-only restore + compaction of a verified HareMachi backup.
DOES NOT CONNECT TO, DELETE FROM, OR DEPLOY TO SUPABASE/RENDER.
On successful run creates a trimmed local pg_dump for later review.
Run from PowerShell in a trusted folder; review this script first.
#>
param(
  [string]$Backup = 'C:\Users\Vaio\Documents\Codex\2026-11-15\referenced-chatgpt-conversation-this-is-an\outputs\HareMachiBackup_20261115_193319_JST\hare_factory.dump',
  [string]$LocalPgUser = 'postgres',
  [string]$PgPort = '5432',
  [string]$OutputDir = "$HOME\Documents\HareMachiFreeRecovery"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ExpectedSha = 'cc226e9f0246bf41b1c4571ca67694082fb6a09e71bd8d9e444f77604755207e'
if (-not (Test-Path -LiteralPath $Backup -PathType Leaf)) {
  throw "The verified backup does not exist at $Backup. Pass -Backup <actual dump path>."
}
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Backup).Hash.ToLowerInvariant()
if ($hash -ne $ExpectedSha) { throw 'Backup SHA256 mismatch; refusing restore' }
foreach ($cmd in @('python','pg_restore','createdb','pg_dump','psql')) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Missing executable: $cmd. Install PostgreSQL 17 + Python and add bin paths to PATH." }
}
$driveName = [System.IO.Path]::GetPathRoot((Resolve-Path $Backup).Path)
$free = [IO.DriveInfo]::new($driveName).AvailableFreeSpace
if ($free -lt 8GB) {
  throw 'Less than 8 GiB free on backup volume; restore and VACUUM FULL may need temporary disk. Choose a volume with sufficient space.'
}
New-Item -Type Directory -Force -Path $OutputDir | Out-Null
$root = (Resolve-Path $OutputDir).Path
$uri = 'https://raw.githubusercontent.com/HamPen810/hare-machi-factory/335a4412706f49aed2a1a24ed98c58d081724c7c/deployment/recovery/'
$audit = Join-Path $root 'audit_local_backup.py'
$compact = Join-Path $root 'compact_restored_db.py'
Invoke-WebRequest -Uri ($uri + 'audit_local_backup.py') -OutFile $audit
Invoke-WebRequest -Uri ($uri + 'compact_restored_db.py') -OutFile $compact
$env:PGHOST='127.0.0.1'
$env:PGUSER=$LocalPgUser
$env:PGPORT=$PgPort
Write-Host 'Validating verified backup and restoring into NEW local-only PostgreSQL DB.'
$restoreOutput = & python -u $audit $Backup --sha256 $ExpectedSha --restore 2>&1
if ($LASTEXITCODE -ne 0) {
  $restoreOutput | ForEach-Object { Write-Host $_ }
  throw 'Local restore failed. Original backup was not modified.'
}
$restoreOutput | ForEach-Object { Write-Host $_ }
$dbLine = @($restoreOutput | ForEach-Object { [string]$_ } | Where-Object { $_ -match '^RESTORE_TARGET_NEW_DATABASE hare_recovery_audit_[0-9a-f]{10}$' })
if ($dbLine.Count -ne 1) { throw 'Restored database identifier was not found in tool output' }
$db = ($dbLine[0] -split ' ')[1]
if ($db -notmatch '^hare_recovery_audit_[0-9a-f]{10}$') { throw 'Unsafe database name' }
Write-Host "Inspecting $db before changes."
& python -u $compact --host 127.0.0.1 --db $db
if ($LASTEXITCODE -ne 0) { throw 'Local inspection failed' }
& python -u $compact --host 127.0.0.1 --db $db --apply --archive-confirmed
if ($LASTEXITCODE -ne 0) { throw 'Local compaction failed; original backup remains intact' }
Write-Host 'Reclaiming physical space in the LOCAL disposable DB only.'
foreach ($table in @('actions','market_ticks')) {
  & psql -X -v ON_ERROR_STOP=1 -d $db -c ("VACUUM FULL hare_factory."+$table+";")
  if ($LASTEXITCODE -ne 0) { throw "Local VACUUM FULL failed on $table" }
}
$bytes = (& psql -X -At -d $db -c "SELECT pg_database_size(current_database());").Trim()
if ($LASTEXITCODE -ne 0 -or $bytes -notmatch '^\d+$') { throw 'Physical DB size verification failed' }
Write-Host "LOCAL_COMPACTED_DATABASE_BYTES $bytes"
if ([int64]$bytes -ge 460MB) {
  Write-Warning 'Physical database remains >=460MiB; do not import into the 500MB free database yet. Additional safe compaction is required.'
  return
}
$target = Join-Path $root ('hare_factory_compacted_'+$db+'.dump')
& pg_dump -Fc -Z 6 -n hare_factory --no-owner --no-acl -f $target -d $db
if ($LASTEXITCODE -ne 0) { throw 'Local compacted backup export failed' }
$sum = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash
Write-Host "LOCAL_COMPACTED_BACKUP_CREATED $target"
Write-Host "LOCAL_COMPACTED_BACKUP_SHA256 $sum"
Write-Host 'DONE: original verified backup untouched; source Supabase and Render never contacted.'
