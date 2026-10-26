param([int]$Puerto = 8001)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:DIRECTORIO_MODELO = Join-Path $PSScriptRoot 'salidas_mejoradas'
if (-not (Test-Path (Join-Path $env:DIRECTORIO_MODELO 'galeria.npz'))) {
    throw 'Falta la galería. Ejecuta primero entrenar_rostros.py.'
}
& (Join-Path $PSScriptRoot 'venv\Scripts\python.exe') -m uvicorn app:app --host 127.0.0.1 --port $Puerto
