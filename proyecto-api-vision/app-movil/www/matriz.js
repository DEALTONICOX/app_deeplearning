/**
 * matriz.js — Conversión de una imagen a la matriz 128 x 128 x 3 que espera la API.
 *
 * Las funciones puras (cuadradoCentral, rgbaAMatriz, validarMatriz) funcionan en el
 * navegador y en Node, por lo que se pueden probar sin dispositivo
 * (`npm run probar-matriz`). Las funciones que usan <canvas> solo corren en el
 * navegador / WebView.
 *
 * Flujo:
 *   fotograma de la cámara -> recorte cuadrado central (lo que muestra el visor)
 *   -> reducción a 128 x 128 -> píxeles RGBA -> matriz [128][128][3] con valores 0-255
 */
(function (raiz, fabrica) {
  if (typeof module === "object" && module.exports) {
    module.exports = fabrica();
  } else {
    raiz.Matriz = fabrica();
  }
})(typeof self !== "undefined" ? self : this, function () {
  const LADO_MATRIZ = 128; // alto y ancho exigidos por la API
  const CANALES = 3; // R, G, B

  /** Cuadrado centrado del mayor tamaño posible dentro de una imagen ancho x alto. */
  function cuadradoCentral(ancho, alto) {
    const lado = Math.min(ancho, alto);
    return {
      sx: Math.floor((ancho - lado) / 2),
      sy: Math.floor((alto - lado) / 2),
      lado: lado,
    };
  }

  /**
   * Convierte un arreglo RGBA plano (formato de ImageData.data) de una imagen
   * cuadrada en la matriz [alto][ancho][3]. Descarta el canal alfa.
   */
  function rgbaAMatriz(rgba, ancho, alto) {
    if (rgba.length !== ancho * alto * 4) {
      throw new Error("El tamaño del arreglo RGBA no coincide con ancho x alto x 4.");
    }
    const matriz = new Array(alto);
    for (let fila = 0; fila < alto; fila++) {
      const filaPixeles = new Array(ancho);
      for (let columna = 0; columna < ancho; columna++) {
        const posicion = (fila * ancho + columna) * 4;
        filaPixeles[columna] = [rgba[posicion], rgba[posicion + 1], rgba[posicion + 2]];
      }
      matriz[fila] = filaPixeles;
    }
    return matriz;
  }

  /** Comprueba que la matriz tenga forma 128 x 128 x 3 con valores enteros 0-255. */
  function validarMatriz(matriz) {
    if (!Array.isArray(matriz) || matriz.length !== LADO_MATRIZ) return false;
    for (const fila of matriz) {
      if (!Array.isArray(fila) || fila.length !== LADO_MATRIZ) return false;
      for (const pixel of fila) {
        if (!Array.isArray(pixel) || pixel.length !== CANALES) return false;
        for (const valor of pixel) {
          if (!Number.isInteger(valor) || valor < 0 || valor > 255) return false;
        }
      }
    }
    return true;
  }

  // -------------------------------------------------------------------------
  // Funciones que requieren <canvas> (solo navegador / WebView)
  // -------------------------------------------------------------------------

  function crearCanvas(lado) {
    const lienzo = document.createElement("canvas");
    lienzo.width = lado;
    lienzo.height = lado;
    return lienzo;
  }

  /**
   * Recorta el cuadrado central de `fuente` (video o imagen) y lo reduce a
   * 128 x 128. La reducción se hace en pasos de mitad para evitar el efecto de
   * dentado (aliasing) que produce reducir 720 px a 128 px de una sola vez.
   */
  function cuadradoA128(fuente, anchoFuente, altoFuente) {
    const { sx, sy, lado } = cuadradoCentral(anchoFuente, altoFuente);

    let actual = crearCanvas(lado);
    let contexto = actual.getContext("2d");
    contexto.drawImage(fuente, sx, sy, lado, lado, 0, 0, lado, lado);

    while (actual.width / 2 >= LADO_MATRIZ) {
      const siguiente = crearCanvas(Math.floor(actual.width / 2));
      contexto = siguiente.getContext("2d");
      contexto.imageSmoothingEnabled = true;
      contexto.imageSmoothingQuality = "high";
      contexto.drawImage(actual, 0, 0, siguiente.width, siguiente.height);
      actual = siguiente;
    }

    const final = crearCanvas(LADO_MATRIZ);
    contexto = final.getContext("2d", { willReadFrequently: true });
    contexto.imageSmoothingEnabled = true;
    contexto.imageSmoothingQuality = "high";
    contexto.drawImage(actual, 0, 0, LADO_MATRIZ, LADO_MATRIZ);
    return contexto.getImageData(0, 0, LADO_MATRIZ, LADO_MATRIZ);
  }

  /** Captura el fotograma actual de un <video> y lo devuelve como matriz 128x128x3. */
  function matrizDesdeVideo(video) {
    const datos = cuadradoA128(video, video.videoWidth, video.videoHeight);
    return rgbaAMatriz(datos.data, LADO_MATRIZ, LADO_MATRIZ);
  }

  /** Convierte una imagen ya cargada (<img> o ImageBitmap) en matriz 128x128x3. */
  function matrizDesdeImagen(imagen) {
    const ancho = imagen.naturalWidth || imagen.width;
    const alto = imagen.naturalHeight || imagen.height;
    const datos = cuadradoA128(imagen, ancho, alto);
    return rgbaAMatriz(datos.data, LADO_MATRIZ, LADO_MATRIZ);
  }

  /** Mantiene el fotograma completo; el servidor aplica el recorte de entrenamiento. */
  function fotoDesdeVideo(video) {
    const escala = Math.min(1, 800 / Math.max(video.videoWidth, video.videoHeight));
    const lienzo = document.createElement("canvas");
    lienzo.width = Math.max(1, Math.round(video.videoWidth * escala));
    lienzo.height = Math.max(1, Math.round(video.videoHeight * escala));
    lienzo.getContext("2d").drawImage(video, 0, 0, lienzo.width, lienzo.height);
    return new Promise((resolve, reject) => {
      lienzo.toBlob((blob) => blob ? resolve(blob) : reject(new Error("No se pudo capturar la foto.")),
        "image/jpeg", 0.92);
    });
  }

  return {
    LADO_MATRIZ: LADO_MATRIZ,
    CANALES: CANALES,
    cuadradoCentral: cuadradoCentral,
    rgbaAMatriz: rgbaAMatriz,
    validarMatriz: validarMatriz,
    matrizDesdeVideo: matrizDesdeVideo,
    matrizDesdeImagen: matrizDesdeImagen,
    fotoDesdeVideo: fotoDesdeVideo,
  };
});
