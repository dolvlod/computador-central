# ~/serv/mi_app/utils.py

import os
from PIL import Image, ImageDraw, ImageFont
import logging
from ultralytics import YOLO
import numpy as np
from ultralytics.utils.ops import scale_boxes
import torch
import torch.nn as nn
from ultralytics.nn.tasks import DetectionModel
from ultralytics.nn.modules.conv import Conv
from ultralytics.nn.modules.block import C2f
from ultralytics.nn.modules.block import Bottleneck
from ultralytics.nn.modules.block import SPPF
from ultralytics.nn.modules.conv import Concat
from ultralytics.nn.modules.head import Detect
from ultralytics.nn.modules.block import DFL 

logger = logging.getLogger(__name__)


MODEL_PATH = '/home/dolv07/PycharmProjects/RGBIMG/YOLODOLV/runs5/leds_detectiondolv3_v2/weights/best.pt'
MODEL = None

if 'MODEL' not in globals():
    logger.error("CRITICAL ERROR: 'MODEL' variable was NOT defined at module load time in utils.py!")
else:
    logger.info(f"DEBUG: 'MODEL' variable is defined at module load time. Current value: {MODEL}")


LINE_THICKNESS = 1
CLASS_COLORS = {
    0: "red",
    1: "green",
    2: "blue",
    3: "yellow"
}

CONF_THRESHOLD = 0.05
IOU_THRESHOLD = 0.9
IMG_SIZE = 160


ORIG_IMG_WIDTH = 160
ORIG_IMG_HEIGHT = 120


try:
    font_path_arial = "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"
    font_path_dejavu = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    if os.path.exists(font_path_arial):
        FONT = ImageFont.truetype(font_path_arial, 10)
        FONT_NUMBER = ImageFont.truetype(font_path_arial, 12)
    elif os.path.exists(font_path_dejavu):
        FONT = ImageFont.truetype(font_path_dejavu, 10)
        FONT_NUMBER = ImageFont.truetype(font_path_dejavu, 12)
    else:
        FONT = ImageFont.load_default()
        FONT_NUMBER = ImageFont.load_default()
        logger.warning("ADVERTENCIA: No se encontraron fuentes específicas. Usando fuente por defecto.")
except IOError:
    FONT = ImageFont.load_default()
    FONT_NUMBER = ImageFont.load_default()
    logger.warning("ADVERTENCIA: Fallo al cargar fuentes, usando fuente por defecto.")


def get_distance_class(y_center_pixel_orig, image_height_pixel_orig):
    if y_center_pixel_orig >= 83:
        return "d1"
    elif 45 <= y_center_pixel_orig < 83:
        return "d2"
    elif y_center_pixel_orig < 45:
        return "d3"
    else:
        return "unknown_distance"



def process_raw_to_png(raw_file_path, output_png_path):
    try:
        with open(raw_file_path, 'rb') as f:
            width_bytes = f.read(2)
            if not width_bytes or len(width_bytes) < 2:
                logger.error(f"Error al leer ancho en {raw_file_path}: datos insuficientes.")
                return None
            width = int.from_bytes(width_bytes, 'big')

            height_bytes = f.read(2)
            if not height_bytes or len(height_bytes) < 2:
                logger.error(f"Error al leer alto en {raw_file_path}: datos insuficientes.")
                return None
            height = int.from_bytes(height_bytes, 'big')

            raw_pixel_data = f.read()

        expected_pixel_data_size = width * height * 2
        if len(raw_pixel_data) != expected_pixel_data_size:
            logger.error(
                f"El tamaño del archivo RAW ({len(raw_pixel_data) + 4} bytes) de '{os.path.basename(raw_file_path)}' no coincide con el tamaño esperado ({expected_pixel_data_size + 4} bytes) para {width}x{height}.")
            return None

        rgb_data = bytearray(width * height * 3)
        for i in range(0, len(raw_pixel_data), 2):
            pixel_565 = (raw_pixel_data[i] << 8) | raw_pixel_data[i + 1]
            r = (pixel_565 >> 11) & 0x1F
            g = (pixel_565 >> 5) & 0x3F
            b = pixel_565 & 0x1F
            r = (r * 255) // 31
            g = (g * 255) // 63
            b = (b * 255) // 31
            idx_rgb = (i // 2) * 3
            rgb_data[idx_rgb] = r
            rgb_data[idx_rgb + 1] = g
            rgb_data[idx_rgb + 2] = b

        img = Image.frombytes('RGB', (width, height), bytes(rgb_data))
        img.save(output_png_path)
        logger.info(f"Imagen PNG guardada en: {output_png_path}")
        return output_png_path

    except FileNotFoundError:
        logger.error(f"Archivo RAW no encontrado: {raw_file_path}")
        return None
    except Exception as e:
        logger.exception(f"Error inesperado al procesar RAW a PNG para '{raw_file_path}': {e}")
        return None



CONF_RED = 0.0
CONF_GREEN = 0.0
CONF_BLUE = 0.0
CONF_YELLOW = 0.0

def process_and_detect_image(input_png_path, output_detected_png_path):
    import os
    import csv
    from PIL import Image, ImageDraw
    global MODEL, CONF_RED, CONF_GREEN, CONF_BLUE, CONF_YELLOW
    logger.info(f"DEBUG: Inside process_and_detect_image. MODEL is currently {MODEL}.")

    if MODEL is None:
        try:
            from ultralytics.nn.tasks import DetectionModel
            from ultralytics.nn.modules.conv import Conv
            import torch.nn as nn
            from ultralytics.nn.modules.block import C2f, Bottleneck, SPPF
            torch.serialization.add_safe_globals([
                DetectionModel, nn.Sequential, Conv, nn.Conv2d,
                nn.BatchNorm2d, nn.SiLU, C2f, nn.ModuleList,
                Bottleneck, SPPF, nn.MaxPool2d, nn.Upsample,
                Concat, Detect, DFL
            ])
            MODEL = YOLO(MODEL_PATH)
            logger.info(f"Modelo YOLO cargado desde: {MODEL_PATH}")
        except Exception as e:
            logger.error(f"Error al cargar YOLO: {e}")
            return None

    try:
        logger.info(f"Realizando inferencia en {input_png_path}")
        results = MODEL.predict(
            source=input_png_path,
            save=False,
            save_conf=True,
            save_txt=False,
            conf=CONF_THRESHOLD,
            iou=IOU_THRESHOLD,
            imgsz=IMG_SIZE
        )

        detections_dir = '/home/dolv07/PycharmProjects/RGBIMG/deteccionesfinal'
        os.makedirs(detections_dir, exist_ok=True)
        csv_path = os.path.join(
            detections_dir,
            f"{os.path.splitext(os.path.basename(input_png_path))[0]}.csv"
        )

        for r in results:
            img = Image.open(input_png_path).convert("RGB")
            draw = ImageDraw.Draw(img)

          
            detections = []  # cada item: {'box':(x1,y1,x2,y2), 'cls_id': int, 'conf': float}
            if hasattr(r, 'boxes') and len(r.boxes) > 0:
                boxes = scale_boxes((IMG_SIZE, IMG_SIZE), r.boxes.xyxy.clone(), r.orig_shape)
                for i, box_np in enumerate(boxes.cpu().numpy()):
                    cls_id = int(r.boxes.cls[i].item())
                    conf = float(r.boxes.conf[i].item())
                    x1, y1, x2, y2 = map(int, box_np.tolist())
                    # Ajuste vertical
                    y1 += 20; y2 += 20
                    # Clamp
                    x1 = max(0, x1); y1 = max(0, y1)
                    x2 = min(img.width-1, x2); y2 = min(img.height-1, y2)
                    detections.append({'box': (x1, y1, x2, y2), 'cls_id': cls_id, 'conf': conf})

          
            half_height = img.height / 2
            detections = [d for d in detections if ((d['box'][1] + d['box'][3]) / 2) > half_height]

         
            detections.sort(key=lambda d: d['conf'], reverse=True)
            csv_rows = []

            for idx, det in enumerate(detections, start=1):
                x1, y1, x2, y2 = det['box']
                cls_id = det['cls_id']
                conf = det['conf']
                color = CLASS_COLORS.get(cls_id, 'white')
               
                if color == 'red': CONF_RED = max(CONF_RED, conf)
                elif color == 'green': CONF_GREEN = max(CONF_GREEN, conf)
                elif color == 'blue': CONF_BLUE = max(CONF_BLUE, conf)
                elif color == 'yellow': CONF_YELLOW = max(CONF_YELLOW, conf)

                
                draw.rectangle([x1, y1, x2, y2], outline=color, width=LINE_THICKNESS)
                num = str(idx)
               
                try:
                    bbox = draw.textbbox((0,0), num, font=FONT_NUMBER)
                    w = bbox[2] - bbox[0]; h = bbox[3] - bbox[1]
                except AttributeError:
                    w, h = FONT_NUMBER.getmask(num).size
                cx = x1 + (x2 - x1)//2 - w//2
                draw.text((cx, y1 - h - 2), num, fill=color, font=FONT_NUMBER)
                draw.text((cx, y2 + 2), num, fill=color, font=FONT_NUMBER)

                csv_rows.append([idx, color, conf])

          
            img.save(output_detected_png_path)
            logger.info(f"Imagen guardada en {output_detected_png_path}")

            
            if csv_rows:
                with open(csv_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['rank', 'color', 'confidence'])
                    writer.writerows(csv_rows)
                logger.info(f"CSV guardado en {csv_path}")
            else:
                logger.info("No hay detecciones en mitad inferior; no se generó CSV.")

        return output_detected_png_path

    except Exception as e:
        logger.exception(f"Error procesando {input_png_path}: {e}")
        return None
