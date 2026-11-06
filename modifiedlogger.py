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
import fcntl
import smbus
import numpy as np
from scipy import signal
from statistics import mean
from adafruit_pm25.uart import PM25_UART
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from serial.tools.list_ports import comports
from math import log10

# -----------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------
# Server Configuration
# -----------------------------------------------------------
URL = "https://noise-api.sunbird.ai/device_metrics/environmental-parameters/"
HEADERS = {"Content-Type": "application/json"}

# -----------------------------------------------------------
# Requests Session with Retry
# -----------------------------------------------------------
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

# -----------------------------------------------------------
# Check Internet Connection
# -----------------------------------------------------------
def is_connected(host="8.8.8.8", port=53, timeout=3):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except OSError:
        return False

# -----------------------------------------------------------
# Noise Level Measurement (LAeq, dB(A))
# -----------------------------------------------------------
MIC_LOCK = "/tmp/seas-mic.lock"

# Record the I2S mic straight from the hardware device: no softvol gain and no
# stereo->mono averaging (the mic is on the LEFT channel, the right one is silent).
MIC_DEVICE   = "dmic_hw"
MIC_RATE     = 44100
MIC_CHANNEL  = 0

# SPL = LAeq(dBFS) + CAL_OFFSET_DB.  PROVISIONAL, from the INMP441 datasheet
# (-26 dBFS @ 94 dB SPL, i.e. -29 dBFS RMS -> 123 dB). Replace with a value
# measured against a 114 dB calibrator or a reference meter (Casella).
CAL_OFFSET_DB = 123.0

def _a_weighting_sos(fs):
    """IEC 61672 A-weighting as second-order sections (bilinear transform)."""
    f1, f2, f3, f4 = 20.598997, 107.65265, 737.86223, 12194.217
    a1000 = 1.9997
    w = lambda f: -2 * np.pi * f
    z = [0, 0, 0, 0]
    p = [w(f4), w(f4), w(f1), w(f1), w(f2), w(f3)]
    k = (2 * np.pi * f4) ** 2 * 10 ** (a1000 / 20)
    z, p, k = signal.bilinear_zpk(z, p, k, fs)
    return signal.zpk2sos(z, p, k)

_A_SOS = _a_weighting_sos(MIC_RATE)

def get_db_level(duration=5):
    """Returns LAeq in dB(A) over `duration` seconds, or NaN on failure.
    Audio is piped straight into memory and never written to disk."""
    try:
        # Shared with inference.py: the I2S mic can only be opened by one process
        with open(MIC_LOCK, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            raw = subprocess.run(
                ["arecord", "-D", MIC_DEVICE, "-c2", "-r", str(MIC_RATE),
                 "-f", "S32_LE", "-t", "raw", "-d", str(duration), "-q", "-"],
                capture_output=True, timeout=duration + 10, check=True
            ).stdout

        x = np.frombuffer(raw, dtype=np.int32).reshape(-1, 2)[:, MIC_CHANNEL] / 2**31
        x = x[int(0.2 * MIC_RATE):]  # drop mic start-up transient
        if len(x) < MIC_RATE:
            logger.warning("Noise level: recording too short")
            return float('nan')

        # A-weighting also removes the mic's DC offset; energy average = LAeq
        xa = signal.sosfilt(_A_SOS, x)[int(0.1 * MIC_RATE):]  # skip filter settling
        ms = float(np.mean(xa ** 2))
        if ms <= 0:
            return float('nan')
        laeq_dbfs = 10 * log10(ms)
        # Floor at 0: dB(A) SPL is not reported as negative
        return round(max(0.0, laeq_dbfs + CAL_OFFSET_DB), 2)

    except subprocess.TimeoutExpired:
        logger.warning("Noise level: arecord timed out")
        return float('nan')
    except Exception as e:
        logger.warning(f"Noise level: measurement failed: {e}")
        return float('nan')

# -----------------------------------------------------------
# BME680 Initialization
# -----------------------------------------------------------
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
sensor.set_gas_status(bme680.ENABLE_GAS_MEAS)
sensor.set_gas_heater_temperature(320)
sensor.set_gas_heater_duration(150)
sensor.select_gas_heater_profile(0)

# Gas Sensor Burn-in
gas_burn_in = []
burn_in_time = 30
logger.info(f"Collecting gas burn-in for {burn_in_time}s...")

start = time.time()
while time.time() - start < burn_in_time:
    if sensor.get_sensor_data() and sensor.data.heat_stable:
        gas_burn_in.append(sensor.data.gas_resistance)
    time.sleep(1)

gas_baseline = mean(gas_burn_in) if gas_burn_in else None
hum_baseline = 40.0
hum_weighting = 0.25

logger.info(f"gas_baseline={gas_baseline:.1f} Ohms")

# -----------------------------------------------------------
# INA219 (Power Sensor)
# -----------------------------------------------------------
class BusVoltageRange:
    RANGE_16V = 0x00
    RANGE_32V = 0x01

class Gain:
    DIV_1_40MV = 0x00
    DIV_2_80MV = 0x01
    DIV_4_160MV = 0x02
    DIV_8_320MV = 0x03

class ADCResolution:
    ADCRES_12BIT_32S = 0x0D

class Mode:
    SANDBVOLT_CONTINUOUS = 0x07

_REG_CONFIG = 0x00
_REG_SHUNTVOLTAGE = 0x01
_REG_BUSVOLTAGE = 0x02
_REG_CALIBRATION = 0x05

class INA219:
    def __init__(self, i2c_bus=1, addr=0x42):
        self.bus = smbus.SMBus(i2c_bus)
        self.addr = addr
        self._cal_value = 4096

        self.write(_REG_CALIBRATION, self._cal_value)

        cfg = (
            BusVoltageRange.RANGE_32V << 13 |
            Gain.DIV_8_320MV << 11 |
            ADCResolution.ADCRES_12BIT_32S << 7 |
            ADCResolution.ADCRES_12BIT_32S << 3 |
            Mode.SANDBVOLT_CONTINUOUS
        )
        self.write(_REG_CONFIG, cfg)

    def read(self, addr):
        data = self.bus.read_i2c_block_data(self.addr, addr, 2)
        return (data[0] << 8) | data[1]

    def write(self, addr, val):
        self.bus.write_i2c_block_data(self.addr, addr,
                                      [(val >> 8) & 0xFF, val & 0xFF])

    def getBusVoltage_V(self):
        raw = self.read(_REG_BUSVOLTAGE)
        return ((raw >> 3) * 0.004)

# -----------------------------------------------------------
# PM2.5 Sensor
# -----------------------------------------------------------
def find_pm25_sensor(baud=9600, timeout=0.25):
    candidates = glob.glob('/dev/serial/by-id/usb-Silicon_Labs_CP2102*')

    if not candidates:
        ports = [p.device for p in comports()
                 if p.vid == 0x10C4 and p.pid == 0xEA60]
        candidates = ports

    if not candidates:
        logger.warning("No PM2.5 sensor found")
        return None

    try:
        uart = serial.Serial(candidates[0], baudrate=baud, timeout=timeout)
        return PM25_UART(uart, reset_pin=None)
    except Exception:
        logger.exception("PM2.5 init failed")
        return None

pm25 = find_pm25_sensor()
ina219 = INA219()

logger.info("All sensors initialized. Starting main loop...")

# -----------------------------------------------------------
# Main Loop
# -----------------------------------------------------------
while True:
    try:
        # 1. Noise Level
        db_level = get_db_level(duration=5)
        if db_level == db_level:  # not NaN
            logger.info(f"Noise level: {db_level:6.2f} dB(A)")
        else:
            logger.warning("Noise level unavailable")
            db_level = None

        # 2. BME680 readings
        temperature = pressure = humidity = gas_resistance = None

        if sensor.get_sensor_data():
            temperature = sensor.data.temperature
            pressure = sensor.data.pressure
            humidity = sensor.data.humidity
            gas_resistance = sensor.data.gas_resistance

        # 3. Air Quality Calculation
        air_quality = None

        if gas_baseline and humidity is not None:
            gas_offset = gas_baseline - gas_resistance
            hum_offset = humidity - hum_baseline

            hum_score = (
                (100 - hum_baseline - hum_offset) / (100 - hum_baseline) * (hum_weighting * 100)
                if hum_offset > 0 else
                (hum_baseline + hum_offset) / hum_baseline * (hum_weighting * 100)
            )

            gas_score = (
                (gas_resistance / gas_baseline) * (100 - hum_weighting * 100)
                if gas_offset > 0 else
                100 - (hum_weighting * 100)
            )

            air_quality = hum_score + gas_score

        # PM2.5 overrides BME680 AQ
        if pm25:
            try:
                aq_data = pm25.read()
                air_quality = aq_data.get("pm25 env")
            except Exception:
                pass

        # 4. System Stats
        try:
            # MemAvailable (MB): memory actually free for use, not total RAM
            with open("/proc/meminfo") as f:
                ram_value = next(int(l.split()[1]) // 1024 for l in f if l.startswith("MemAvailable"))
        except Exception:
            ram_value = None

        try:
            res = subprocess.check_output(["vcgencmd", "measure_temp"])
            system_temperature = float(re.search(r"temp=([\d\.]+)", res.decode()).group(1))
        except Exception:
            system_temperature = None

        try:
            power_usage = ina219.getBusVoltage_V()
        except Exception:
            power_usage = None

        # 5. Build Payload
        payload = {
            "device": "SEAS-2",
            "temperature": temperature,
            "pressure": pressure,
            "humidity": humidity,
            "air_quality": air_quality,
            "ram_value": ram_value,
            "system_temperature": system_temperature,
            "power_usage": power_usage,
            "db_level": db_level
        }

        logger.info(f"Payload: {json.dumps(payload)}")

        # 6. Upload
        if is_connected():
            try:
                resp = session.post(URL, json=payload, headers=HEADERS, timeout=10)
                resp.raise_for_status()
                logger.info("Data uploaded successfully")
            except Exception as e:
                logger.error(f"Upload failed: {e}")
        else:
            logger.warning("No internet connection")

    except Exception as e:
        logger.exception(f"Unexpected error in main loop: {e}")

    time.sleep(60)
