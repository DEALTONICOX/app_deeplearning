"""Comprueba que Guardar rechaza el servidor web y acepta la API nueva local."""
from playwright.sync_api import sync_playwright


with sync_playwright() as p:
    navegador = p.chromium.launch(channel='msedge',args=[
        '--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
    try:
        contexto = navegador.new_context()
        contexto.add_init_script("localStorage.setItem('urlApi','http://127.0.0.1:8001')")
        pagina = contexto.new_page()
        pagina.goto('http://127.0.0.1:5173')
        pagina.click('#btn-ajustes')
        pagina.fill('#entrada-url','http://127.0.0.1:5173')
        pagina.click('#btn-guardar')
        pagina.wait_for_selector('#estado-conexion.error')
        assert pagina.locator('#ajustes').evaluate('(d) => d.open')
        assert pagina.evaluate("localStorage.getItem('urlApi')")=='http://127.0.0.1:8001'
        pagina.fill('#entrada-url','http://127.0.0.1:8001')
        pagina.click('#btn-guardar')
        pagina.wait_for_function("!document.getElementById('ajustes').open")
        assert pagina.evaluate("localStorage.getItem('urlApi')")=='http://127.0.0.1:8001'
        print('OK: dirección incorrecta rechazada; API mejorada comprobada y guardada.')
    finally:
        navegador.close()
