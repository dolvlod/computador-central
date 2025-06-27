import machine
import time
from time import sleep
from machine import Pin, PWM, UART

# --- Pines motores DC ---
in1 = Pin(16, Pin.OUT)
in2 = Pin(17, Pin.OUT)
ena = PWM(Pin(18)); ena.freq(1000)

in3 = Pin(19, Pin.OUT)
in4 = Pin(20, Pin.OUT)
enb = PWM(Pin(21)); enb.freq(1000)

# --- UART ---
uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))

# --- Pines servos y electroimán ---
servo1 = PWM(Pin(2));  servo1.freq(50)
servo2 = PWM(Pin(4));  servo2.freq(50)
electroiman = Pin(5, Pin.OUT)

# --- Estado del electroimán (0=apagado, 1=encendido) ---
electroiman_state = 0
electroiman.value(electroiman_state)

# --- Mapa de velocidades según secuencia de 8 bits ---
# (b0,b1,b2,b3,b4,b5,b6,b7) -> (vel_ena, vel_enb)
speed_map = {
    (1,0,1,0,1,1,0,0): (23000, 24500),
    (0,1,0,1,1,1,0,0): (23000, 24500),
    (1,0,0,0,1,1,0,0): (25000,     0),
    (0,0,1,0,1,1,0,0): (    0, 25000),
}
DEFAULT_SPEED = (0, 0)

# --- Helpers servos ---
def pulse_us_to_duty(pulse_us):
    # Convierte un pulso en µs (1 ms a 2 ms) a valor duty_u16 (0–65535)
    return int((pulse_us * 65535) / 20000)

def set_servo(servo, pulse_us):
    servo.duty_u16(pulse_us_to_duty(pulse_us))

# --- Movimiento para key == 00000010 ---
def movimiento_key_00000010():
    set_servo(servo1, 1500); set_servo(servo2, 1620); sleep(0.6)
    set_servo(servo1, 1500); set_servo(servo2, 1500); sleep(0.2)
    set_servo(servo1,  900); set_servo(servo2, 1500); sleep(0.1)
    set_servo(servo1, 1500); set_servo(servo2, 1500); sleep(0.2)
    set_servo(servo1, 1500); set_servo(servo2, 1620); sleep(0.3)
    set_servo(servo1, 1600); set_servo(servo2, 1000); sleep(0.000001)
    set_servo(servo1, 1500); set_servo(servo2, 1620); sleep(0.03)
    

# --- Movimiento para key == 00000001 ---
def movimiento_key_00000001(n_veces=10):
    set_servo(servo1, 1550); set_servo(servo2,  600); sleep(0.5)
    for _ in range(n_veces):
        electroiman.value(1)
        set_servo(servo1, 1500); set_servo(servo2, 1250)
        sleep(0.08)


# --- Alternar estado del electroimán para key == 00000011 ---
def toggle_electroiman():
    global electroiman_state
    electroiman_state ^= 1           # cambia 0→1 o 1→0
    electroiman.value(electroiman_state)

# --- Bucle principal ---
while True:
    line = uart.readline()
    if not line:
        sleep(0.01)
        continue
    if set(line) <= {0xFF, 0x0A}:
        continue

    bits_str = line.decode('ascii', 'ignore').strip()
    bits = [int(ch) for ch in bits_str if ch in '01']
    if len(bits) < 8:
        continue

    b0,b1,b2,b3,b4,b5,b6,b7 = bits[:8]
    key = (b0,b1,b2,b3,b4,b5,b6,b7)

    # Control motores DC
    in1.value(b0); in2.value(b1)
    in3.value(b2); in4.value(b3)
    vel_ena, vel_enb = speed_map.get(key, DEFAULT_SPEED)
    ena.duty_u16(vel_ena)
    enb.duty_u16(vel_enb)

    # Secuencias especiales
    if key == (0,0,0,0,0,0,1,0):
        movimiento_key_00000010()

    if key == (0,0,0,0,0,0,0,1):
        movimiento_key_00000001(n_veces=10)

    if key == (0,0,0,0,0,0,1,1):
        toggle_electroiman()

    sleep(0.01)
