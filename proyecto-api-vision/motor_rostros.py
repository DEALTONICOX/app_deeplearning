"""YuNet + alineación de cinco puntos + SFace; galería local con rechazo calibrado."""
from pathlib import Path
from threading import RLock

import cv2
import numpy as np
from PIL import ImageOps

MODELOS = Path(__file__).resolve().parent / 'modelos_rostro'


def normalizar(vector):
    return vector / max(float(np.linalg.norm(vector)), 1e-8)


def variantes(cara):
    """Variantes suaves del rostro alineado; cada variante conserva su original."""
    yield cara
    for gamma in (0.70, 1.35):
        tabla = ((np.arange(256) / 255.0) ** gamma * 255).astype('uint8')
        yield cv2.LUT(cara, tabla)
    yield cv2.convertScaleAbs(cara, alpha=0.85, beta=15)
    yield cv2.GaussianBlur(cara, (3, 3), 0.65)
    _, jpeg = cv2.imencode('.jpg', cara, [cv2.IMWRITE_JPEG_QUALITY, 55])
    yield cv2.imdecode(jpeg, cv2.IMREAD_COLOR)
    for angulo in (-7, 7):
        giro = cv2.getRotationMatrix2D((56, 56), angulo, 1.0)
        yield cv2.warpAffine(cara, giro, (112, 112), borderMode=cv2.BORDER_REFLECT_101)


def puntuar(consulta, vectores, etiquetas, grupos, clases):
    """Cada original aporta una vez, aunque tenga muchas variantes aumentadas."""
    similitudes = vectores @ consulta
    resultado = np.full(clases, -1.0, dtype=np.float32)
    for clase in range(clases):
        originales = np.unique(grupos[etiquetas == clase])
        mejores = [float(similitudes[(etiquetas == clase) & (grupos == g)].max()) for g in originales]
        if mejores:
            mejores = sorted(mejores, reverse=True)
            resultado[clase] = 0.6 * mejores[0] + 0.4 * np.mean(mejores[:3])
    return resultado


class ExtractorRostros:
    def __init__(self):
        self.detector = cv2.FaceDetectorYN.create(str(MODELOS / 'face_detection_yunet_2023mar.onnx'),
            '', (320, 320), 0.85, 0.3, 5000)
        self.reconocedor = cv2.FaceRecognizerSF.create(str(MODELOS / 'face_recognition_sface_2021dec.onnx'), '')
        self.lock = RLock()

    def alinear(self, imagen):
        rgb = np.asarray(ImageOps.exif_transpose(imagen).convert('RGB'))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        escala = min(1.0, 800 / max(bgr.shape[:2]))
        if escala < 1:
            bgr = cv2.resize(bgr, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
        with self.lock:
            self.detector.setInputSize((bgr.shape[1], bgr.shape[0]))
            _, caras = self.detector.detect(bgr)
            if caras is None:
                return None, 'sin_rostro'
            orden = np.argsort(caras[:, 2] * caras[:, 3])[::-1]
            principal = caras[orden[0]]
            if len(orden) > 1 and caras[orden[1], 2] * caras[orden[1], 3] > principal[2] * principal[3] * 0.4:
                return None, 'varios_rostros'
            if min(principal[2:4]) < 35:
                return None, 'rostro_pequeno'
            return self.reconocedor.alignCrop(bgr, principal), 'ok'

    def descriptor(self, cara):
        with self.lock:
            uno = self.reconocedor.feature(cara).ravel().copy()
            espejo = self.reconocedor.feature(cv2.flip(cara, 1)).ravel().copy()
        return normalizar(normalizar(uno) + normalizar(espejo)).astype('float32')

    def extraer(self, imagen):
        cara, motivo = self.alinear(imagen)
        return (self.descriptor(cara) if cara is not None else None), motivo


class MotorRostros(ExtractorRostros):
    def __init__(self, directorio, configuracion):
        super().__init__()
        with np.load(Path(directorio) / 'galeria.npz', allow_pickle=False) as datos:
            self.vectores = datos['vectores'].copy()
            self.etiquetas = datos['etiquetas'].copy()
            self.grupos = datos['grupos'].copy()
        self.clases = configuracion['numero_clases']
        if self.vectores.ndim != 2 or self.vectores.shape[1] != 128 or set(self.etiquetas) != set(range(self.clases)):
            raise ValueError('Galería de rostros incompatible con su configuración.')

    def puntuar(self, vector):
        return puntuar(vector, self.vectores, self.etiquetas, self.grupos, self.clases)
