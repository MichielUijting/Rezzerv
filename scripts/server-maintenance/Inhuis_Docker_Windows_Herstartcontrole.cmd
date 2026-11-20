@echo off
CLS
setlocal EnableExtensions DisableDelayedExpansion
rem INHUIS: uitsluitend uitlezen; geen Windows, Docker, database of onderhoudsacties.
set "INHUIS_RESTART_CHECK=%~f0"
where powershell.exe >nul 2>&1
if errorlevel 1 (
  CLS
  echo FOUT: Windows PowerShell ontbreekt; niets gewijzigd.
  pause
  exit /b 1
)
powershell.exe -NoProfile -NonInteractive -Command "$s=[IO.File]::ReadAllText($env:INHUIS_RESTART_CHECK);$m='# INHUIS_RESTART_POWERSHELL';$i=$s.LastIndexOf($m);if($i -lt 0){exit 3};& ([scriptblock]::Create($s.Substring($i+$m.Length)))"
set "INHUIS_RC=%ERRORLEVEL%"
CLS
echo ============================================================
echo INHUIS - DOCKER NA WINDOWS-AANMELDING CONTROLEREN
echo ============================================================
if "%INHUIS_RC%"=="0" (
  echo Controle afgerond. Geen serverinstellingen gewijzigd.
) else (
  echo Controle onvolledig. Raadpleeg het rapport in Downloads.
)
echo.
echo Rapport: Inhuis_Docker_Windows_Herstartcontrole_Resultaat.txt
echo Windows en Docker zijn NIET herstart.
pause
exit /b %INHUIS_RC%

# INHUIS_RESTART_POWERSHELL
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$folder=Join-Path $env:USERPROFILE 'Downloads'
if(-not(Test-Path -LiteralPath $folder -PathType Container)){$folder=$env:TEMP}
$report=Join-Path $folder 'Inhuis_Docker_Windows_Herstartcontrole_Resultaat.txt'
$baseline=Join-Path $folder 'Inhuis_Docker_Windows_Herstart_Baseline.json'
$lines=[System.Collections.Generic.List[string]]::new()
function Say([string]$s){$lines.Add($s)}
function YesNo([bool]$b){if($b){return 'JA'};return 'NEE'}
function DockerRead([string[]]$Arguments){
    try {
        $output=@(& docker.exe @Arguments 2>$null)
        if($LASTEXITCODE -ne 0){return @{ok=$false;text=''}}
        return @{ok=$true;text=($output -join [Environment]::NewLine)}
    } catch {return @{ok=$false;text=''}}
}
function DockerJson([string[]]$Arguments){
    $r=DockerRead $Arguments
    if(-not $r.ok -or -not $r.text){return $null}
    try{return ConvertFrom-Json -InputObject $r.text -ErrorAction Stop}
    catch{return $null}
}
function RunningIds([string[]]$Filters){
    $r=DockerRead (@('ps','-q')+$Filters)
    if(-not $r.ok){throw 'DOCKER_PS_MISLUKT'}
    if(-not $r.text){return}
    foreach($id in @($r.text -split '[\r\n]+' | Where-Object {$_ -match '^[0-9a-fA-F]{12,64}$'})){Write-Output ([string]$id)}
}
function Inspect([string]$Id){
    if($Id -notmatch '^[0-9a-fA-F]{12,64}$'){throw 'CONTAINER_ID_ONGELDIG'}
    $objects=@(DockerJson @('inspect',$Id))
    if($objects.Count -ne 1 -or -not $objects[0].State.Running){throw 'CONTAINER_NIET_UNIEK_OF_GESTOPT'}
    return $objects[0]
}
function Version([string]$Base){
    try{
        $v=Invoke-RestMethod -Uri ($Base+'/version.json') -TimeoutSec 5 -ErrorAction Stop
        if([string]$v.version -match '^Rezzerv-MVP-v[0-9]'){return [string]$v.version}
    }catch{}
    return ''
}
function Healthy([string]$Base){
    try{
        $h=Invoke-RestMethod -Uri ($Base+'/api/health') -TimeoutSec 5 -ErrorAction Stop
        return ($h.status -ceq 'ok' -and $h.datastore -ceq 'postgresql')
    }catch{return $false}
}
function AutoSetting {
    foreach($p in @((Join-Path $env:APPDATA 'Docker\settings-store.json'),(Join-Path $env:APPDATA 'Docker\settings.json'))){
        if(-not(Test-Path -LiteralPath $p -PathType Leaf)){continue}
        try{
            $j=Get-Content -LiteralPath $p -Raw | ConvertFrom-Json -ErrorAction Stop
            foreach($key in @('autoStart','autoStartEnabled','startOnLogin')){
                $prop=$j.PSObject.Properties[$key]
                if($null -ne $prop -and $prop.Value -is [bool]){
                    if($prop.Value){return 'AAN'}else{return 'UIT'}
                }
            }
        }catch{}
    }
    return 'ONBEKEND'
}
function LoginStart {
    try{
        $r=Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -ErrorAction Stop
        $p=$r.PSObject.Properties['Docker Desktop']
        if($null -ne $p -and -not [string]::IsNullOrWhiteSpace([string]$p.Value)){return $true}
    }catch{}
    try{
        $path=[Environment]::GetFolderPath('Startup')
        if(Test-Path -LiteralPath $path -PathType Container){
            return (@(Get-ChildItem -LiteralPath $path -File -ErrorAction SilentlyContinue |
                Where-Object {$_.Name -match 'Docker\s*Desktop'}).Count -gt 0)
        }
    }catch{}
    return $false
}
function RestartReady($c){
    return ($c.State.Running -and [string]$c.HostConfig.RestartPolicy.Name -in @('always','unless-stopped'))
}
function SnapshotEquals($before,$after){
    foreach($key in @('project','port','version','frontend_id','frontend_image','backend_id','backend_image','postgres_id','postgres_image')){
        if([string]$before.$key -cne [string]$after.$key){return $false}
    }
    return $true
}
Say 'INHUIS - DOCKER EN WINDOWS-AANMELDSTART - ALLEEN LEZEN'
Say ('Datum: '+(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'))
Say 'Geen mutaties aan Windows, Docker, PostgreSQL, containers, agent of Inhuis.'
Say 'Geen gebruikersdata, wachtwoorden, environmentwaarden of volledige lokale paden in rapport.'
Say ''
$stage='Windows/Docker-aanmelding'
$completed=$false
try{
    $boot=(Get-CimInstance Win32_OperatingSystem -ErrorAction Stop).LastBootUpTime.ToUniversalTime().ToString('o')
    $setting=AutoSetting
    $registered=LoginStart
    $process=@(Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue).Count -gt 0
    $loginReady=$process -and $setting -ne 'UIT' -and ($registered -or $setting -eq 'AAN')
    Say '[1] Docker Desktop bij Windows-aanmelding'
    Say ('Docker Desktop actief: '+(YesNo $process))
    Say ('Instelling automatisch starten: '+$setting)
    Say ('Windows-aanmeldregistratie aanwezig: '+(YesNo $registered))
    Say ('Aanmeldstart aannemelijk ingesteld: '+(YesNo $loginReady))
    if(-not(Get-Command docker.exe -ErrorAction SilentlyContinue)){throw 'DOCKER_CLI_ONTBREEKT'}
    $engine=DockerRead @('version','--format','{{.Server.Version}}')
    Say ('Docker-engine bereikbaar: '+(YesNo $engine.ok))
    if(-not $engine.ok){throw 'DOCKER_ENGINE_NIET_BEREIKBAAR'}
    Say ''
    $stage='Echte Inhuis-frontend bepalen'
    $candidates=[System.Collections.Generic.List[object]]::new()
    foreach($id in @(RunningIds @('--filter','label=com.docker.compose.service=frontend'))){
        $f=Inspect $id
        $proj=[string]$f.Config.Labels.'com.docker.compose.project'
        if(-not $proj){continue}
        foreach($mapping in @($f.NetworkSettings.Ports.'80/tcp'|Where-Object {$_})){
            $port=[string]$mapping.HostPort
            if($port -notmatch '^[0-9]{1,5}$' -or [int]$port -lt 1 -or [int]$port -gt 65535){continue}
            if([string]$mapping.HostIp -notin @('','0.0.0.0','127.0.0.1','::','::1')){continue}
            $root='http://127.0.0.1:'+$port
            $v=Version $root
            if($v -and (Healthy $root)){
                if(@($candidates|Where-Object {$_.front.Id -ceq $f.Id}).Count -eq 0){
                    $candidates.Add([pscustomobject]@{front=$f;project=$proj;port=$port;version=$v})
                }
            }
        }
    }
    Say '[2] Inhuis-runtime'
    Say ('Aantal unieke gezonde Inhuis-frontends: '+$candidates.Count)
    if($candidates.Count -ne 1){throw 'INHUIS_FRONTEND_NIET_UNIEK'}
    $app=$candidates[0]
    $front=$app.front
    $backendIds=@(RunningIds @('--filter',('label=com.docker.compose.project='+$app.project),'--filter','label=com.docker.compose.service=backend'))
    if($backendIds.Count -ne 1){throw 'INHUIS_BACKEND_NIET_UNIEK'}
    $backend=Inspect $backendIds[0]
    $fn=@($front.NetworkSettings.Networks.PSObject.Properties.Name)
    $bn=@($backend.NetworkSettings.Networks.PSObject.Properties.Name)
    if(@($fn|Where-Object {$bn -contains $_}).Count -eq 0){throw 'FRONTEND_BACKEND_NETWERK_VERSCHILT'}
    Say ('Inhuis-versie: '+$app.version)
    Say ('Frontend-herstartbeleid: '+[string]$front.HostConfig.RestartPolicy.Name)
    Say ('Backend-herstartbeleid: '+[string]$backend.HostConfig.RestartPolicy.Name)
    Say 'Inhuis en PostgreSQL-health: JA'
    Say ''
    $stage='Fysieke PostgreSQL-container herkennen'
    $probe=DockerRead @('exec',[string]$backend.Id,'python','-m','app.maintenance.server_maintenance_host_probe')
    if(-not $probe.ok){throw 'POSTGRES_ADRES_NIET_LEESBAAR'}
    try{$info=ConvertFrom-Json -InputObject $probe.text -ErrorAction Stop}
    catch{throw 'POSTGRES_IDENTITEIT_NIET_LEESBAAR'}
    $address=([string]$info.database_runtime.server_address).Split('/')[0]
    $parsed=$null
    if(-not [Net.IPAddress]::TryParse($address,[ref]$parsed)){throw 'POSTGRES_ADRES_ONGELDIG'}
    $pg=[System.Collections.Generic.List[object]]::new()
    foreach($id in @(RunningIds @())){
        $c=Inspect $id
        foreach($ip in @($c.NetworkSettings.Networks.PSObject.Properties|ForEach-Object {$_.Value.IPAddress;$_.Value.GlobalIPv6Address}|Where-Object {$_})){
            $testIp=$null
            if([Net.IPAddress]::TryParse([string]$ip,[ref]$testIp) -and $testIp.Equals($parsed)){
                $pg.Add($c)
                break
            }
        }
    }
    if($pg.Count -ne 1){throw 'POSTGRES_CONTAINER_NIET_UNIEK'}
    $postgres=$pg[0]
    $imageKnown=([string]$postgres.Config.Image -match '(^|[/])postgres(:|@)')
    if(-not $imageKnown){
        $image=@(DockerJson @('image','inspect',[string]$postgres.Image))
        if($image.Count -eq 1){$imageKnown=@($image[0].RepoTags|Where-Object {$_ -match '(^|[/])postgres(:|@)'}).Count -gt 0}
    }
    if(-not $imageKnown){throw 'POSTGRES_IMAGE_NIET_HERKEND'}
    if(@($postgres.Mounts|Where-Object {$_.Type -in @('volume','bind')}).Count -lt 1){throw 'POSTGRES_DUURZAME_OPSLAG_NIET_HERKEND'}
    Say '[3] PostgreSQL'
    Say 'Fysieke databasecontainer via backendadres herkend: JA'
    Say ('PostgreSQL-herstartbeleid: '+[string]$postgres.HostConfig.RestartPolicy.Name)
    $ready=$loginReady -and (RestartReady $front) -and (RestartReady $backend) -and (RestartReady $postgres)
    Say ('Aanmeldstart en alle drie container-herstartbeleiden geschikt: '+(YesNo $ready))
    if(-not $ready){throw 'HERSTARTINSTELLINGEN_ONVOLDOENDE'}
    Say ''
    $stage='Technische baseline en nieuwe Windows-boot'
    Say '[4] Voor/na Windows-herstart'
    $now=[ordered]@{
        boot=$boot;project=$app.project;port=$app.port;version=$app.version
        frontend_id=[string]$front.Id;frontend_image=[string]$front.Image
        backend_id=[string]$backend.Id;backend_image=[string]$backend.Image
        postgres_id=[string]$postgres.Id;postgres_image=[string]$postgres.Image
    }
    $before=$null
    if(Test-Path -LiteralPath $baseline -PathType Leaf){
        try{$before=Get-Content -LiteralPath $baseline -Raw|ConvertFrom-Json -ErrorAction Stop}
        catch{throw 'BASELINE_ONLEESBAAR'}
    }
    if($null -eq $before -or [string]$before.boot -ceq $boot){
        $now|ConvertTo-Json -Depth 4|Set-Content -LiteralPath $baseline -Encoding UTF8 -ErrorAction Stop
        Say 'BASISCONTROLE GESLAAGD: terugkeer na Windows-herstart nog niet getest.'
    }else{
        $same=SnapshotEquals $before $now
        Say ('Andere Windows-boot vastgesteld: '+(YesNo ([string]$before.boot -cne $boot)))
        Say ('Dezelfde drie bestaande containers en images terug: '+(YesNo $same))
        if(-not $same){throw 'BESTAANDE_CONTAINERS_NIET_TERUG'}
        Say 'NA HERSTART GESLAAGD: Inhuis en dezelfde drie containers zijn bereikbaar.'
        $now|ConvertTo-Json -Depth 4|Set-Content -LiteralPath $baseline -Encoding UTF8 -ErrorAction Stop
    }
    Say 'Geen automatische Windows-herstart en geen formele onderhoudsvrijgave.'
    $completed=$true
}catch{
    Say ''
    Say ('ONVOLLEDIG BIJ: '+$stage)
    $e=[string]$_.Exception.Message
    if($e -match '^[A-Z_]{5,80}$'){Say ('Reden: '+$e)}
    else{Say ('Foutcategorie: '+$_.Exception.GetType().Name)}
    Say 'Geen Windows-, Docker- of Inhuis-instellingen gewijzigd.'
}
Say ''
Say ('UITKOMST: '+$(if($completed){'CONTROLE GESLAAGD'}else{'CONTROLE ONVOLLEDIG'}))
try{[IO.File]::WriteAllLines($report,$lines,[Text.UTF8Encoding]::new($false))}
catch{Write-Host 'Rapport schrijven mislukt; geen serverwijzigingen';exit 2}
if($completed){exit 0}else{exit 1}
