import machine
import time
import rp2
import network
import sdcard
import socket
import struct
import gc
import uos
import sys
import urequests as requests
from machine import Pin, UART
from machine import Pin, I2C, SPI, PWM
from ov7670_wrapper import *


# ---------- MÓDULO PIO PARA LECTURA IR ----------
@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def ir_reader():
    label('inicio')
    mov(x, invert(null))
    jmp(pin, 'uno')
    label('cero')
    set(pins, 0)
    jmp(x_dec, 'cero_bis')
    jmp('fin')
    label('cero_bis')
    jmp(pin, 'fin')
    jmp('cero')
    label('uno')
    set(pins, 1)
    jmp(x_dec, 'uno_bis')
    jmp('fin')
    label('uno_bis')
    nop()
    jmp(pin, 'uno')
    label('fin')
    mov(isr, x)
    push(noblock)
    jmp('inicio')

led = Pin(10, Pin.OUT)
# --- PARÁMETROS DE PINES (CÁMARA OV7670) ---
mclk_pin_no     = 22
pclk_pin_no     = 21
data_pin_base   = 2  # D0-D7: GP2 a GP9
vsync_pin_no    = 17
href_pin_no     = 26
reset_pin_no    = 14
shutdown_pin_no = 15
sda_pin_no      = 12
scl_pin_no      = 13

# ---------- CONFIGURAR PIO IR EN GP20 ----------
sm = rp2.StateMachine(
    1,
    ir_reader,
    freq=38_000 * 100,
    set_base=Pin(0),               # para timing interno
    jmp_pin=Pin(20, Pin.IN, Pin.PULL_UP)
)
sm.active(1)

# ---------- CONFIGURAR UART0 (TX=GP0, RX=GP1) ----------
uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))

# ---------- PAQUETE ASCII POR UART ----------
def enviar_bits_ascii(b0, b1, b2, b3, b4, b5,b6,b7):
    """
    Construye una cadena "b0b1b2b3b4b5\n" y la envía por UART
    """
    bit_str = f"{b0}{b1}{b2}{b3}{b4}{b5}{b6}{b7}\n"
    uart.write(bit_str)
    #print("UART TX ASCII:", repr(bit_str))

# ---------- FUNCIONES DE MOVIMIENTO QUE HACEN send() ----------
def move_forward():
    enviar_bits_ascii(1, 0, 1, 0, 1, 1,0,0)

def move_reverse():
    enviar_bits_ascii(0, 1, 0, 1, 1, 1,0,0)

def stop_motors():
    enviar_bits_ascii(0, 0, 0, 0, 0, 0, 0,0)

def turn_right():
    enviar_bits_ascii(1, 0, 0, 0, 1, 1 ,0,0)

def turn_left():
    enviar_bits_ascii(0, 0, 1, 0, 1, 1,0,0)

def pivot_right():
    enviar_bits_ascii(0, 1, 1, 0, 1, 1,0,0)

def pivot_left():
    enviar_bits_ascii(1, 0, 0, 1, 1, 1,0,0)
def up_mov():
    enviar_bits_ascii(0, 0, 0, 0, 0, 0,1,0)
def down_mov():
    enviar_bits_ascii(0, 0, 0, 0, 0, 0,0,1)
def electroiman():
    enviar_bits_ascii(0, 0, 0, 0, 0, 0,1,1) 
def setup_camera():
    """Configura la cámara OV7670 y retorna el objeto"""
    #print("Configurando MCLK para OV7670...")
    pwm = PWM(Pin(mclk_pin_no))
    pwm.freq(30_000_000)
    pwm.duty_u16(32768)

    #print("Inicializando I2C y OV7670...")
    i2c = I2C(0, freq=400_000, scl=Pin(scl_pin_no), sda=Pin(sda_pin_no))

    try:
        ov7670 = OV7670Wrapper(
            i2c_bus=i2c,
            mclk_pin_no=mclk_pin_no,
            pclk_pin_no=pclk_pin_no,
            data_pin_base=data_pin_base,
            vsync_pin_no=vsync_pin_no,
            href_pin_no=href_pin_no,
            reset_pin_no=reset_pin_no,
            shutdown_pin_no=shutdown_pin_no,
        )
        ov7670.wrapper_configure_rgb()
        ov7670.wrapper_configure_base()
        width, height = ov7670.wrapper_configure_size(OV7670_WRAPPER_SIZE_DIV4)
        ov7670.wrapper_configure_test_pattern(OV7670_WRAPPER_TEST_PATTERN_NONE)
        #print(f"✅ Cámara inicializada. Resolución: {width}x{height}")
        return ov7670, width, height
    except Exception as e:
        
        #print(f"❌ Error al inicializar cámara: {e}")
        #sys.exit(1)
        return None
def setup_sd_card():
    """Configura y monta la tarjeta SD"""
    #print("Inicializando MicroSD...")
    try:
        spi = SPI(0,
                  baudrate=30_000_000,
                  polarity=0,
                  phase=0,
                  sck=Pin(18),
                  mosi=Pin(19),
                  miso=Pin(16))
        cs = Pin(27, Pin.OUT)
        sd = sdcard.SDCard(spi, cs)
        uos.mount(uos.VfsFat(sd), "/sd")
        #print("✅ MicroSD montada en /sd")
        return True
    except Exception as e:
        #print(f"❌ Error SD: {e}")
        return False
def send_image_to_django(frame_buf, img_width, img_height):
    """Envía imagen al servidor Django"""
    UPLOAD_URL = f"{DJANGO_SERVER_URL}{UPLOAD_ENDPOINT}"
    full_data = img_width.to_bytes(2, 'big') + \
                img_height.to_bytes(2, 'big') + \
                frame_buf

    try:
        response = requests.post(UPLOAD_URL, data=full_data, timeout=TIMEOUT_SECONDS)
        if response.status_code in (200, 201):
            #print("✅ Imagen enviada")
            response.close()
            return True
        #print(f"❌ Error HTTP: {response.status_code}")
        response.close()
    except Exception as e:
        pass
        #print(f"❌ Error envío: {e}")
    return False
    
# ---------- LECTURA IR & MAPEO A MOVIMIENTOS ----------
datos = []
MAX_MUESTRAS = 102

SSID = 'dolvrock3'
PASSWORD = '12345678'
DJANGO_SERVER_URL = "http://10.0.0.1:8000"
UPLOAD_ENDPOINT = ""
HOST = '10.0.0.1'  # IP del servidor Django
TIMEOUT_SECONDS = 30
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5
MAX_RETRIES = 25
RETRY_DELAY = 1

result = setup_camera()
camera_ok = result is not None
if camera_ok:
    ov7670, width, height = result
    frame_buf = bytearray(width * height * 2)
else:
    pass#print("⚠️ Error: cámara no inicializada, captura desactivada")
while True:
    # Acumula datos IR en la FIFO
    if sm.rx_fifo():
        dat = sm.get()
        datos.append((2**32) - dat)

    # Una vez recogidas, decodifica y despacha un comando
    if len(datos) >= MAX_MUESTRAS:
        muestras = datos[4::2][:40]
        bin_str = ''.join('1' if v >= 1000 else '0' for v in muestras)
        hex_str = hex(int(bin_str, 2))[2:].upper()
        #print("IR code:", hex_str)

        # Mapeo estándar NEC → movimiento
        if hex_str in ("F0B2A00801", "E165401002", "C2CA802004"):
            move_forward()
        elif hex_str in ("F0B2A00823", "E165401046", "C2CA80208C"):
            stop_motors()
        elif hex_str in ("F0B2A00803", "E165401006", "C2CA80200C"):
            move_reverse()
        elif hex_str in ("F0B2A00811", "E165401022", "C2CA802044"):
            turn_right()
        elif hex_str in ("F0B2A00813", "E165401026", "C2CA80204C"):
            turn_left()
        elif hex_str in ("F0B2A00829", "E165401052", "C2CA8020A4"):
            stop_motors()
            time.sleep(1)
            up_mov()    
        elif hex_str in ("F0B2A00812", "E165401025", "C2CA80204A"):
            electroiman()
              
                
        elif hex_str in ("F0B2A0082A", "E165401054", "C2CA8020A8"):
            stop_motors()
            time.sleep(1)
            down_mov()    
        elif hex_str in ("F0B2A00820", "E165401041", "C2CA802082"):
            
            turn_right()
            time.sleep(0.2)
            stop_motors()
            time.sleep(0.5)
                
                
        elif hex_str in ("F0B2A00830", "E165401061", "C2CA8020C2"):
             wlan = network.WLAN(network.STA_IF)
             wlan.active(True)
             
             if not wlan.isconnected():
                 #print(f"Conectando a '{SSID}'...")
                 wlan.connect(SSID, PASSWORD)
                 
                 for retry in range(MAX_RETRIES):
                     if wlan.isconnected():
                         break
                     #print(f"  Intento {retry+1}/{MAX_RETRIES}...")
                     time.sleep(RETRY_DELAY)
             
             if not wlan.isconnected():
                 #print("❌ No se pudo conectar al Wi-Fi")
                 #sys.exit(1)
                 led.on()
             ip, subnet, gateway, dns = wlan.ifconfig()
             led.on()
             time.sleep(0.25)
             led.off()
             time.sleep(0.25)
             led.on()
             time.sleep(0.25)
             led.off()
             #print("✅ Conectado:")
             #print(f"   IP      : {ip}")
             #print(f"   Gateway : {gateway}")
             
        elif hex_str in ("F0B2A00821", "C2CA802084", "E165401042"):
            #result = setup_camera()
            if camera_ok:
               
                ov7670, width, height = result
                frame_buf = bytearray(width * height * 2)
                gc.collect()
                
                sd_available = setup_sd_card()
                
                # 4. Captura y envío de imágenes
                #print("\nIniciando captura de imágenes...")
                for i in range(1, 2):
                    #print(f"\n--- Captura #{i} ---")
                    gc.collect()
                    
                    # Capturar imagen
                    ov7670.capture(frame_buf)
                    led.on()
                    
                    #print(f"✅ Imagen capturada ({len(frame_buf)} bytes)")
                    
                    # Guardar en SD (opcional)
                    if sd_available:
                        try:
                            path = f"/sd/img_{i}.raw"
                            with open(path, "wb") as f:
                                f.write(width.to_bytes(2, "big"))
                                f.write(height.to_bytes(2, "big"))
                                f.write(frame_buf)
                            #print(f"💾 Guardada en SD: {path}")
                        except Exception as e:
                            #print(f"❌ Error SD: {e}")
                            pass   
                    
                    # Enviar a Django
                    if send_image_to_django(frame_buf, width, height):
                        pass  # print(f"📤 Enviada a Django")
                    else:
                        pass  # print(f"❌ Fallo envío Django")
                    
                    time.sleep(0.5)
                    led.off()# Pausa entre capturas

 
        elif hex_str == "F0B2A00831":
            pivot_left()
        else:
            stop_motors()

        datos.clear()
        time.sleep(0.1)
