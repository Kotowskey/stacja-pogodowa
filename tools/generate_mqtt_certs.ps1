# Generuje self-signed PKI (CA + cert serwera) i plik haseł Mosquitto.
# Zgodnie z instrukcją TLS z Claude.html (MQTT-CA, port 8883).
#
# Użycie (PowerShell, z katalogu repo):
#   .\tools\generate_mqtt_certs.ps1
#   .\tools\generate_mqtt_certs.ps1 -ServerCn "raspberrypi.local" -SanIp "192.168.1.100"

param(
    [string]$CertsDir = "mosquitto/certs",
    [string]$PasswdFile = "mosquitto/config/passwd",
    [string]$CaCn = "MQTT-CA",
    [string]$ServerCn = "localhost",
    [string]$SanIp = "",
    [string]$Esp32Password = "iot-dev-pass",
    [string]$GatewayPassword = "iot-dev-pass",
    [int]$Days = 3650
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

New-Item -ItemType Directory -Force -Path $CertsDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $PasswdFile) | Out-Null

$caKey = Join-Path $CertsDir "ca.key"
$caCrt = Join-Path $CertsDir "ca.crt"
$serverKey = Join-Path $CertsDir "server.key"
$serverCsr = Join-Path $CertsDir "server.csr"
$serverCrt = Join-Path $CertsDir "server.crt"
$extFile = Join-Path $CertsDir "server.ext"

Write-Host "[certs] CA ($CaCn)..."
# ca.crt may be committed without ca.key (gitignored); without the key we cannot sign server.crt.
if ((Test-Path $caCrt) -and -not (Test-Path $caKey)) {
    Write-Host "[certs] brak ca.key — usuwam stary ca.crt i generuje CA od nowa..."
    Remove-Item -Force $caCrt, (Join-Path $CertsDir "ca.srl") -ErrorAction SilentlyContinue
}
if (-not (Test-Path $caCrt) -or -not (Test-Path $caKey)) {
    openssl genrsa -out $caKey 2048
    $caSubj = "/CN=$CaCn"
    openssl req -new -x509 -days $Days -key $caKey -out $caCrt -subj $caSubj
}

Write-Host "[certs] certyfikat serwera (CN=$ServerCn)..."
$sanLines = @(
    "DNS.1 = $ServerCn",
    "DNS.2 = raspberrypi.local"
)
if ($SanIp) {
    $sanLines += "IP.1 = $SanIp"
}
@"
[ v3_req ]
subjectAltName = @alt_names

[alt_names]
$($sanLines -join "`n")
"@ | Set-Content -Encoding ascii $extFile

openssl genrsa -out $serverKey 2048
$serverSubj = "/CN=$ServerCn"
openssl req -new -key $serverKey -out $serverCsr -subj $serverSubj
openssl x509 -req -in $serverCsr -CA $caCrt -CAkey $caKey -CAcreateserial `
    -out $serverCrt -days $Days -extfile $extFile -extensions v3_req

Remove-Item -Force $serverCsr, $extFile -ErrorAction SilentlyContinue

Write-Host "[certs] plik hasel MQTT ($PasswdFile)..."
python "$RepoRoot/tools/mqtt_passwd.py" -c "$PasswdFile" esp32_user "$Esp32Password"
python "$RepoRoot/tools/mqtt_passwd.py" "$PasswdFile" rpi_gateway "$GatewayPassword"

Write-Host ""
Write-Host "Gotowe:"
Write-Host "  CA (dla ESP32 / klientów): $caCrt"
Write-Host "  Serwer: $serverCrt"
Write-Host "  Uzytkownicy: esp32_user, rpi_gateway (haslo domyslne: $Esp32Password)"
Write-Host ""
Write-Host "Wgraj ca.crt na ESP32 (secrets.h) i uruchom: docker compose up -d mosquitto"
