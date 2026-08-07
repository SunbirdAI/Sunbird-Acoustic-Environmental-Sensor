#!/usr/bin/env python3
import time
import json
import subprocess
import re
import socket
import requests
import bme680
import serial
import glob
import logging
import sys
from adafruit_pm25.uart import PM25_UART
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from serial.tools.list_ports import comports

# — Configure logging —  
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Server configuration
URL     = "https://noise-sensors-dashboard.herokuapp.com/device_metrics/environmental-parameters/"
HEADERS = {"Content-Type": "application/json"}

# — Build a requests Session with retry for HTTP errors —  
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

def is_connected(host="8.8.8.8", port=53, timeout=3):
    """
    Quick check to see if we can reach a public DNS server.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except OSError:
        return False

# — BME680 setup —  
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

def find_pm25_sensor(baud=9600, timeout=0.25):
    """
    Locate and initialize the PM2.5 sensor on a CP2102 USB bridge.
    First tries the stable by-id symlink, then falls back to filtering by VID/PID.
    """
    # 1) Try Linux by-id symlink
    candidates = glob.glob('/dev/serial/by-id/usb-Silicon_Labs_CP2102*')
    if candidates:
        port = candidates[0]
        logger.info(f"Found CP2102 via by-id on {port}")
    else:
        # 2) Fallback: scan comports for the CP2102 VID/PID
        ports = [p.device for p in comports() if p.vid == 0x10c4 and p.pid == 0xea60]
        if not ports:
            logger.error("No CP2102 device (VID:PID 10C4:EA60) found")
            return None
        port = ports[0]
        logger.info(f"Found CP2102 via VID/PID on {port}")

    # Try opening the serial port and PM2.5 UART
    try:
        uart = serial.Serial(port, baudrate=baud, timeout=timeout)
        pm25 = PM25_UART(uart, reset_pin=None)
        logger.info(f"PM2.5 sensor initialized on {port}")
        return pm25
    except Exception as e:
        logger.exception(f"Failed to open PM2.5 sensor on {port}: {e}")
        return None

# — Initialize PM2.5 sensor (once at startup) —  
pm25 = find_pm25_sensor()
if pm25 is None:
    logger.error("PM2.5 sensor not detected; aborting startup.")
    sys.exit(1)

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

        time.sleep(1)  # let I²C settle

        # — Read PM2.5 —
        pm25_env = None
        try:
            aqdata   = pm25.read()
            pm25_env = aqdata["pm25 env"]
            logger.debug(f"PM2.5 → {pm25_env} µg/m³")
        except Exception:
            logger.exception("PM2.5 read failed; attempting to re-find sensor once")
            new_pm25 = find_pm25_sensor()
            if new_pm25:
                pm25 = new_pm25
            else:
                logger.error("Lost PM2.5 sensor; continuing with None")

        # — Read system stats —
        ram_value = system_temp = None
        try:
            ram_value = int(subprocess.check_output(['free', '-m']).decode().split()[7])
            logger.debug(f"Free RAM → {ram_value} MB")
        except Exception:
            logger.exception("Failed to read RAM value")

        try:
            res = subprocess.check_output(['vcgencmd', 'measure_temp'])
            system_temp = float(re.search(r"temp=([\d\.]+)", res.decode()).group(1))
            logger.debug(f"CPU temp → {system_temp:.2f}°C")
        except Exception:
            logger.exception("Failed to read CPU temperature")

        # — Read battery voltage —
        try:
            with open("/home/pi/environmentsensor/batterydata/combined_data.json") as jf:
                batt = json.load(jf)
            voltage_raw = float(batt.get("Voltage", 0))
            power_usage = voltage_raw / 1000.0
            logger.debug(f"Battery voltage → {power_usage:.3f} V")
        except Exception:
            logger.exception("Failed to read battery JSON; defaulting to 5 V")
            power_usage = 5

        # — Build payload —
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

        # — POST to server if online —
        if is_connected():
            try:
                resp = session.post(URL, json=payload, headers=HEADERS, timeout=10)
                resp.raise_for_status()
                logger.info("Data logged successfully")
            except Exception:
                logger.exception("Failed to POST data to server")
        else:
            logger.warning("No internet connection; skipping POST this cycle")

    except Exception:
        logger.exception("Unexpected error in polling loop")

    # Wait before next cycle
    time.sleep(60)
