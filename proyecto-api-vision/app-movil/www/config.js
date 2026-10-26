/**
 * config.js — Configuración editable de la app.
 *
 * API_URL_POR_DEFECTO: dirección de la API (debe ser HTTPS en el teléfono).
 * Ejemplo: "https://mi-api.onrender.com". Si se deja vacía, la app pide la URL
 * en Ajustes la primera vez. El usuario puede cambiarla luego desde la app.
 */
window.CONFIG = {
  API_URL_POR_DEFECTO: "",
  FOTOGRAMAS_POR_CAPTURA: 3, // fotos consecutivas cuyas probabilidades se promedian
  PAUSA_ENTRE_FOTOGRAMAS_MS: 300,
  TIEMPO_MAXIMO_API_MS: 30000,
};
