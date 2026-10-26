/**
 * app.js — Lógica de la interfaz.
 *
 * Flujo principal:
 *   1. Abre la cámara y muestra un visor cuadrado con una guía ovalada.
 *   2. Al pulsar "Identificar" captura fotos completas y las envía a la API,
 *      que aplica el recorte de rostro usado en el entrenamiento.
 *   3. Muestra el nombre o indica que no fue posible identificar.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const elementos = {
    video: $("video"),
    avisoCamara: $("aviso-camara"),
    contador: $("contador"),
    ayuda: $("ayuda"),
    btnIdentificar: $("btn-identificar"),
    btnVoltear: $("btn-voltear"),
    btnAjustes: $("btn-ajustes"),
    etiquetaArchivo: $("etiqueta-archivo"),
    entradaArchivo: $("entrada-archivo"),
    resultado: $("resultado"),
    ajustes: $("ajustes"),
    formularioAjustes: $("formulario-ajustes"),
    entradaUrl: $("entrada-url"),
    estadoConexion: $("estado-conexion"),
    btnProbar: $("btn-probar"),
    btnGuardar: $("btn-guardar"),
  };

  const estado = { flujo: null, camara: "user", ocupado: false, urlApi: "", inicioCamara: 0 };
  const CLAVE_URL = "urlApi";
  const TEXTO_AYUDA =
    "Coloca tu rostro dentro del óvalo, de frente y con buena luz.";

  // ---------------------------------------------------------------------------
  // Utilidades
  // ---------------------------------------------------------------------------
  const pausar = (ms) => new Promise((resolver) => setTimeout(resolver, ms));

  // localStorage puede lanzar errores (modo privado, datos bloqueados): se protege.
  function leerAjuste(clave) {
    try { return window.localStorage.getItem(clave) || ""; } catch (_) { return ""; }
  }
  function guardarAjuste(clave, valor) {
    try { window.localStorage.setItem(clave, valor); } catch (_) { /* sin persistencia */ }
  }

  function crear(etiqueta, clase, texto) {
    const nodo = document.createElement(etiqueta);
    if (clase) nodo.className = clase;
    if (texto !== undefined) nodo.textContent = texto; // textContent: nunca HTML de la API
    return nodo;
  }

  // ---------------------------------------------------------------------------
  // Cámara
  // ---------------------------------------------------------------------------
  function mostrarAvisoCamara(texto) {
    elementos.avisoCamara.textContent = texto;
    elementos.avisoCamara.hidden = false;
  }

  function detenerCamara() {
    estado.inicioCamara += 1; // invalida también solicitudes de cámara pendientes
    if (estado.flujo) {
      estado.flujo.getTracks().forEach((pista) => pista.stop());
      estado.flujo = null;
    }
    elementos.video.pause();
    elementos.video.srcObject = null;
  }

  async function iniciarCamara() {
    detenerCamara();
    const inicio = estado.inicioCamara;
    if (document.hidden) return false;
    mostrarAvisoCamara("Iniciando cámara…");

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      mostrarAvisoCamara(
        "La cámara no está disponible en este contexto (el navegador exige HTTPS). " +
        "Puedes elegir una foto del dispositivo."
      );
      elementos.etiquetaArchivo.hidden = false;
      return false;
    }

    try {
      const flujo = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: estado.camara },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });
      if (inicio !== estado.inicioCamara || document.hidden) {
        flujo.getTracks().forEach((pista) => pista.stop());
        return false;
      }
      estado.flujo = flujo;
      elementos.video.srcObject = flujo;
      elementos.video.muted = true;
      elementos.video.classList.toggle("espejo", estado.camara === "user");
      try {
        await elementos.video.play();
      } catch (error) {
        if (inicio !== estado.inicioCamara) return false;
        throw Object.assign(new Error("No se pudo reproducir la cámara."), { name: "ReproduccionCamara" });
      }
      if (inicio !== estado.inicioCamara) return false;
      if (!(await esperarVideoListo(inicio))) {
        if (inicio !== estado.inicioCamara) return false;
        throw Object.assign(new Error("La cámara no entrega video."), { name: "ReproduccionCamara" });
      }
      elementos.avisoCamara.hidden = true;
      flujo.getVideoTracks().forEach((pista) => pista.addEventListener("ended", () => {
        if (inicio === estado.inicioCamara) {
          detenerCamara();
          mostrarAvisoCamara("La cámara se desconectó. Pulsa Cambiar cámara para volver a conectarla.");
          elementos.etiquetaArchivo.hidden = false;
        }
      }));
      elementos.etiquetaArchivo.hidden = true;
      return true;
    } catch (error) {
      if (inicio !== estado.inicioCamara) return false;
      detenerCamara();
      const mensajes = {
        NotAllowedError: "Permiso de cámara denegado. Actívalo en los ajustes del teléfono y vuelve a abrir la app.",
        NotFoundError: "No se encontró ninguna cámara en este dispositivo.",
        NotReadableError: "La cámara está siendo usada por otra aplicación.",
        ReproduccionCamara: "No se recibe video de la cámara. Cierra otras apps o pestañas que la usen y pulsa Cambiar cámara para reintentar.",
      };
      mostrarAvisoCamara(mensajes[error.name] || "No se pudo abrir la cámara.");
      elementos.etiquetaArchivo.hidden = false;
      return false;
    }
  }

  async function esperarVideoListo(inicio = estado.inicioCamara) {
    for (let intento = 0; intento < 40; intento++) {
      if (inicio !== estado.inicioCamara || document.hidden) return false;
      if (elementos.video.srcObject && !elementos.video.paused &&
          elementos.video.videoWidth > 0 && elementos.video.readyState >= 2) return true;
      await pausar(100);
    }
    return false;
  }

  async function capturarFotogramas() {
    if (!(await esperarVideoListo())) {
      throw new Error("La cámara aún no está lista. Espera un momento e inténtalo otra vez.");
    }
    const total = window.CONFIG.FOTOGRAMAS_POR_CAPTURA;
    const fotos = [];
    for (let i = 0; i < total; i++) {
      elementos.contador.textContent = `${i + 1}/${total}`;
      elementos.contador.hidden = false;
      fotos.push(await Matriz.fotoDesdeVideo(elementos.video));
      if (i < total - 1) await pausar(window.CONFIG.PAUSA_ENTRE_FOTOGRAMAS_MS);
    }
    elementos.contador.hidden = true;
    return fotos;
  }

  // ---------------------------------------------------------------------------
  // Resultado
  // ---------------------------------------------------------------------------
  function porcentaje(valor) {
    return `${Math.round(valor * 100)} %`;
  }

  function mostrarError(texto) {
    const tarjeta = elementos.resultado;
    tarjeta.replaceChildren(
      crear("div", "etiqueta", "Error"),
      crear("div", "nombre", "No se pudo identificar"),
      crear("p", "mensaje", texto)
    );
    tarjeta.className = "resultado error";
    tarjeta.hidden = false;
  }

  function mostrarResultado(respuesta) {
    const etiquetaPuntuacion = respuesta.tipo_puntuacion === "similitud_coseno" ? "Similitud" : "Confianza";
    const tarjeta = elementos.resultado;
    tarjeta.replaceChildren();
    tarjeta.className = "resultado " + (respuesta.identificado ? "ok" : "no");

    tarjeta.append(
      crear("div", "etiqueta", respuesta.identificado ? "Persona identificada" : "Sin coincidencia"),
      crear("div", "nombre", respuesta.identificado ? respuesta.nombre : "No fue posible identificar")
    );

    if (respuesta.identificado) {
      const barra = crear("div", "barra");
      const relleno = document.createElement("span");
      relleno.style.width = porcentaje(respuesta.confianza);
      barra.append(relleno);
      tarjeta.append(barra, crear("div", "confianza", `${etiquetaPuntuacion}: ${porcentaje(respuesta.confianza)}`));
    } else if (!respuesta.rostro_detectado) {
      tarjeta.append(
        crear("p", "mensaje",
          "No se detectó un rostro claro. Deja una sola persona en el encuadre, centra tu cara y busca más luz.")
      );
    } else {
      tarjeta.append(
        crear("p", "mensaje",
          respuesta.consenso === false ? "Los fotogramas no coinciden en una misma persona. Mantén el rostro estable y vuelve a intentar." :
          respuesta.margen < respuesta.margen_minimo ? "Hay dos personas con puntuaciones parecidas. Cambia ligeramente el ángulo o la iluminación y vuelve a intentar." :
          `No se alcanzó la puntuación mínima (${etiquetaPuntuacion.toLowerCase()}: ${porcentaje(respuesta.confianza)}, mínimo ${porcentaje(respuesta.umbral)}).`)
      );
    }

    const detalle = document.createElement("details");
    detalle.append(crear("summary", "", "Detalle técnico"));
    const lista = document.createElement("ul");
    lista.append(
      crear("li", "", `Fotogramas con rostro: ${respuesta.fotogramas_con_rostro} de ${respuesta.fotogramas_analizados}`),
      crear("li", "", `Mínimo de ${etiquetaPuntuacion.toLowerCase()}: ${porcentaje(respuesta.umbral)}`)
    );
    (respuesta.candidatos || []).forEach((candidato) => {
      lista.append(crear("li", "", `${candidato.nombre}: ${porcentaje(candidato.probabilidad)}${respuesta.tipo_puntuacion === "similitud_coseno" ? " de similitud" : ""}`));
    });
    detalle.append(lista);
    tarjeta.append(detalle);

    tarjeta.hidden = false;
    tarjeta.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // ---------------------------------------------------------------------------
  // Identificación
  // ---------------------------------------------------------------------------
  function fijarOcupado(ocupado, textoBoton) {
    estado.ocupado = ocupado;
    elementos.btnIdentificar.disabled = ocupado;
    elementos.btnVoltear.disabled = ocupado;
    elementos.btnIdentificar.classList.toggle("girando", ocupado);
    elementos.btnIdentificar.textContent = textoBoton || "Identificar";
  }

  /** Obtiene fotos completas; la API comparte el preprocesamiento con entrenamiento. */
  async function identificar(obtenerFotos) {
    if (estado.ocupado) return;
    if (!estado.urlApi) {
      abrirAjustes("Primero configura la URL de la API.");
      return;
    }
    elementos.resultado.hidden = true;
    fijarOcupado(true, "Capturando");
    try {
      const fotos = await obtenerFotos();
      fijarOcupado(true, "Analizando");
      const respuesta = await Api.predecirFotos(
        estado.urlApi, fotos, window.CONFIG.TIEMPO_MAXIMO_API_MS);
      mostrarResultado(respuesta);
    } catch (error) {
      elementos.contador.hidden = true;
      mostrarError(error.message || "Ocurrió un error inesperado.");
    } finally {
      fijarOcupado(false);
    }
  }

  async function identificarDesdeArchivo(archivo) {
    await identificar(async () => [archivo]);
  }

  // ---------------------------------------------------------------------------
  // Ajustes
  // ---------------------------------------------------------------------------
  function fijarEstadoConexion(texto, clase) {
    elementos.estadoConexion.textContent = texto;
    elementos.estadoConexion.className = "estado-conexion" + (clase ? " " + clase : "");
  }

  function abrirAjustes(mensaje) {
    elementos.entradaUrl.value = estado.urlApi;
    fijarEstadoConexion(mensaje || "", mensaje ? "error" : "");
    if (typeof elementos.ajustes.showModal === "function") elementos.ajustes.showModal();
  }

  async function probarConexion() {
    const url = Api.normalizarUrl(elementos.entradaUrl.value);
    if (!url) {
      fijarEstadoConexion("Escribe la URL de la API.", "error");
      return;
    }
    elementos.btnProbar.disabled = true;
    fijarEstadoConexion("Conectando…", "");
    try {
      const datos = await Api.salud(url);
      fijarEstadoConexion(
        `Conectado · ${datos.personas_en_base_de_datos} personas en la base de datos`, "ok");
    } catch (error) {
      fijarEstadoConexion(error.message, "error");
    } finally {
      elementos.btnProbar.disabled = false;
    }
  }

  async function guardarAjustes(evento) {
    evento.preventDefault();
    const url = Api.normalizarUrl(elementos.entradaUrl.value);
    if (!url) {
      fijarEstadoConexion("Escribe la URL de la API.", "error");
      return;
    }
    elementos.btnGuardar.disabled = true;
    fijarEstadoConexion("Comprobando conexión…", "");
    try {
      await Api.salud(url);
      estado.urlApi = url;
      guardarAjuste(CLAVE_URL, estado.urlApi);
      elementos.ajustes.close();
    } catch (error) {
      fijarEstadoConexion(error.message, "error");
    } finally {
      elementos.btnGuardar.disabled = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Inicio
  // ---------------------------------------------------------------------------
  function registrarEventos() {
    elementos.btnIdentificar.addEventListener("click", () => identificar(capturarFotogramas));
    elementos.btnVoltear.addEventListener("click", async () => {
      estado.camara = estado.camara === "user" ? "environment" : "user";
      await iniciarCamara();
    });
    elementos.btnAjustes.addEventListener("click", () => abrirAjustes());
    elementos.btnProbar.addEventListener("click", probarConexion);
    elementos.formularioAjustes.addEventListener("submit", guardarAjustes);
    elementos.entradaArchivo.addEventListener("change", (evento) => {
      const archivo = evento.target.files && evento.target.files[0];
      if (archivo) identificarDesdeArchivo(archivo);
      evento.target.value = "";
    });

    // Privacidad y batería: la cámara se apaga cuando la app pasa a segundo plano.
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) detenerCamara();
      else iniciarCamara();
    });
  }

  async function iniciar() {
    elementos.ayuda.textContent = TEXTO_AYUDA;
    estado.urlApi = Api.normalizarUrl(leerAjuste(CLAVE_URL) || window.CONFIG.API_URL_POR_DEFECTO);
    registrarEventos();
    await iniciarCamara();
    if (!estado.urlApi) abrirAjustes("Configura la URL de tu API para comenzar.");
  }

  iniciar();
})();
