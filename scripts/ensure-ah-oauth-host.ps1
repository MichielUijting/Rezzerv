param(
    [Parameter(Mandatory = $true)]
    [string]$Hostname,
    [string]$Address = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"

function Get-HostMappings {
    if (-not (Test-Path -LiteralPath $hostsPath)) {
        throw "Windows hosts-bestand niet gevonden: $hostsPath"
    }

    $rows = @()
    foreach ($line in Get-Content -LiteralPath $hostsPath -ErrorAction Stop) {
        $clean = ($line -split '#', 2)[0].Trim()
        if (-not $clean) { continue }
        $parts = @($clean -split '\s+' | Where-Object { $_ })
        if ($parts.Count -lt 2) { continue }
        $ip = $parts[0]
        foreach ($name in $parts[1..($parts.Count - 1)]) {
            $rows += [pscustomobject]@{ Address = $ip; Hostname = $name }
        }
    }
    return $rows
}

$mappings = @(Get-HostMappings)
$exact = $mappings | Where-Object {
    $_.Hostname -ieq $Hostname -and $_.Address -eq $Address
}
if ($exact) {
    Write-Host "[OK] AH OAuth-host bestaat al: $Address $Hostname"
    exit 0
}

$conflict = $mappings | Where-Object {
    $_.Hostname -ieq $Hostname -and $_.Address -ne $Address
}
if ($conflict) {
    Write-Error "AH OAuth-host $Hostname bestaat al met een ander adres. Er is niets gewijzigd."
    exit 2
}

$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
$isAdmin = $principal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
    Write-Host "[INFO] Eenmalige Windows-toestemming is nodig om $Hostname lokaal aan 127.0.0.1 te koppelen."
    $args = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"{0}"' -f $PSCommandPath),
        "-Hostname", ('"{0}"' -f $Hostname),
        "-Address", ('"{0}"' -f $Address)
    )
    try {
        $process = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru -ArgumentList $args
    }
    catch {
        Write-Error "Windows-toestemming voor de lokale AH OAuth-host is niet gegeven. Er is niets gewijzigd."
        exit 3
    }
    exit $process.ExitCode
}

$lineToAdd = $Address + [char]9 + $Hostname + " # Inhuis AH OAuth local development"
Add-Content -LiteralPath $hostsPath -Value $lineToAdd -Encoding ASCII
ipconfig /flushdns | Out-Null

$verified = @(Get-HostMappings) | Where-Object {
    $_.Hostname -ieq $Hostname -and $_.Address -eq $Address
}
if (-not $verified) {
    Write-Error "De lokale AH OAuth-host kon niet worden bevestigd."
    exit 4
}

Write-Host "[OK] Lokale AH OAuth-host toegevoegd: $Address $Hostname"
exit 0