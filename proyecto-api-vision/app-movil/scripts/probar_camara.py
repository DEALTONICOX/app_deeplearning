"""Regresiones de cámara: solicitudes superpuestas y errores de reproducción."""
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    raiz = Path(__file__).resolve().parents[1] / "www"
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(raiz)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch(channel="msedge" if sys.platform == "win32" else None,
                args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
            try:
                contexto = navegador.new_context()
                contexto.add_init_script("""
                    localStorage.setItem('urlApi', 'http://127.0.0.1:8000');
                    window.oculto = false;
                    Object.defineProperty(document, 'hidden', {get: () => window.oculto});
                    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                    window.flujos = [];
                    let contador = 0;
                    navigator.mediaDevices.getUserMedia = async (opciones) => {
                      const numero = ++contador;
                      const flujo = await original(opciones);
                      window.flujos.push({numero, flujo});
                      if (numero === 1) await new Promise(r => setTimeout(r, 600));
                      return flujo;
                    };
                """)
                pagina = contexto.new_page()
                pagina.goto(f"http://127.0.0.1:{servidor.server_port}")
                pagina.wait_for_function("window.flujos.length === 1")
                pagina.evaluate("""() => {
                    window.oculto = true;
                    document.dispatchEvent(new Event('visibilitychange'));
                    window.oculto = false;
                    document.dispatchEvent(new Event('visibilitychange'));
                }""")
                pagina.wait_for_function("""window.flujos.length === 2 &&
                    window.flujos[0].flujo.getVideoTracks()[0].readyState === 'ended' &&
                    document.getElementById('video').readyState >= 2 &&
                    !document.getElementById('video').paused &&
                    document.getElementById('aviso-camara').hidden""")
                assert pagina.evaluate("document.getElementById('video').srcObject === window.flujos[1].flujo")
                assert pagina.evaluate("window.flujos.filter(f => f.flujo.getVideoTracks()[0].readyState === 'live').length") == 1
                print("OK: solicitud obsoleta cerrada y vista previa reanudada con un solo flujo activo.")
                contexto.close()

                contexto = navegador.new_context()
                contexto.add_init_script("""
                    localStorage.setItem('urlApi', 'http://127.0.0.1:8000');
                    HTMLMediaElement.prototype.play = () => Promise.reject(new Error('Fallo de reproducción simulado'));
                """)
                pagina = contexto.new_page()
                pagina.goto(f"http://127.0.0.1:{servidor.server_port}")
                pagina.wait_for_selector("#aviso-camara:not([hidden])")
                pagina.wait_for_function("document.getElementById('aviso-camara').textContent.includes('No se recibe video')")
                assert pagina.evaluate("document.getElementById('video').srcObject === null")
                assert pagina.is_visible("#etiqueta-archivo")
                print("OK: fallo de reproducción visible, cámara liberada y alternativa de archivo disponible.")
                contexto.close()
                print("2/2 regresiones de cámara aprobadas; prueba con cámara simulada.")
            finally:
                navegador.close()
    finally:
        servidor.shutdown()
        servidor.server_close()


if __name__ == "__main__":
    main()
