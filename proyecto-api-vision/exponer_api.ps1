<#
.SYNOPSIS
  Levanta la API en este PC y la publica con HTTPS mediante un túnel temporal de Cloudflare.

.DESCRIPTION
  1. Inicia uvicorn (app:app) en 127.0.0.1:<Puerto> usando el venv del proyecto.
  2. Inicia `cloudflared tunnel --url ...` (no requiere cuenta) y muestra la URL https://….trycloudflare.com.
  3. Verifica GET /salud a través de la URL pública.
  La URL cambia en cada ejecución y solo funciona mientras esta ventana siga abierta.
  Ctrl+C detiene el túnel y la API.

.EXAMPLE
  .\exponer_api.ps1
  .\exponer_api.ps1 -Puerto 8001 -Cloudflared C:\herramientas\cloudflared.exe
#>
param(
    [int]$Puerto = 8000,
    [string]$Cloudflared = "$env:LOCALAPPDATA\cloudflared\cloudflared.exe"
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path $Cloudflared)) {
    $comando = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($null -eq $comando) {
        throw "No se encontró cloudflared. Descárgalo de https://github.com/cloudflare/cloudflared/releases (cloudflared-windows-amd64.exe) y pásalo con -Cloudflared."
    }
    $Cloudflared = $comando.Source
}

$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "No existe venv\. Crea el entorno: py -3.12 -m venv venv; .\venv\Scripts\pip install -r requirements.txt" }

$registroTunel = Join-Path $env:TEMP "cloudflared_api_$Puerto.log"
Remove-Item $registroTunel -ErrorAction SilentlyContinue

Write-Host "Iniciando API en http://127.0.0.1:$Puerto ..."
$api = Start-Process $python -ArgumentList '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', $Puerto -PassThru -NoNewWindow
Write-Host "Iniciando túnel de Cloudflare ..."
$tunel = Start-Process $Cloudflared -ArgumentList 'tunnel', '--no-autoupdate', '--url', "http://127.0.0.1:$Puerto" `
    -RedirectStandardError $registroTunel -PassThru -WindowStyle Hidden

try {
    $url = $null
    for ($i = 0; $i -lt 60 -and -not $url; $i++) {
        Start-Sleep -Seconds 2
        if (Test-Path $registroTunel) {
            $coincidencia = Select-String -Path $registroTunel -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
            if ($coincidencia) { $url = $coincidencia.Matches[0].Value }
        }
    }
    if (-not $url) { throw "El túnel no entregó una URL. Revisa $registroTunel" }

    # La API tarda unos segundos en cargar TensorFlow y el modelo.
    $salud = $null
    for ($i = 0; $i -lt 30 -and -not $salud; $i++) {
        Start-Sleep -Seconds 3
        try { $salud = Invoke-RestMethod "$url/salud" -TimeoutSec 15 } catch { }
    }

    Write-Host ""
    Write-Host "URL pública (pégala en la app: Ajustes > URL de la API):" -ForegroundColor Green
    Write-Host "  $url" -ForegroundColor Green
    if ($salud) { Write-Host "  /salud -> estado=$($salud.estado), personas=$($salud.personas_en_base_de_datos)" }
    else { Write-Warning "La URL existe pero /salud aún no responde; espera unos segundos y prueba $url/salud" }
    Write-Host "Documentación: $url/docs"
    Write-Host "Ctrl+C para detener."
    Wait-Process -Id $api.Id
}
finally {
    foreach ($proceso in @($tunel, $api)) {
        if ($proceso -and -not $proceso.HasExited) { Stop-Process -Id $proceso.Id -Force }
    }
}
