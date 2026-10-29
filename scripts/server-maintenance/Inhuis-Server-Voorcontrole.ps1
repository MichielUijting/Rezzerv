# Inhuis server: operationele voorcontrole (alleen lezen, geen beheeracties).
# Draaibaar met Windows PowerShell 5.1; officiële onderhoudsagent vereist PowerShell 7.4+.
# Bewust GEEN databasequery, Docker exec, Compose, start.bat, taakmutatie of secrets.
$ErrorActionPreference = 'Stop'
Clear-Host
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'
$downloads = Join-Path $env:USERPROFILE 'Downloads'
$report = Join-Path $downloads 'Inhuis_Server_Voorcontrole_Resultaat.txt'
$lines = New-Object 'System.Collections.Generic.List[string]'
function Add-Result([string]$text) { [void]$lines.Add($text) }
Add-Result 'INHUIS - SERVER VOORCONTROLE (ALLEEN LEZEN)'
Add-Result "Datum: $stamp"
Add-Result 'Geen start/stop, back-up, databasequery, configuratiewijziging of deployment.'
Add-Result ''
try {
    if (-not (Test-Path -LiteralPath $downloads -PathType Container)) {
        throw 'Downloads is niet toegankelijk; geen veilig resultaatbestand mogelijk.'
    }
    Add-Result "Windows PowerShell: $($PSVersionTable.PSVersion)"
    $pwsh = Get-Command 'pwsh.exe' -ErrorAction SilentlyContinue
    if ($null -eq $pwsh) {
        Add-Result 'Officiele agent PowerShell 7.4+: NIET AANGETOOND (pwsh.exe ontbreekt op PATH).'
    } else {
        $v = & $pwsh.Source -NoProfile -Command '$PSVersionTable.PSVersion.ToString()' 2>$null
        if ($LASTEXITCODE -ne 0) { Add-Result 'Officiele agent PowerShell: versie niet uitleesbaar.' }
        else { Add-Result "Officiele agent PowerShell: $v" }
    }
    $repo = 'C:\Inhuis_Server\Rezzerv'
    $agent = Join-Path $repo 'scripts\server-maintenance\Windows-Host-Agent.ps1'
    foreach ($entry in @(@('Repository',$repo),@('Officiele hostagent',$agent),@('Serverconfig','C:\Inhuis_Server\Serverconfig\docker-compose.server-local.yml'))) {
        Add-Result ("{0}: {1}" -f $entry[0],$(if(Test-Path -LiteralPath $entry[1]){'AANWEZIG'}else{'ONTBREEKT'}))
    }
    Add-Result ''
    $docker = Get-Command 'docker.exe' -ErrorAction SilentlyContinue
    if ($null -eq $docker) {
        Add-Result 'Docker CLI: ONTBREEKT'
    } else {
        $ver = & $docker.Source version --format '{{.Server.Version}}' 2>$null
        if ($LASTEXITCODE -eq 0) { Add-Result "Docker bereikbaar: $ver" }
        else { Add-Result 'Docker: niet bereikbaar.' }
        Add-Result 'Draaiende containers (naam, status, compose-project, service; geen configuratie/secrets):'
        $rows = & $docker.Source ps --format '{{.Names}} | {{.Status}} | {{.Label "com.docker.compose.project"}} | {{.Label "com.docker.compose.service"}}' 2>$null
        if ($LASTEXITCODE -eq 0) { foreach($r in @($rows)) { Add-Result ([string]$r) } }
        else { Add-Result 'Docker ps mislukt.' }
    }
    Add-Result ''
    Add-Result 'Bestaande Inhuis-onderhoudstaken (naam en status; geen taakacties/argumenten):'
    try {
        $tasks = @(Get-ScheduledTask -ErrorAction Stop | Where-Object { $_.TaskName -like 'Inhuis-Onderhoud-*' })
        if ($tasks.Count -eq 0) { Add-Result 'Geen Inhuis-Onderhoud-* taak gevonden.' }
        foreach ($t in $tasks) { Add-Result ("{0}: {1}" -f $t.TaskName,$t.State) }
    } catch { Add-Result 'Taakstatus niet uitleesbaar; geen wijziging uitgevoerd.' }
    Add-Result ''
    Add-Result 'LET OP: deze inventarisatie bevestigt NIET welke database actueel is.'
    Add-Result 'Vereist voor onderhouds-GO: officiële agentproof, echte backend/DB-identiteit en herstelproef.'
    Add-Result 'RESULTAAT: alleen inventarisatie, GEEN toestemming tot herstart/upgrade.'
} catch {
    Add-Result 'RESULTAAT: voorcontrole niet voltooid; geen wijzigingen uitgevoerd.'
    Add-Result ("Reden: " + $_.Exception.GetType().Name)
}
try {
    [IO.File]::WriteAllLines($report, [string[]]$lines, (New-Object Text.UTF8Encoding($true)))
    Clear-Host
    Write-Host 'INHUIS - SERVER VOORCONTROLE'
    Write-Host 'Alleen lezen. Geen wijzigingen aan Inhuis, Docker of de database.'
    Write-Host "Resultaat: $report"
    Write-Host 'Stuur dit ene TXT-bestand terug.'
} catch {
    Clear-Host
    Write-Host 'INHUIS - SERVER VOORCONTROLE'
    Write-Host 'Het rapport kon niet in Downloads worden opgeslagen.'
    Write-Host 'Er is niets gewijzigd.'
}
