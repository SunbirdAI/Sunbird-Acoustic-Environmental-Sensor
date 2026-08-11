#!/usr/bin/env python3
"""
SEAS Environmental Data Logger
Reads BME680 (I2C) + PMS5003 (USB-UART, optional) + system stats
and POSTs to server every 60s. If PM2.5 sensor is absent, continues
with air_quality = None rather than aborting.
"""
import time
import json
import subprocess
import re
import socket
import logging
import sys
import glob

import requests
import bme680
import serial
from adafruit_pm25.uart import PM25_UART
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from serial.tools.list_ports import comports

# — Logging —
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# — Server —
URL     = "https://noise-sensors-dashboard.herokuapp.com/device_metrics/environmental-parameters/"
HEADERS = {"Content-Type": "application/json"}

# — HTTP session with retry —
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://",  adapter)
session.mount("https://", adapter)


def is_connected(host="8.8.8.8", port=53, timeout=3):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except OSError:
        return False


# — BME680 —
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


# — PM2.5 — optional, graceful if absent —
def find_pm25_sensor(baud=9600, timeout=0.25):
    candidates = glob.glob('/dev/serial/by-id/usb-Silicon_Labs_CP2102*')
    if candidates:
        port = candidates[0]
        logger.info(f"Found CP2102 via by-id on {port}")
    else:
        ports = [p.device for p in comports() if p.vid == 0x10c4 and p.pid == 0xea60]
        if not ports:
            logger.warning("No CP2102 PM2.5 sensor found — will run without PM2.5 data")
            return None
        port = ports[0]
        logger.info(f"Found CP2102 via VID/PID on {port}")
    try:
        uart = serial.Serial(port, baudrate=baud, timeout=timeout)
        pm25 = PM25_UART(uart, reset_pin=None)
        logger.info(f"PM2.5 sensor initialised on {port}")
        return pm25
    except Exception as e:
        logger.warning(f"Could not open PM2.5 sensor on {port}: {e} — continuing without it")
        return None


pm25 = find_pm25_sensor()
logger.info("Entering polling loop…")

# — Main loop —
while True:
    try:
        # BME680
        temperature = pressure = humidity = None
        if sensor.get_sensor_data():
            temperature = sensor.data.temperature
            pressure    = sensor.data.pressure
            humidity    = sensor.data.humidity
            logger.debug(f"BME680 → T={temperature:.2f}°C  P={pressure:.2f}hPa  H={humidity:.2f}%")
        else:
            logger.warning("BME680 .get_sensor_data() returned False")

        time.sleep(1)

        # PM2.5 — skip gracefully if not present
        pm25_env = None
        if pm25 is not None:
            try:
                aqdata   = pm25.read()
                pm25_env = aqdata["pm25 env"]
                logger.debug(f"PM2.5 → {pm25_env} µg/m³")
            except Exception:
                logger.warning("PM2.5 read failed — attempting re-detect")
                pm25 = find_pm25_sensor()

        # System stats
        ram_value = system_temp = None
        try:
            ram_value = int(subprocess.check_output(['free', '-m']).decode().split()[7])
            logger.debug(f"Free RAM → {ram_value} MB")
        except Exception:
            logger.exception("Failed to read RAM")

        try:
            res = subprocess.check_output(['vcgencmd', 'measure_temp'])
            system_temp = float(re.search(r"temp=([\d\.]+)", res.decode()).group(1))
            logger.debug(f"CPU temp → {system_temp:.2f}°C")
        except Exception:
            logger.exception("Failed to read CPU temp")

        # Battery voltage from INA219 JSON (written by seas-batterydata)
        power_usage = None
        try:
            batt_path = "/home/pi/environmentsensor/batterydata/combined_data.json"
            with open(batt_path) as jf:
                batt = json.load(jf)
            power_usage = float(batt.get("Voltage", 0))
            logger.debug(f"Battery voltage → {power_usage:.3f} V")
        except Exception:
            logger.warning("Could not read battery JSON — power_usage will be None")

        # Payload
        payload = {
            "device":             "SEAS-3",
            "temperature":        temperature,
            "pressure":           pressure,
            "humidity":           humidity,
            "air_quality":        pm25_env,
            "ram_value":          ram_value,
            "system_temperature": system_temp,
            "power_usage":        power_usage,
        }
        logger.info(f"Payload: {json.dumps(payload)}")

        # POST
        if is_connected():
            try:
                resp = session.post(URL, json=payload, headers=HEADERS, timeout=10)
                resp.raise_for_status()
                logger.info("Data posted successfully")
            except Exception:
                logger.exception("POST failed")
        else:
            logger.warning("No internet — skipping POST this cycle")

    except Exception:
        logger.exception("Unexpected error in polling loop")

    time.sleep(60)
