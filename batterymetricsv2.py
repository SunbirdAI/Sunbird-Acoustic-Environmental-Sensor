#!/usr/bin/python3
"""
SEAS Battery & Power Metrics — INA219 I2C reader
Reads voltage, current and power from INA219 over I2C,
logs to CSV and writes combined_data.json for other scripts to consume.
"""
import time
import csv
import os
import json
import logging
from typing import Optional

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# — LOG DIRECTORY —
LOG_DIR = "/home/pi/environmentsensor/batterydata"
os.makedirs(LOG_DIR, exist_ok=True)

# — INA219 SETUP —
try:
    import board
    import busio
    from adafruit_ina219 import INA219
    i2c = busio.I2C(board.SCL, board.SDA)
    ina = INA219(i2c)
    logger.info("INA219 initialised on I2C")
except Exception as e:
    logger.error(f"Failed to initialise INA219: {e}")
    ina = None


def read_ina219() -> Optional[dict]:
    """Read voltage, current and power from INA219."""
    if ina is None:
        logger.warning("INA219 not available — skipping read")
        return None
    try:
        voltage = ina.bus_voltage + ina.shunt_voltage / 1000  # V
        current = ina.current                                  # mA
        power   = ina.power                                    # W
        logger.debug(f"INA219 → {voltage:.3f}V  {current:.1f}mA  {power:.3f}W")
        return {
            "Voltage":  round(voltage, 3),
            "Current":  round(current, 1),
            "Power":    round(power, 3),
        }
    except Exception as e:
        logger.exception(f"INA219 read error: {e}")
        return None


def log_to_csv(data: dict) -> None:
    today    = time.strftime("%Y-%m-%d")
    csv_file = os.path.join(LOG_DIR, f"NoiseSensor_Log_{today}.csv")
    fieldnames = ["Timestamp"] + list(data.keys())
    file_exists = os.path.isfile(csv_file)
    with open(csv_file, mode="a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        entry = {"Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), **data}
        writer.writerow(entry)
    logger.info(f"Logged to CSV: {entry}")


def write_json(data: dict) -> None:
    json_path = os.path.join(LOG_DIR, "combined_data.json")
    with open(json_path, "w") as jf:
        json.dump(data, jf, indent=4)
    logger.debug(f"Written combined_data.json: {data}")


if __name__ == "__main__":
    logger.info("SEAS Battery Metrics — INA219 start-up")
    try:
        while True:
            data = read_ina219()
            if data:
                log_to_csv(data)
                write_json(data)
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
