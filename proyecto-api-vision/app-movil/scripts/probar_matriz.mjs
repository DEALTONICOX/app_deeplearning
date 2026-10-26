/**
 * Pruebas de las funciones puras de www/matriz.js (sin navegador ni dispositivo).
 * Uso: npm run probar-matriz
 */
import { createRequire } from "node:module";
import assert from "node:assert/strict";

const requerir = createRequire(import.meta.url);
const Matriz = requerir("../www/matriz.js");

let pruebas = 0;
function prueba(nombre, funcion) {
  funcion();
  pruebas++;
  console.log(`  ok  ${nombre}`);
}

prueba("cuadradoCentral de una imagen vertical 720x1280", () => {
  assert.deepEqual(Matriz.cuadradoCentral(720, 1280), { sx: 0, sy: 280, lado: 720 });
});
prueba("cuadradoCentral de una imagen horizontal 1280x720", () => {
  assert.deepEqual(Matriz.cuadradoCentral(1280, 720), { sx: 280, sy: 0, lado: 720 });
});
prueba("cuadradoCentral de una imagen ya cuadrada", () => {
  assert.deepEqual(Matriz.cuadradoCentral(500, 500), { sx: 0, sy: 0, lado: 500 });
});

prueba("rgbaAMatriz ordena [fila][columna][RGB] y descarta alfa", () => {
  // Imagen 2x2: rojo, verde / azul, blanco (con alfa 255)
  const rgba = new Uint8ClampedArray([
    255, 0, 0, 255,   0, 255, 0, 255,
    0, 0, 255, 255,   255, 255, 255, 255,
  ]);
  const matriz = Matriz.rgbaAMatriz(rgba, 2, 2);
  assert.deepEqual(matriz, [
    [[255, 0, 0], [0, 255, 0]],
    [[0, 0, 255], [255, 255, 255]],
  ]);
});

prueba("rgbaAMatriz rechaza tamaños inconsistentes", () => {
  assert.throws(() => Matriz.rgbaAMatriz(new Uint8ClampedArray(10), 2, 2));
});

prueba("rgbaAMatriz de 128x128 produce forma 128x128x3 válida", () => {
  const ancho = Matriz.LADO_MATRIZ;
  const rgba = new Uint8ClampedArray(ancho * ancho * 4);
  for (let i = 0; i < rgba.length; i++) rgba[i] = i % 256;
  const matriz = Matriz.rgbaAMatriz(rgba, ancho, ancho);
  assert.equal(matriz.length, 128);
  assert.equal(matriz[0].length, 128);
  assert.equal(matriz[0][0].length, 3);
  assert.equal(Matriz.validarMatriz(matriz), true);
});

prueba("validarMatriz rechaza forma o valores incorrectos", () => {
  assert.equal(Matriz.validarMatriz([[[0, 0, 0]]]), false);
  assert.equal(Matriz.validarMatriz("texto"), false);
  const buena = Array.from({ length: 128 }, () =>
    Array.from({ length: 128 }, () => [10, 20, 30]));
  assert.equal(Matriz.validarMatriz(buena), true);
  const conDecimal = structuredClone(buena);
  conDecimal[5][5][1] = 1.5;
  assert.equal(Matriz.validarMatriz(conDecimal), false);
  const fueraDeRango = structuredClone(buena);
  fueraDeRango[0][0][0] = 300;
  assert.equal(Matriz.validarMatriz(fueraDeRango), false);
});

console.log(`\n${pruebas} pruebas aprobadas.`);
