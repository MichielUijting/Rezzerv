@echo off
CLS
setlocal EnableExtensions DisableDelayedExpansion
set "INHUIS_SCRIPT=%~f0"
where powershell.exe >nul 2>&1
if errorlevel 1 (
 CLS
 echo FOUT: Windows PowerShell is niet beschikbaar. Er is niets gewijzigd.
 pause
 exit /b 1
)
powershell.exe -NoProfile -NonInteractive -Command "$x=[IO.File]::ReadAllText($env:INHUIS_SCRIPT);$m='# INHUIS_READONLY_CHECK';$p=$x.LastIndexOf($m);if($p -lt 0){exit 2};& ([scriptblock]::Create($x.Substring($p+$m.Length)))"
set "RC=%ERRORLEVEL%"
CLS
echo ==========================================================
echo INHUIS - POSTGRESQL IDENTITEIT DIAGNOSE
echo ==========================================================
if "%RC%"=="0" (echo GESLAAGD: database-identiteit is voldoende bevestigd.) else (echo NOG NIET BEWEZEN: bekijk het rapport.)
echo.
echo Rapport in Downloads: Inhuis_PostgreSQL_Identiteit_Diagnose_Resultaat.txt
echo Alleen gecontroleerd. Niets gestart, gestopt of hersteld.
pause
exit /b %RC%
# INHUIS_READONLY_CHECK
$ErrorActionPreference='Stop'
$folder=Join-Path $env:USERPROFILE 'Downloads'
if(-not(Test-Path -LiteralPath $folder -PathType Container)){$folder=$env:TEMP}
$report=Join-Path $folder 'Inhuis_PostgreSQL_Identiteit_Diagnose_Resultaat.txt'
$lines=[System.Collections.Generic.List[string]]::new()
function AddLine([string]$s){[void]$lines.Add($s)}
function CommandRead([string[]]$argsList){
  $out=@(& docker.exe @argsList 2>$null)
  if($LASTEXITCODE -ne 0){throw 'DOCKER_LEESACTIE_MISLUKT'}
  return ($out -join [Environment]::NewLine)
}
function InspectOne([string]$id){
  if($id -notmatch '^[0-9a-f]{12,64}$'){throw 'ONGELDIGE_CONTAINER_ID'}
  $raw=CommandRead @('inspect',$id)
  $v=@(ConvertFrom-Json -InputObject $raw)
  if($v.Count -ne 1 -or -not $v[0].State.Running){throw 'CONTAINER_NIET_ACTIEF'}
  return $v[0]
}
$success=$false
AddLine 'INHUIS - READ-ONLY DATABASE-IDENTITEIT DIAGNOSE'
AddLine ('Moment: '+(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
AddLine 'Geen wijzigingen aan Windows, Docker, Inhuis of PostgreSQL.'
AddLine ''
try{
  $boot=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime
  AddLine ('Windows laatst gestart: '+$boot.ToString('yyyy-MM-dd HH:mm:ss'))
  $desktop=@(Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue).Count -gt 0
  AddLine ('Docker Desktop actief: '+$(if($desktop){'JA'}else{'NEE'}))
  if(-not $desktop){throw 'DOCKER_DESKTOP_NIET_ACTIEF'}
  if(-not(Get-Command docker.exe -ErrorAction SilentlyContinue)){throw 'DOCKER_CLI_ONTBREEKT'}
  [void](CommandRead @('version','--format','{{.Server.Version}}'))
  AddLine 'Docker-engine bereikbaar: JA'
  $frontendIds=CommandRead @('ps','-q','--filter','label=com.docker.compose.service=frontend')
  $candidates=[System.Collections.Generic.List[object]]::new()
  foreach($id in @($frontendIds -split '[\r\n]+' | Where-Object {$_ -match '^[0-9a-f]{12,64}$'})){
    $f=InspectOne $id
    $project=[string]$f.Config.Labels.'com.docker.compose.project'
    if(-not $project){continue}
    foreach($entry in @($f.NetworkSettings.Ports.'80/tcp'|Where-Object {$_})){
      $port=[string]$entry.HostPort
      if($port -notmatch '^[0-9]{1,5}$'){continue}
      if([string]$entry.HostIp -notin @('','0.0.0.0','127.0.0.1','::','::1')){continue}
      $base='http://127.0.0.1:'+$port
      try{
        $v=Invoke-RestMethod ($base+'/version.json') -TimeoutSec 5
        $h=Invoke-RestMethod ($base+'/api/health') -TimeoutSec 5
        if([string]$v.version -match '^Rezzerv-MVP-v[0-9]' -and $h.status -ceq 'ok' -and $h.datastore -ceq 'postgresql'){
          $candidates.Add([pscustomobject]@{front=$f;project=$project;version=[string]$v.version})
        }
      }catch{}
    }
  }
  AddLine ('Gezonde Inhuis-frontends gevonden: '+$candidates.Count)
  if($candidates.Count -ne 1){throw 'GEZONDE_INHUIS_FRONTEND_NIET_UNIEK'}
  $a=$candidates[0]
  AddLine ('Inhuis-versie: '+$a.version)
  $backendIds=CommandRead @('ps','-q','--filter',('label=com.docker.compose.project='+$a.project),'--filter','label=com.docker.compose.service=backend')
  $ids=@($backendIds -split '[\r\n]+'|Where-Object {$_ -match '^[0-9a-f]{12,64}$'})
  if($ids.Count -ne 1){throw 'BACKEND_NIET_UNIEK'}
  $back=InspectOne $ids[0]
  AddLine 'Inhuis-backend actief: JA'
  $probe=CommandRead @('exec',[string]$back.Id,'python','-m','app.maintenance.server_maintenance_host_probe')
  $info=ConvertFrom-Json -InputObject $probe
  $addr=([string]$info.database_runtime.server_address).Split('/')[0]
  $ip=$null
  if(-not [Net.IPAddress]::TryParse($addr,[ref]$ip)){throw 'DATABASE_ADRES_ONBEKEND'}
  $all=CommandRead @('ps','-q')
  $matching=[System.Collections.Generic.List[object]]::new()
  foreach($id in @($all -split '[\r\n]+'|Where-Object {$_ -match '^[0-9a-f]{12,64}$'})){
    $c=InspectOne $id
    foreach($n in $c.NetworkSettings.Networks.PSObject.Properties){
      if([string]$n.Value.IPAddress -eq $addr -or [string]$n.Value.GlobalIPv6Address -eq $addr){$matching.Add($c);break}
    }
  }
  if($matching.Count -ne 1){throw 'DATABASECONTAINER_NIET_UNIEK'}
  $db=$matching[0]
  AddLine 'Databaseadres vanuit actieve Inhuis-backend koppelt aan exact een draaiende container: JA'
  AddLine ('Databasecontainer in hetzelfde Compose-project: '+$(if([string]$db.Config.Labels.'com.docker.compose.project' -ceq $a.project){'JA'}else{'NEE/ONBEKEND'}))
  AddLine ('Database Compose-servicenaam: '+$(if([string]$db.Config.Labels.'com.docker.compose.service'){$db.Config.Labels.'com.docker.compose.service'}else{'ONBEKEND'}))
  $imageText=[string]$db.Config.Image
  $imageIsPostgres=($imageText -match '(^|[/])postgres(:|@)')
  $imageByTag=$false
  try {
    $imageRaw=CommandRead @('image','inspect',[string]$db.Image)
    $imageObjs=@(ConvertFrom-Json -InputObject $imageRaw)
    if($imageObjs.Count -eq 1){
      $imageByTag=@($imageObjs[0].RepoTags|Where-Object {$_ -match '(^|[/])postgres(:|@)'}).Count -gt 0
    }
  }catch{AddLine 'Image-inspectie: niet beschikbaar (geen aanpassing uitgevoerd)'}
  AddLine ('PostgreSQL-image herkenbaar via configuratie: '+$(if($imageIsPostgres){'JA'}else{'NEE'}))
  AddLine ('PostgreSQL-image herkenbaar via lokale imagetags: '+$(if($imageByTag){'JA'}else{'NEE/ONBEKEND'}))
  $mounts=@($db.Mounts | Where-Object {$_ -and $_.Type -in @('volume','bind')})
  AddLine ('Aantal duurzame volume-/bindkoppelingen: '+$mounts.Count)
  $dataMounts=@($mounts|Where-Object {[string]$_.Destination -match '(^|/)var/lib/postgresql(/data)?(/|$)'})
  AddLine ('PostgreSQL-standaarddatapad als mount herkenbaar: '+$(if($dataMounts.Count -gt 0){'JA'}else{'NEE/ONBEKEND'}))
  AddLine ('Backend/API meldt PostgreSQL gezond: JA')
  AddLine ''
  AddLine '[Autostart bestaande containers]'
  $allPolicies=$true
  foreach($pair in @(@('Frontend',$a.front),@('Backend',$back),@('Database',$db))){
    $policy=[string]$pair[1].HostConfig.RestartPolicy.Name
    AddLine ($pair[0]+' automatisch herstartbeleid: '+$policy)
    if($policy -notin @('always','unless-stopped')){$allPolicies=$false}
  }
  AddLine ''
  if(($imageIsPostgres -or $imageByTag) -and $mounts.Count -ge 1 -and $allPolicies){
    AddLine 'CONCLUSIE: backend is gekoppeld aan een unieke draaiende PostgreSQL-container; image, duurzame opslag en herstartbeleid zijn bevestigd.'
    AddLine 'LET OP: identieke container-ID na reboot is zonder nulmeting voor reboot niet vast te stellen.'
    $success=$true
  }else{
    AddLine 'CONCLUSIE: Inhuis meldt PostgreSQL gezond, maar één of meer extra identiteit-/opslag-/herstartvoorwaarden zijn niet bevestigd.'
    AddLine 'Dit bewijst GEEN databasefout. Geen automatische reparatie uitvoeren.'
  }
}catch{
  $msg=[string]$_.Exception.Message
  if($msg -notmatch '^[A-Z_]{5,80}$'){$msg='ONVERWACHTE_LEESFOUT'}
  AddLine ('CONTROLE NIET GESLAAGD: '+$msg)
  AddLine 'Er is niets hersteld of gewijzigd.'
}
AddLine ''
AddLine ('RESULTAAT: '+$(if($success){'GESLAAGD'}else{'ONVOLLEDIG'}))
try{[IO.File]::WriteAllLines($report,$lines,[Text.UTF8Encoding]::new($false))}catch{exit 2}
if($success){exit 0}else{exit 1}
