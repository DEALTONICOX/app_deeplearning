/**
 * Servidor estático mínimo para probar la app en el navegador (carpeta www/).
 * Uso: npm run servir [-- puerto]      (por defecto 5173)
 * Nota: en un teléfono, la cámara del navegador exige HTTPS; para eso use un
 * túnel (ngrok / cloudflared) o pruebe directamente con el APK.
 */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const raiz = join(fileURLToPath(new URL(".", import.meta.url)), "..", "www");
const puerto = Number(process.argv[2]) || 5173;
const tipos = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json", ".png": "image/png",
};

createServer(async (peticion, respuesta) => {
  const ruta = normalize(decodeURIComponent(new URL(peticion.url, "http://x").pathname));
  const archivo = join(raiz, ruta === "/" || ruta === "\\" ? "index.html" : ruta);
  if (!archivo.startsWith(raiz)) { respuesta.writeHead(403).end(); return; }
  try {
    const datos = await readFile(archivo);
    respuesta.writeHead(200, { "Content-Type": tipos[extname(archivo)] || "application/octet-stream" });
    respuesta.end(datos);
  } catch {
    respuesta.writeHead(404).end("No encontrado");
  }
}).listen(puerto, () => console.log(`App en http://localhost:${puerto}`));
