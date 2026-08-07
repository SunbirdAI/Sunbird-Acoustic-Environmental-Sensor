#!/usr/bin/env python3
import time
import json
import subprocess
import re
import requests
import bme680
import serial
import logging
from adafruit_pm25.uart import PM25_UART

# — Configure logging —  
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Server configuration
URL = "https://noise-sensors-dashboard.herokuapp.com/device_metrics/environmental-parameters/"
HEADERS = {"Content-Type": "application/json"}

# BME680 setup
try:
    sensor = bme680.BME680(bme680.I2C_ADDR_PRIMARY)
    logger.info("BME680 on PRIMARY address")
except (RuntimeError, IOError):
    sensor = bme680.BME680(bme680.I2C_ADDR_SECONDARY)
    logger.info("BME680 on SECONDARY address")

sensor.set_humidity_oversample(bme680.OS_2X)
sensor.set_pressure_oversample(bme680.OS_4X)
sensor.set_temperature_oversample(bme680.OS_8X)
sensor.set_filter(bme680.FILTER_SIZE_3)

# PM2.5 sensor setup
uart = serial.Serial("/dev/ttyUSB0", baudrate=9600, timeout=0.25)
pm25 = PM25_UART(uart, reset_pin=None)

logger.info("Initialized sensors. Entering polling loop…")

while True:
    try:
        # — Read BME680 —
        temperature = pressure = humidity = None
        if sensor.get_sensor_data():
            temperature = sensor.data.temperature
            pressure    = sensor.data.pressure
            humidity    = sensor.data.humidity
            logger.debug(f"BME680 → T={temperature:.2f}°C, P={pressure:.2f}hPa, H={humidity:.2f}%")
        else:
            logger.warning("BME680 .get_sensor_data() returned False")

        # small delay so I²C settles
        time.sleep(1)

        # — Read PM2.5 —
        pm25_env = None
        try:
            aqdata   = pm25.read()
            pm25_env = aqdata["pm25 env"]
            logger.debug(f"PM2.5 → {pm25_env} µg/m³")
        except Exception:
            logger.exception("Failed to read PM2.5 sensor")

        # — Read system stats —
        ram_value = system_temp = None
        try:
            #out = subprocess.check_output("awk '/Mem:/ {print $7}'", shell=True)
            #ram_value = int(out.decode().strip())
            ram_value = int(subprocess.check_output(['free', '-m']).decode().split()[7])
            logger.debug(f"Free RAM → {ram_value} kB")
        except Exception:
            logger.exception("Failed to read RAM value")

        try:
            res = subprocess.check_output(['vcgencmd', 'measure_temp'])
            system_temp = float(re.search(r"temp=([\d\.]+)", res.decode()).group(1))
            logger.debug(f"CPU temp → {system_temp:.2f}°C")
        except Exception:
            logger.exception("Failed to read CPU temperature")

        power_usage = 5  # placeholder

        # — Build payload —
        payload = {
            "device":           "SEAS-3",
            "temperature":      temperature,
            "pressure":         pressure,
            "humidity":         humidity,
            "air_quality":      pm25_env,
            "ram_value":        ram_value,
            "system_temperature": system_temp,
            "power_usage":      power_usage,
        }
        logger.info(f"Payload: {json.dumps(payload)}")

        # — POST to server —
        try:
            resp = requests.post(URL, json=payload, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            logger.info("Data logged successfully")
        except Exception:
            logger.exception("Failed to POST data to server")

    except Exception:
        # catch any unexpected error in the whole cycle
        logger.exception("Unexpected error in polling loop")

    # — Wait before next cycle —
    time.sleep(60)
