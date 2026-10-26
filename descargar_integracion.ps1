<# Ejecutar desde PowerShell del usuario: .\descargar_integracion.ps1 -ConfigurarCredenciales #>
param([switch]$ConfigurarCredenciales, [switch]$Diagnostico)
$ErrorActionPreference = 'Stop'
$repositorio = Join-Path $PSScriptRoot 'proyecto-dataset-vision'
$pythonProyecto = Join-Path $PSScriptRoot 'proyecto-api-vision\venv\Scripts\python.exe'
$autenticacion = Join-Path $PSScriptRoot 'proyecto-api-vision\autenticar_drive.py'
if (-not (Test-Path -LiteralPath $pythonProyecto)) {
    throw 'Primero crea el venv e instala las dependencias siguiendo INSTALACION_INTEGRACION.md.'
}
$rama = & git -C $repositorio branch --show-current
if ($LASTEXITCODE -ne 0 -or $rama -ne 'integracion') {
    throw 'La copia del dataset debe estar en integracion.'
}
Push-Location $repositorio
try {
    if ($Diagnostico) {
        & $pythonProyecto $autenticacion --repositorio $repositorio --diagnostico
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo diagnosticar la sesión de Drive.' }
        return
    }
    if ($ConfigurarCredenciales) {
        $cliente = Read-Host 'ID de cliente OAuth entregado por el profesor'
        $secretoSeguro = Read-Host 'Secreto OAuth (oculto)' -AsSecureString
        $secretoTexto = [System.Net.NetworkCredential]::new('', $secretoSeguro).Password
        try {
            if ([string]::IsNullOrWhiteSpace($cliente) -or [string]::IsNullOrWhiteSpace($secretoTexto)) {
                throw 'El ID y el secreto no pueden estar vacíos.'
            }
            & $pythonProyecto -m dvc remote modify --local almacenamiento gdrive_client_id $cliente
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo configurar el ID de cliente.' }
            & $pythonProyecto -m dvc remote modify --local almacenamiento gdrive_client_secret $secretoTexto
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo configurar el secreto.' }
        } finally {
            Remove-Variable secretoTexto, secretoSeguro -ErrorAction SilentlyContinue
        }
    }
    # Sesión del usuario dentro de una ruta local que Git ya excluye (.dvc/tmp/).
    $archivoSesion = Join-Path $repositorio '.dvc\tmp\gdrive-user.json'
    New-Item -ItemType Directory -Path (Split-Path $archivoSesion) -Force | Out-Null
    & $pythonProyecto -m dvc remote modify --local almacenamiento gdrive_user_credentials_file $archivoSesion
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo configurar el archivo local de sesión.' }
    Write-Host 'Comprobando la sesión de Google. Si se abre el navegador, autoriza este intento una sola vez.'
    & $pythonProyecto $autenticacion --repositorio $repositorio
    if ($LASTEXITCODE -ne 0) { throw 'La sesión no quedó lista. Revisa el error anterior; no se repetirá la autorización automáticamente.' }
    $modoAnterior = [Environment]::GetEnvironmentVariable('GDRIVE_NON_INTERACTIVE', 'Process')
    try {
        $env:GDRIVE_NON_INTERACTIVE = '1'
        & $pythonProyecto -m dvc pull data/images.dvc --jobs 1
        if ($LASTEXITCODE -ne 0) { throw 'DVC no terminó la descarga. La sesión no se reabrirá: revisa el error de permisos, conexión u objetos faltantes.' }
    } finally {
        [Environment]::SetEnvironmentVariable('GDRIVE_NON_INTERACTIVE', $modoAnterior, 'Process')
    }
    Write-Host 'Descarga completada. Continúa con la auditoría antes de entrenar.'
} finally {
    Pop-Location
}
