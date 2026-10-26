"""Comprueba o inicia una sola autenticación DVC/Drive sin mostrar secretos."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import appdirs
from dvc.config import Config
from dvc_gdrive import GDriveFileSystem


def datos_sesion(repositorio: Path):
    config = Config(dvc_dir=str(repositorio / ".dvc"))
    remoto = config.get("remote", {}).get("almacenamiento", {})
    if not remoto:
        raise ValueError("No está configurado el remoto almacenamiento.")
    ruta = remoto.get("gdrive_user_credentials_file")
    if ruta:
        ruta = Path(ruta)
    else:
        ruta = (Path(appdirs.user_cache_dir("pydrive2fs", appauthor=False))
                / remoto.get("gdrive_client_id", GDriveFileSystem.DEFAULT_GDRIVE_CLIENT_ID)
                / f"{remoto.get('profile', 'default')}.json")
    return remoto, ruta


def diagnostico(remoto, ruta: Path) -> dict:
    resultado = {"cliente_configurado": bool(remoto.get("gdrive_client_id")),
                 "secreto_configurado": bool(remoto.get("gdrive_client_secret")),
                 "archivo_sesion_existe": ruta.is_file(),
                 "sesion_con_refresh_token": False, "sesion_invalida": None}
    if ruta.is_file():
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            resultado["sesion_con_refresh_token"] = bool(datos.get("refresh_token"))
            resultado["sesion_invalida"] = bool(datos.get("invalid", False))
        except (OSError, ValueError):
            resultado["sesion_invalida"] = True
    return resultado


def explicar_error(error: Exception) -> str:
    mensajes, tipos = [], []
    actual = error
    while actual is not None:
        mensajes.append(str(actual).lower())
        tipos.append(type(actual).__name__)
        actual = actual.__cause__ or actual.__context__
    texto = " ".join(mensajes)
    if "non interactive mode" in texto:
        return "No hay una sesión guardada utilizable. Ejecuta descargar_integracion.ps1 para completar un único inicio de sesión."
    if "invalid_client" in texto or "unauthorized_client" in texto:
        return "Google rechazó el ID/secreto OAuth. Vuelve a configurarlos con los valores del profesor."
    if "invalid_grant" in texto:
        return "Google rechazó el código o la sesión. Cancela los intentos anteriores y vuelve a autorizar una sola vez."
    if "scope" in texto:
        return "Los permisos devueltos por Google no coinciden con los solicitados. Revisa y acepta todos los permisos de Drive solicitados por esta conexión."
    if "redirect" in texto or "local web server" in texto:
        return "No se completó el retorno a localhost. Revisa los puertos 8080/8090 y que no haya otro intento de autenticación abierto."
    if "refresh_token" in texto:
        return "La sesión no incluye permiso de renovación; vuelve a autorizar el acceso sin conexión."
    if any(p in texto for p in ("ssl", "certificate", "timeout", "timed out", "connection", "resolve", "network")):
        return "Falló la conexión de Python con Google al completar la sesión. Revisa conexión, proxy y certificados."
    return "No se pudo completar la sesión de Drive (" + " -> ".join(tipos) + "). La descarga se detuvo sin reabrir Google."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repositorio", type=Path, required=True)
    parser.add_argument("--diagnostico", action="store_true")
    args = parser.parse_args()
    try:
        remoto, ruta = datos_sesion(args.repositorio.resolve())
        if args.diagnostico:
            print(json.dumps(diagnostico(remoto, ruta), ensure_ascii=False, indent=2))
            return 0
        if not remoto.get("gdrive_client_id") or not remoto.get("gdrive_client_secret"):
            raise ValueError("Falta configurar el ID/secreto OAuth del profesor.")
        # Una sola creación del cliente: evita que el recolector DVC inicie varios flujos.
        cliente = GDriveFileSystem(**remoto).fs
        credenciales = cliente.client.auth.credentials
        if not credenciales or credenciales.invalid or not credenciales.refresh_token:
            raise ValueError("La sesión no tiene refresh_token válido.")
        estado = diagnostico(remoto, ruta)
        if not estado["archivo_sesion_existe"] or not estado["sesion_con_refresh_token"]:
            raise ValueError("No se guardó el refresh_token en el archivo local de sesión.")
        print("Sesión de Google guardada y reutilizable. Iniciando descarga sin nuevas ventanas de autorización.")
        return 0
    except Exception as error:
        print("ERROR: " + explicar_error(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
