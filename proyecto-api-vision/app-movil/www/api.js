/**
 * api.js — Cliente de la API de reconocimiento de personas.
 *
 * Endpoints usados:
 *   GET  /salud             -> estado del servicio y del modelo
 *   POST /predecir-fotos/   -> fotos completas; recorte compartido con entrenamiento
 *   POST /predecir-lote/    -> varias matrices 128x128x3; promedia las probabilidades
 *   POST /predecir-matriz/  -> una sola matriz 128x128x3
 */
const Api = (function () {
  /** Normaliza lo que escribe el usuario: agrega esquema y quita "/" final. */
  function normalizarUrl(texto) {
    let url = (texto || "").trim();
    if (!url) return "";
    if (!/^https?:\/\//i.test(url)) {
      // Una IP o "localhost" sin esquema se asume HTTP; un dominio, HTTPS.
      const esLocal = /^(localhost|\d{1,3}(\.\d{1,3}){3})(:\d+)?(\/|$)/i.test(url);
      url = (esLocal ? "http://" : "https://") + url;
    }
    return url.replace(/\/+$/, "");
  }

  /** fetch con límite de tiempo y mensajes de error comprensibles en español. */
  async function peticion(url, opciones, tiempoMaximoMs) {
    const controlador = new AbortController();
    const temporizador = setTimeout(() => controlador.abort(), tiempoMaximoMs);
    let respuesta;
    try {
      respuesta = await fetch(url, { ...opciones, signal: controlador.signal });
    } catch (error) {
      if (error.name === "AbortError") {
        throw new Error("La API tardó demasiado en responder. Inténtalo de nuevo.");
      }
      throw new Error(
        "No se pudo conectar con la API. Revisa la URL en Ajustes y tu conexión a internet."
      );
    } finally {
      clearTimeout(temporizador);
    }

    let cuerpo = null;
    try {
      cuerpo = await respuesta.json();
    } catch (_) {
      /* el cuerpo no era JSON */
    }
    if (!respuesta.ok) {
      if (respuesta.status === 501) {
        throw new Error("La dirección corresponde a un servidor que no acepta fotos. Revisa la URL de la API en Ajustes; el puerto 5173 sirve solamente la página.");
      }
      const detalle = cuerpo && cuerpo.detail ? cuerpo.detail : `Error ${respuesta.status}`;
      throw new Error(typeof detalle === "string" ? detalle : "La API rechazó la solicitud.");
    }
    return cuerpo;
  }

  async function salud(urlBase, tiempoMaximoMs) {
    const datos = await peticion(urlBase + "/salud", { method: "GET" }, tiempoMaximoMs || 10000);
    if (!datos || datos.estado !== "ok" || !Number.isInteger(datos.personas_en_base_de_datos)) {
      throw new Error("La dirección no responde como una API de reconocimiento. Revisa la URL.");
    }
    return datos;
  }

  function enviarJson(ruta, urlBase, carga, tiempoMaximoMs) {
    return peticion(
      urlBase + ruta,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(carga),
      },
      tiempoMaximoMs
    );
  }

  /** Envía varias matrices (valores 0-255); la API promedia y decide. */
  function predecirLote(urlBase, matrices, tiempoMaximoMs) {
    return enviarJson(
      "/predecir-lote/",
      urlBase,
      { matrices: matrices, normalizada: false },
      tiempoMaximoMs
    );
  }

  /** Envía una sola matriz (valores 0-255). */
  function predecirMatriz(urlBase, matriz, tiempoMaximoMs) {
    return enviarJson(
      "/predecir-matriz/",
      urlBase,
      { matriz: matriz, normalizada: false },
      tiempoMaximoMs
    );
  }

  function predecirFotos(urlBase, fotos, tiempoMaximoMs) {
    const carga = new FormData();
    fotos.forEach((foto, indice) => carga.append("archivos", foto, `fotograma_${indice}.jpg`));
    return peticion(urlBase + "/predecir-fotos/", { method: "POST", body: carga }, tiempoMaximoMs);
  }

  return {
    normalizarUrl: normalizarUrl,
    salud: salud,
    predecirLote: predecirLote,
    predecirMatriz: predecirMatriz,
    predecirFotos: predecirFotos,
  };
})();
