@echo off
CLS
setlocal EnableExtensions DisableDelayedExpansion
set "INHUIS_SELF=%~f0"
where powershell.exe >nul 2>&1
if errorlevel 1 goto FAILED
where tailscale.exe >nul 2>&1
if errorlevel 1 goto FAILED
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$raw=[IO.File]::ReadAllText($env:INHUIS_SELF); $mark=':: INHUIS_PS_START'; $i=$raw.LastIndexOf($mark); if($i -lt 0){exit 1}; $code=$raw.Substring($i+$mark.Length); & ([scriptblock]::Create($code))"
if errorlevel 1 goto FAILED
CLS
echo GESLAAGD: de aparte AH-HTTPS-poort 8443 is bereikbaar.
echo De bestaande Inhuis HTTPS-verbinding op 443 is intact.
echo Rapport: Downloads\Inhuis_AH_HTTPS_8443_Resultaat.txt
pause
exit /b 0
:FAILED
CLS
echo VEILIG GESTOPT: AH HTTPS 8443 is niet bevestigd.
echo Geen Docker, database of gebruikersgegevens aangepast.
echo Zie het rapport in Downloads voor de concrete oorzaak.
pause
exit /b 1
:: INHUIS_PS_START
$ErrorActionPreference = 'Stop'
$report = Join-Path (Join-Path $env:USERPROFILE 'Downloads') 'Inhuis_AH_HTTPS_8443_Resultaat.txt'
$changes = 'Geen Tailscale-wijziging uitgevoerd'
try {
  $repo = Join-Path $env:USERPROFILE 'Rezzerv_CODEX_WORK'
  if (-not (Test-Path -LiteralPath (Join-Path $repo 'start.bat'))) {
    throw 'De officiele Inhuis-repository met start.bat ontbreekt'
  }
  $beforeText = & tailscale.exe serve status --json
  if ($LASTEXITCODE -ne 0) { throw 'Tailscale Serve-status kon niet worden gelezen' }
  $before = ($beforeText | Out-String | ConvertFrom-Json)
  if (-not $before -or -not $before.Web) { throw 'Bestaande HTTPS Serve-configuratie ontbreekt of is onleesbaar' }
  $entries = @($before.Web.PSObject.Properties)
  $main = @($entries | Where-Object { $_.Name -match ':443$' })
  if ($main.Count -ne 1) { throw 'Bestaande Inhuis HTTPS-poort 443 kon niet eenduidig worden vastgesteld' }
  $hostName = $main[0].Name -replace ':443$', ''
  if ($hostName -notmatch '^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+\.ts\.net$') {
    throw 'HTTPS-host is geen vertrouwd Tailscale DNS-adres'
  }
  $old443 = ($main[0].Value | ConvertTo-Json -Depth 20 -Compress)
  $existing = @($entries | Where-Object { $_.Name -match ':8443$' })
  $dest = 'http://127.0.0.1:8011'
  if ($existing.Count -gt 1) { throw 'Meerdere HTTPS-8443-configuraties: niets overschrijven' }
  if ($existing.Count -eq 1) {
    $actual = [string]$existing[0].Value.Handlers.'/'.Proxy
    if ($existing[0].Name -ne ($hostName + ':8443') -or $actual.TrimEnd('/') -ne $dest) {
      throw 'HTTPS-8443 is voor een andere bestemming in gebruik: veilig gestopt'
    }
  }
  $funnel = $before.AllowFunnel
  if ($funnel -and $funnel.PSObject.Properties[$hostName + ':8443'] -and $funnel.PSObject.Properties[$hostName + ':8443'].Value) {
    throw 'Poort 8443 is openbaar via Funnel: veilig gestopt'
  }
  $localBackend = Test-NetConnection -ComputerName 127.0.0.1 -Port 8011 -InformationLevel Quiet -WarningAction SilentlyContinue
  if (-not $localBackend) { throw 'Backend 127.0.0.1:8011 niet bereikbaar. Start Inhuis via de bestaande start.bat' }
  if ($existing.Count -eq 0) {
    & tailscale.exe serve --bg --https=8443 $dest
    if ($LASTEXITCODE -ne 0) { throw 'Tailscale kon de extra HTTPS-poort niet openen' }
    $changes = 'Uitsluitend HTTPS-poort 8443 toegevoegd voor de bestaande backend 8011'
  }
  $afterText = & tailscale.exe serve status --json
  if ($LASTEXITCODE -ne 0) { throw 'Tailscale-status na inrichting is onleesbaar' }
  $after = ($afterText | Out-String | ConvertFrom-Json)
  $new443 = $after.Web.PSObject.Properties[$hostName + ':443']
  $new8443 = $after.Web.PSObject.Properties[$hostName + ':8443']
  if (-not $new443 -or (($new443.Value | ConvertTo-Json -Depth 20 -Compress) -ne $old443)) {
    throw 'De bestaande HTTPS-443-configuratie is onverwacht veranderd'
  }
  if (-not $new8443 -or ([string]$new8443.Value.Handlers.'/'.Proxy).TrimEnd('/') -ne $dest) {
    throw 'De nieuwe HTTPS-8443-route klopt niet'
  }
  $null = Invoke-WebRequest -Uri ('https://' + $hostName + ':8443/openapi.json') -UseBasicParsing -TimeoutSec 15
  $message = 'GESLAAGD: AH HTTPS8443 bereikbaar met normale TLS-certificaatcontrole.' + [Environment]::NewLine + $changes + [Environment]::NewLine + 'Inhuis HTTPS443 behouden; geen Docker- of gebruikersdatawijziging.'
  Set-Content -LiteralPath $report -Value $message -Encoding UTF8
  exit 0
} catch {
  $message = ('VEILIG GESTOPT: ' + $_.Exception.Message) + [Environment]::NewLine + ('Status: ' + $changes) + [Environment]::NewLine + 'Geen Docker- of gebruikersdatawijziging.'
  try { Set-Content -LiteralPath $report -Value $message -Encoding UTF8 } catch { }
  Write-Host $message
  exit 1
}
