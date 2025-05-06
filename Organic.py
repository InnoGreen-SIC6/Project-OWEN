import time
import machine
import dht
from machine import Pin, ADC, SoftI2C, PWM
import network
import urequests

FLASK_SERVER_IP = "172.16.200.92"
FLASK_URL = f"http://{FLASK_SERVER_IP}:5000/upload"

WIFI_SSID = "RUANG 125-STI"
WIFI_PASSWORD = "12345678"

#Sensor DHT22
dht_pin = Pin(15)
sensor_dht22 = dht.DHT22(dht_pin)

#I2C dan INA219
i2c_scl_pin = Pin(22, Pin.OUT, Pin.PULL_UP)
i2c_sda_pin = Pin(21, Pin.OUT, Pin.PULL_UP)
i2c = SoftI2C(scl=i2c_scl_pin, sda=i2c_sda_pin)
shunt_ohms = 0.1
ina_address = 0x40
INA219_CONFIG_REGISTER = 0x00
INA219_SHUNT_VOLTAGE_REGISTER = 0x01
INA219_BUS_VOLTAGE_REGISTER = 0x02

def ina219_write_register(address, register, data):
    try:
        i2c.writeto_mem(address, register, data)
    except Exception as e:
        print(f"Error writing to INA219 register 0x{register:02X}: {e}")

def ina219_read_register(address, register, num_bytes):
    try:
        return i2c.readfrom_mem(address, register, num_bytes)
    except Exception as e:
        print(f"Error reading from INA219 register 0x{register:02X}: {e}")
        return None

def configure_ina219(): 
    config_data = b'\x01\x9F'  
    ina219_write_register(ina_address, INA219_CONFIG_REGISTER, config_data)
    time.sleep_ms(100)  

def read_ina219_voltage():
    """Membaca tegangan bus dari INA219."""
    raw_data = ina219_read_register(ina_address, INA219_BUS_VOLTAGE_REGISTER, 2)
    if raw_data:
        value = (raw_data[0] << 8 | raw_data[1]) >> 3
        return value * 0.004  # mV
    else:
        return None

#Sensor Turbidity
turbidity_pin = ADC(Pin(36)) 
turbidity_pin.atten(ADC.ATTN_11DB)  

#Sensor pH
ph_sensor = ADC(Pin(32))
ph_sensor.atten(ADC.ATTN_11DB)

#Servo
servo_pin = Pin(13, Pin.OUT)
servo_pwm = PWM(servo_pin, freq=50)

def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Connecting to WiFi...')
        wlan.connect(ssid, password)
        max_wait = 10  
        while not wlan.isconnected() and max_wait > 0:
            time.sleep(1)
            max_wait -= 1
        if wlan.isconnected():
            print('WiFi connected')
            print('IP address:', wlan.ifconfig()[0])
            return True
        else:
            print('WiFi connection failed')
            return False
    else:
        print('Already connected to WiFi')
        print('IP address:', wlan.ifconfig()[0])
        return True

def read_dht22():
    try:
        sensor_dht22.measure()
        temperature = sensor_dht22.temperature()
        humidity = sensor_dht22.humidity()
        return temperature, humidity
    except Exception as e:
        print(f"Error reading DHT22: {e}")
        return None, None

def read_turbidity():
    try:
        raw_value = turbidity_pin.read()
        turbidity_percentage = 100 - (raw_value / 4095) * 100
        return turbidity_percentage
    except Exception as e:
        print(f"Error reading turbidity: {e}")
        return None

def read_ph():
    try:
        raw_value = ph_sensor.read()
        ph_value = raw_value / 4095 * 7.5
        return ph_value
    except Exception as e:
        print(f"Error reading pH: {e}")
        return None

def control_servo(turbidity_percentage):
    try:
        target_angle = 90 if turbidity_percentage > 15 else 0
        duty = angle_to_duty_cycle(target_angle)
        servo_pwm.duty(duty)
    except Exception as e:
        print(f"Error controlling servo: {e}")

def angle_to_duty_cycle(angle):
    min_us = 500
    max_us = 2500
    pulse_width_us = (angle / 180) * (max_us - min_us) + min_us
    duty_cycle = int(1023 * (pulse_width_us / 20000))
    return duty_cycle

def send_data_to_flask(url, data):
    try:
        response = urequests.post(url, json=data)
        if response.status_code == 200:
            print("Data sent successfully")
            return True
        else:
            print(f"Failed to send data. Status code: {response.status_code}, Response: {response.text}")
            return False
        response.close()
    except Exception as e:
        print(f"Error sending data to Flask: {e}")
        return False

def main():
    if not connect_wifi(WIFI_SSID, WIFI_PASSWORD):
        print("Failed to connect to WiFi.  Stopping.")
        return 

    configure_ina219() 
    while True:
        temp, hum = read_dht22()
        voltage = read_ina219_voltage()
        turbidity = read_turbidity()
        ph = read_ph()

        if temp is not None and hum is not None and voltage is not None and turbidity is not None and ph is not None:
            control_servo(turbidity)  

            payload = {
                "suhu": 34.7,
                "kelembaban": 64.59,
                "tegangan": voltage,
                "turbidity": turbidity,
                "ph": ph 
            }
            if send_data_to_flask(FLASK_URL, payload):
                print("Data dikirim ke Flask")
            else:
                print("Gagal mengirim data ke Flask")
        else:
            print("Gagal membaca data s  bensor. Mengirim nilai None.")
            payload = {
                "suhu": None, 
                "kelembaban": None,
                "tegangan": None,
                "turbidity": None,   
                "ph": None
            }
            send_data_to_flask(FLASK_URL, payload)

        time.sleep(5)

if __name__ == "__main__":
    main()