# ~/serv/mi_app/views.py

from django.shortcuts import render
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import os
from datetime import datetime
import logging

from .utils import process_raw_to_png, process_and_detect_image
from .forms import RawFileUploadForm # Keep if you still want a file upload form

logger = logging.getLogger(__name__)



@csrf_exempt
def upload_raw_file(request):
    error_message = None # Para pasar mensajes de error a la plantilla
    
    if request.method == 'POST':
        logger.info("Recibida solicitud POST para subir RAW desde la Pico W.")

        raw_image_data = request.body

        if not raw_image_data:
            error_message = 'No se recibieron datos de imagen RAW.'
            logger.warning(error_message)
        elif len(raw_image_data) < 4:
            error_message = 'Datos de imagen RAW incompletos (menos de 4 bytes para ancho/alto).'
            logger.error(error_message)
        else:
            try:
           
                img_width = int.from_bytes(raw_image_data[0:2], 'big')
                img_height = int.from_bytes(raw_image_data[2:4], 'big')
                pixel_data = raw_image_data[4:]



            except Exception as e:
                error_message = f"Error al interpretar los datos de ancho/alto: {e}"
                logger.error(error_message)

            if not error_message: 
                expected_pixel_data_size = img_width * img_height * 2
                if len(pixel_data) != expected_pixel_data_size:
                    error_message = (f"Los datos de la imagen no corresponden con el ancho y alto proporcionados. "
                                     f"Ancho: {img_width}, Alto: {img_height}, "
                                     f"Bytes esperados: {expected_pixel_data_size}, "
                                     f"Bytes recibidos: {len(pixel_data)}")
                    logger.warning(error_message)
                else:
                    timestamp_numeric = datetime.now().strftime("%y%m%d%H%M%S")
                    raw_filename_with_ts = f"raw_{timestamp_numeric}.raw"
                    intermediate_png_filename = f"original_{timestamp_numeric}.png"
                    detected_png_filename = f"detected_{timestamp_numeric}.png"

                    raw_file_path = os.path.join(settings.MEDIA_ROOT, raw_filename_with_ts)
                    intermediate_png_path = os.path.join(settings.MEDIA_ROOT, intermediate_png_filename)
                    detected_png_path = os.path.join(settings.MEDIA_ROOT, detected_png_filename)

                    try:
                        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

                        with open(raw_file_path, 'wb') as destination:
                            destination.write(raw_image_data)
                        logger.info(f"Archivo RAW guardado en: {raw_file_path}")

                        png_path = process_raw_to_png(raw_file_path, intermediate_png_path)

                        if png_path:
                            logger.info(f"Archivo RAW convertido a PNG: {png_path}")
                            final_detected_path = process_and_detect_image(png_path, detected_png_path)
                            
                            if final_detected_path and os.path.exists(final_detected_path):
                               
                                logger.info(f"Imagen PNG detectada guardada en: {final_detected_path}")
                            else:
                                error_message = f"Fallo en la detección de objetos para la imagen PNG: {intermediate_png_filename}"
                                logger.error(error_message)
                        else:
                            error_message = f"Fallo al procesar el archivo RAW a PNG: {raw_filename_with_ts}"
                            logger.error(error_message)
                    except Exception as e:
                        error_message = f"Ocurrió un error interno al procesar la imagen. Detalles: {e}"
                        logger.exception(error_message)
    
    detected_images_urls = []
    media_root = settings.MEDIA_ROOT
    media_url = settings.MEDIA_URL

    if os.path.exists(media_root):
        
        files = sorted([f for f in os.listdir(media_root) if f.startswith('detected_') and f.endswith('.png')],
                       key=lambda f: os.path.getmtime(os.path.join(media_root, f)), reverse=True)
        
        

        for filename in files:
            image_url = media_url + filename
            detected_images_urls.append(image_url)
    else:
        logger.warning(f"El directorio MEDIA_ROOT no existe: {media_root}")

 
    return render(request, 'mi_app/upload_form.html', {
        'imagenes': detected_images_urls, # Pasamos la lista como 'imagenes'
        'error_message': error_message,
        'MEDIA_URL': settings.MEDIA_URL # También pasamos MEDIA_URL para el template
    })


