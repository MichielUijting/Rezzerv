#Requires -Version 7.4
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$EnvFile,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9][a-z0-9_-]+$')][string]$ComposeProject,
    [Parameter(Mandatory)][uri]$FrontendUrl,
    [Parameter(Mandatory)][uri]$ExternalUrl,
    [string]$DataDirectory = (Join-Path $env:LOCALAPPDATA 'Inhuis/Serveronderhoud'),
    [switch]$Once,
    [switch]$InstallAtLogon
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows) { throw 'De operationele agent vereist Windows; geen hostbewijs geproduceerd.' }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$EnvFile = (Resolve-Path -LiteralPath $EnvFile).Path
if (-not (Test-Path (Join-Path $RepoRoot 'docker-compose.postgresql.yml'))) { throw 'Officiele repository ontbreekt.' }
$ComposeArgs = @('compose','--project-name',$ComposeProject,'--env-file',$EnvFile,'-f',(Join-Path $RepoRoot 'docker-compose.yml'),'-f',(Join-Path $RepoRoot 'docker-compose.postgresql.yml'),'--profile','postgresql')

function Invoke-DockerText([string[]]$Arguments, [string]$InputText = '') {
    $psi = [Diagnostics.ProcessStartInfo]::new('docker.exe')
    $psi.UseShellExecute=$false; $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true
    $psi.RedirectStandardInput=$true
    foreach ($arg in $Arguments) { [void]$psi.ArgumentList.Add($arg) }
    $process=[Diagnostics.Process]::Start($psi)
    $out=$process.StandardOutput.ReadToEndAsync(); $err=$process.StandardError.ReadToEndAsync()
    if ($InputText) { $process.StandardInput.Write($InputText) }
    $process.StandardInput.Close()
    if (-not $process.WaitForExit(120000)) { throw 'Docker-controle duurt te lang; geen onderhoudstoestemming.' }
    $result=$out.GetAwaiter().GetResult(); [void]$err.GetAwaiter().GetResult()
    if ($process.ExitCode -ne 0) { throw 'Docker-controle mislukt; gevoelige uitvoer wordt niet gelogd.' }
    return $result.Trim()
}

function Copy-DockerBinary([string[]]$Arguments, [string]$Archive, [switch]$Restore) {
    $psi=[Diagnostics.ProcessStartInfo]::new('docker.exe')
    $psi.UseShellExecute=$false; $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true; $psi.RedirectStandardInput=$true
    foreach ($arg in $Arguments) { [void]$psi.ArgumentList.Add($arg) }
    $process=[Diagnostics.Process]::Start($psi)
    $errorTask=$process.StandardError.ReadToEndAsync()
    if ($Restore) {
        $outputTask=$process.StandardOutput.ReadToEndAsync()
        $stream=[IO.File]::OpenRead($Archive)
        try { $stream.CopyTo($process.StandardInput.BaseStream) } finally { $stream.Dispose(); $process.StandardInput.Close() }
        [void]$outputTask.GetAwaiter().GetResult()
    } else {
        $process.StandardInput.Close()
        $stream=[IO.File]::Open($Archive,[IO.FileMode]::CreateNew)
        try { $process.StandardOutput.BaseStream.CopyTo($stream); $stream.Flush($true) } finally { $stream.Dispose() }
    }
    if (-not $process.WaitForExit(600000)) { throw 'Back-up-/herstelproef duurde te lang; verwerking blijft geblokkeerd.' }
    [void]$errorTask.GetAwaiter().GetResult()
    if ($process.ExitCode -ne 0) { throw 'Back-up-/herstelproef mislukt; geen onderhoudstoestemming.' }
}

function Get-Container([string]$Service) {
    $ids=@((Invoke-DockerText ($ComposeArgs+@('ps','-q',$Service))).Split("`n") | Where-Object { $_.Trim() })
    if ($ids.Count -ne 1) { throw 'Exact een actieve container per dienst vereist.' }
    $data=@((Invoke-DockerText @('inspect',$ids[0])) | ConvertFrom-Json)[0]
    if ($data.Config.Labels.'com.docker.compose.project' -ne $ComposeProject -or $data.Config.Labels.'com.docker.compose.service' -ne $Service -or -not $data.State.Running) { throw 'Containeridentiteit wijkt af.' }
    return $data
}

function Get-Sha([string]$Value) {
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($Value))).ToLowerInvariant()
}

function Assert-Fingerprint([string]$Container, [string]$User, [string]$Database, $Probe) {
    $raw=Invoke-DockerText @('exec','-i',$Container,'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U',$User,'-d',$Database) $Probe.fingerprint_sql
    $actual=@($raw.Split("`n") | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
    if ($actual.Count -ne $Probe.fingerprints.Count) { throw 'Herstelproef mist tabellen.' }
    for ($i=0;$i -lt $actual.Count;$i++) {
        if ($actual[$i].table -cne $Probe.fingerprints[$i].table -or $actual[$i].rows -ne $Probe.fingerprints[$i].rows -or $actual[$i].digest -cne $Probe.fingerprints[$i].digest) { throw 'Herstelproef/datafingerprint wijkt af.' }
    }
}

New-Item -ItemType Directory -Force -Path $DataDirectory | Out-Null
$ProofDirectory=Join-Path $DataDirectory 'Proof'
New-Item -ItemType Directory -Force -Path $ProofDirectory | Out-Null
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $DataDirectory '/inheritance:r' '/grant:r' "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Privemap kon niet worden beveiligd.' }
$privatePath=Join-Path $DataDirectory 'signing-key.dpapi'
$publicPath=Join-Path $ProofDirectory 'public.pem'
$rsa=[Security.Cryptography.RSA]::Create(3072)
if (Test-Path -LiteralPath $privatePath) {
    $secret=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($privatePath),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    $rsa.FromXmlString([Text.Encoding]::UTF8.GetString($secret))
    [Array]::Clear($secret,0,$secret.Length)
} else {
    [IO.File]::WriteAllBytes($privatePath,[Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($rsa.ToXmlString($true)),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser))
}
# PEM uses a fixed UTF-8/no-BOM representation; deployment pins these exact bytes.
[IO.File]::WriteAllText($publicPath,$rsa.ExportSubjectPublicKeyInfoPem(),[Text.UTF8Encoding]::new($false))
$hostId=Get-Sha ([string](Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Cryptography').MachineGuid)
Write-Host ('Host-ID: '+$hostId)
Write-Host ('Publieke sleutel SHA256: '+(Get-FileHash -LiteralPath $publicPath -Algorithm SHA256).Hash.ToLowerInvariant())
Write-Host ('Alleen deze bewijslocatie read-only aan backend koppelen: '+$ProofDirectory)
if ($InstallAtLogon) {
    # Explicit optional deployment step, never run by a local PO test or backend.
    $user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
    $scheduledArguments="-NoProfile -File `"$PSCommandPath`" -EnvFile `"$EnvFile`" -ComposeProject $ComposeProject -FrontendUrl `"$FrontendUrl`" -ExternalUrl `"$ExternalUrl`" -DataDirectory `"$DataDirectory`""
    $action=New-ScheduledTaskAction -Execute (Get-Command pwsh.exe).Source -Argument $scheduledArguments -WorkingDirectory $RepoRoot
    Register-ScheduledTask -TaskName ('Inhuis-Onderhoud-'+$ComposeProject) -Action $action -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $user) -Principal (New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive) -Description 'Levert ondertekend onderhoudsbewijs; herstart Windows nooit.' | Out-Null
    return
}

do {
    try {
        $backend=Get-Container 'backend'; $postgres=Get-Container 'postgres'
        $probe=(Invoke-DockerText @('exec',$backend.Id,'python','-m','app.maintenance.server_maintenance_host_probe')) | ConvertFrom-Json
        $boot=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')
        $available=[ordered]@{kind='availability';issued_at=[datetimeoffset]::UtcNow.ToString('o');host_id=$hostId;backend_container_id=$backend.Id;windows_boot=$boot}
        $availableBytes=[Text.Encoding]::UTF8.GetBytes(($available | ConvertTo-Json -Compress))
        $availableSignature=$rsa.SignData($availableBytes,[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)
        $availableEnvelope=@{payload=[Convert]::ToBase64String($availableBytes);signature=[Convert]::ToBase64String($availableSignature)} | ConvertTo-Json -Compress
        $availableTemp=Join-Path $ProofDirectory 'availability.tmp'
        [IO.File]::WriteAllText($availableTemp,$availableEnvelope,[Text.UTF8Encoding]::new($false))
        [IO.File]::Move($availableTemp,(Join-Path $ProofDirectory 'availability.json'),$true)
        if ($probe.state -notin @('draining','locked','verifying','blocked') -or -not $probe.cycle_id -or $probe.active_operations -ne 0) { if ($Once) { return }; Start-Sleep -Seconds 10; continue }
        $boot=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')
        $userEnv=@($postgres.Config.Env | Where-Object { $_.StartsWith('POSTGRES_USER=') })
        if ($userEnv.Count -ne 1) { throw 'PostgreSQL bootstrap-identiteit ontbreekt.' }
        $pgUser=$userEnv[0].Substring('POSTGRES_USER='.Length)
        $db=[string]$probe.database_runtime.database
        $identitySql="SELECT json_build_object('database',current_database(),'oid',oid::text,'started',pg_postmaster_start_time(),'cluster',(SELECT system_identifier::text FROM pg_control_system())) FROM pg_database WHERE datname=current_database()"
        $identity=(Invoke-DockerText @('exec',$postgres.Id,'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U',$pgUser,'-d',$db,'-c',$identitySql)) | ConvertFrom-Json
        $ips=@($postgres.NetworkSettings.Networks.PSObject.Properties | ForEach-Object { $_.Value.IPAddress })
        if ($identity.database -cne $db -or $identity.oid -cne $probe.database_runtime.database_oid -or ([datetimeoffset]$identity.started) -ne ([datetimeoffset]$probe.database_runtime.server_started_at) -or $probe.database_runtime.server_address -notin $ips) { throw 'Runtimeverbinding en fysieke PostgreSQL-container verschillen.' }
        $mounts=@($postgres.Mounts | Where-Object { $_.Type -in @('volume','bind') } | Sort-Object Destination | ForEach-Object { [ordered]@{ Type=$_.Type; Source=$_.Source; Destination=$_.Destination } })
        if (-not $mounts.Count) { throw 'Geen duurzame databaseopslag aangetoond.' }
        $volume=Get-Sha ($mounts | ConvertTo-Json -Compress -Depth 10)
        $cycle=[string]$probe.cycle_id
        if ($cycle -notmatch '^[a-f0-9-]{36}$') { throw 'Ongeldige onderhoudscyclus.' }
        $archive=Join-Path $DataDirectory ($cycle+'.dump')
        $receipt=Join-Path $DataDirectory ($cycle+'.backup.json')
        if (-not (Test-Path -LiteralPath $receipt)) {
            # Full custom archive is streamed as bytes, never through PowerShell text.
            Copy-DockerBinary @('exec',$postgres.Id,'pg_dump','-U',$pgUser,'-d',$db,'--format=custom','--no-owner','--no-privileges') $archive
            $testName='inhuis-restore-'+[guid]::NewGuid().ToString('N')
            $testId=''
            try {
                # New isolated container only; no production mounts/network/ports.
                $testId=Invoke-DockerText @('run','-d','--name',$testName,'--label',('inhuis.maintenance.restore='+$cycle),'--network','none','--tmpfs','/var/lib/postgresql/data','-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_USER=postgres',$postgres.Image,'-c','shared_buffers=32MB','-c','max_connections=10')
                $ready=$false
                for ($i=0;$i -lt 60;$i++) {
                    try { [void](Invoke-DockerText @('exec',$testId,'pg_isready','-U','postgres')); $ready=$true; break } catch { Start-Sleep -Seconds 1 }
                }
                if (-not $ready) { throw 'Geisoleerde herstelomgeving niet gereed.' }
                Copy-DockerBinary @('exec','-i',$testId,'pg_restore','--exit-on-error','--clean','--if-exists','--no-owner','--no-privileges','-U','postgres','-d','postgres') $archive -Restore
                Assert-Fingerprint $testId 'postgres' 'postgres' $probe
                Assert-Fingerprint $postgres.Id $pgUser $db $probe
                $backup=[ordered]@{ cycle_id=$cycle; sha256=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant(); restored_and_compared=$true; restored_at=[datetimeoffset]::UtcNow.ToString('o'); domain_fingerprint=$probe.domain_fingerprint }
                [IO.File]::WriteAllText($receipt,($backup | ConvertTo-Json -Compress),[Text.UTF8Encoding]::new($false))
            } finally {
                if ($testId) {
                    $testInspect=@((Invoke-DockerText @('inspect',$testId)) | ConvertFrom-Json)[0]
                    if ($testInspect.Id -cne $testId -or $testInspect.Config.Labels.'inhuis.maintenance.restore' -cne $cycle -or $testInspect.Name -cne ('/'+$testName)) { throw 'Herstelcontainer-identiteit onzeker; niets verwijderd.' }
                    [void](Invoke-DockerText @('rm','-f',$testId))
                }
            }
        }
        $backup=Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
        if ($backup.sha256 -cne (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -or $backup.domain_fingerprint -cne $probe.domain_fingerprint) { throw 'Back-up of actuele data gewijzigd.' }
        $front=Invoke-WebRequest -Uri $FrontendUrl -TimeoutSec 15
        $external=Invoke-WebRequest -Uri $ExternalUrl -TimeoutSec 15
        if ($front.StatusCode -ne 200 -or $external.StatusCode -ne 200 -or $front.Content -notmatch '<title>Inhuis</title>' -or $external.Content -notmatch '<title>Inhuis</title>') { throw 'Frontend/externe route niet functioneel bereikbaar.' }
        foreach ($base in @($FrontendUrl,$ExternalUrl)) {
            $health=Invoke-RestMethod -Uri ([uri]::new($base,'/api/health')) -TimeoutSec 15
            $version=Invoke-RestMethod -Uri ([uri]::new($base,'/api/version')) -TimeoutSec 15
            $frontendVersion=Invoke-RestMethod -Uri ([uri]::new($base,'/version.json')) -TimeoutSec 15
            if ($health.status -cne 'ok' -or $health.datastore -cne 'postgresql' -or $health.database -cne $db -or $version.version -cne $probe.database_runtime.release_version -or $frontendVersion.version -cne $probe.database_runtime.release_version) { throw 'Backend/frontend/externe runtime niet gelijk of niet gereed.' }
        }
        $payload=[ordered]@{ cycle_id=$cycle; issued_at=[datetimeoffset]::UtcNow.ToString('o'); host_id=$hostId; windows_boot=$boot; backend_container_id=$backend.Id; backend_image=$backend.Image; compose_project=$ComposeProject; volume_identity=$volume; cluster_identity=$identity.cluster; database_runtime=$probe.database_runtime; domain_fingerprint=$probe.domain_fingerprint; backup=$backup; frontend_ready=$true; external_ready=$true }
        $bytes=[Text.Encoding]::UTF8.GetBytes(($payload | ConvertTo-Json -Compress -Depth 20))
        $signature=$rsa.SignData($bytes,[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)
        $envelope=@{payload=[Convert]::ToBase64String($bytes);signature=[Convert]::ToBase64String($signature)} | ConvertTo-Json -Compress
        $temp=Join-Path $ProofDirectory 'proof.tmp'
        [IO.File]::WriteAllText($temp,$envelope,[Text.UTF8Encoding]::new($false))
        [IO.File]::Move($temp,(Join-Path $ProofDirectory 'proof.json'),$true)
        Write-Host 'Actueel ondertekend onderhoudsbewijs vernieuwd. Windows wordt niet herstart.'
    } catch {
        # Never renew the signature after a failed check. Existing proof expires.
        Write-Warning 'Onderhoudsbewijs niet vernieuwd; controle mislukt. Inhuis blijft gesloten. Geen gevoelige details gelogd.'
        if ($Once) { throw }
    }
    if (-not $Once) { Start-Sleep -Seconds 10 }
} while (-not $Once)
