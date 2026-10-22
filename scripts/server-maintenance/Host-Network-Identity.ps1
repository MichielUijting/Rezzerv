# Pure network identity checks. Loading this file performs no host/Docker actions.
function ConvertTo-InhuisIPAddress {
    param([Parameter(Mandatory)][string]$Value)
    $parts=$Value.Split('/')
    if ($parts.Count -gt 2 -or $parts[0] -ne $parts[0].Trim() -or $parts[0].Contains('%')) {
        throw 'Ongeldig database-/containeradres.'
    }
    $address=$null
    if (-not [Net.IPAddress]::TryParse($parts[0], [ref]$address)) { throw 'Numeriek IP-adres vereist.' }
    $ipv4=$address.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork
    # .NET also accepts abbreviated, hexadecimal and octal IPv4. Reject these.
    if ($ipv4 -and $parts[0] -cne $address.ToString()) { throw 'Volledig decimaal IPv4-adres vereist.' }
    if ($parts.Count -eq 2) {
        $maximum=if ($ipv4) {32} else {128}
        if ($parts[1] -notmatch '^(0|[1-9][0-9]{0,2})$' -or [int]$parts[1] -gt $maximum) {
            throw 'Ongeldige IP-prefixlengte.'
        }
    }
    return $address
}

function Test-InhuisDatabaseServerAddress {
    param(
        [Parameter(Mandatory)][string]$DatabaseAddress,
        [Parameter(Mandatory)][string[]]$ContainerAddresses
    )
    $database=ConvertTo-InhuisIPAddress -Value $DatabaseAddress
    $addresses=@($ContainerAddresses | ForEach-Object { ConvertTo-InhuisIPAddress -Value $_ })
    if (-not $addresses.Count) { throw 'Geen containeradres aangetoond.' }
    # Compare the exact host, never merely membership of the CIDR network.
    return [bool](@($addresses | Where-Object { $database.Equals($_) }).Count)
}
