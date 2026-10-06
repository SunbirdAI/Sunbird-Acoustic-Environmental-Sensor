"""Environment + power logger: BME680 (temp/RH/pressure/gas -> approx IAQ) and
Waveshare UPS HAT (INA219) battery readings, one JSON line per interval."""
import json, os, socket, struct, sys, time
from datetime import datetime, timezone
import bme680
import saesapi
from smbus2 import SMBus

BUS = int(os.environ.get("SAES_I2C_BUS", 2))
BME_ADDR = int(os.environ.get("SAES_BME_ADDR", 0x77))
INA_ADDR = int(os.environ.get("SAES_INA_ADDR", 0x42))
SHUNT_OHMS = float(os.environ.get("SAES_SHUNT_OHMS", 0.01))  # UNVERIFIED, see README
INTERVAL = int(os.environ.get("SAES_SENSOR_INTERVAL", 30))
DATA_DIR = os.environ.get("SAES_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
BASELINE_FILE = os.path.join(DATA_DIR, "iaq_baseline.json")
BURN_IN_S, HUM_BASELINE, HUM_WEIGHT = 300, 40.0, 25.0
POST_EVERY = int(os.environ.get("SAES_ENV_POST_S", 60))
LAST_NOISE = os.path.join(DATA_DIR, "last_noise.json")   # written by inference.py

def ram_available_mb():
    for l in open("/proc/meminfo"):
        if l.startswith("MemAvailable"):
            return int(l.split()[1]) // 1024

def cpu_temp_c():
    return round(int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000, 1)

DB_OFFSET = os.environ.get("SAES_DB_OFFSET")   # dBFS -> approx dB SPL; unset = don't report db_level

def latest_db(max_age_s=300):
    if DB_OFFSET is None:
        return None
    try:
        d = json.load(open(LAST_NOISE))
        if time.time() - d["t"] <= max_age_s:
            return round(d["rms_dbfs"] + float(DB_OFFSET), 1)
    except Exception:
        pass
    return None

def ina219_read(bus):
    def reg(r):
        d = bus.read_i2c_block_data(INA_ADDR, r, 2)
        return (d[0] << 8) | d[1]
    raw_bus = reg(0x02)
    volts = (raw_bus >> 3) * 0.004
    raw_shunt = struct.unpack(">h", struct.pack(">H", reg(0x01)))[0]
    amps = raw_shunt * 10e-6 / SHUNT_OHMS          # + charging, - discharging
    pct = max(0.0, min(100.0, (volts - 6.0) / 2.4 * 100))   # 2S 18650: 6.0-8.4 V
    volts += raw_shunt * 10e-6
    return {"batt_v": round(volts, 3), "batt_a": round(amps, 4),
            "batt_w": round(volts * amps, 3), "batt_pct": round(pct, 1)}

def load_baseline():
    try:
        return json.load(open(BASELINE_FILE))["gas_baseline"]
    except Exception:
        return None

def iaq(gas, hum, baseline):
    hum_off = hum - HUM_BASELINE
    if hum_off > 0:
        hum_score = (100 - HUM_BASELINE - hum_off) / (100 - HUM_BASELINE) * HUM_WEIGHT
    else:
        hum_score = (HUM_BASELINE + hum_off) / HUM_BASELINE * HUM_WEIGHT
    gas_off = baseline - gas
    if gas_off > 0:
        gas_score = gas / baseline * (100 - HUM_WEIGHT)
    else:
        gas_score = 100 - HUM_WEIGHT
    return round(hum_score + gas_score, 1)   # 0-100, higher = cleaner (approximate)

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    bus = SMBus(BUS)
    s = bme680.BME680(i2c_addr=BME_ADDR, i2c_device=bus)
    s.set_humidity_oversample(bme680.OS_2X); s.set_pressure_oversample(bme680.OS_4X)
    s.set_temperature_oversample(bme680.OS_8X); s.set_filter(bme680.FILTER_SIZE_3)
    s.set_gas_status(bme680.ENABLE_GAS_MEAS)
    s.set_gas_heater_temperature(320); s.set_gas_heater_duration(150); s.select_gas_heater_profile(0)
    baseline = load_baseline(); history = []; start = time.time(); last_post = 0
    host = socket.gethostname()
    while True:
        rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": host}
        try:
            if s.get_sensor_data():
                d = s.data
                rec.update(temp_c=round(d.temperature, 2), humidity=round(d.humidity, 2),
                           pressure_hpa=round(d.pressure, 2))
                if d.heat_stable:
                    rec["gas_ohms"] = int(d.gas_resistance)
                    history = (history + [d.gas_resistance])[-50:]
                    if baseline is None and time.time() - start >= BURN_IN_S and len(history) >= 20:
                        baseline = sum(history[-20:]) / 20
                        json.dump({"gas_baseline": baseline}, open(BASELINE_FILE, "w"))
                    if baseline:
                        rec["iaq_approx"] = iaq(d.gas_resistance, d.humidity, baseline)
                    else:
                        rec["iaq_approx"] = None   # still burning in
        except Exception as e:
            rec["bme_error"] = str(e)
        try:
            rec.update(ina219_read(bus))
        except Exception as e:
            rec["ups_error"] = str(e)
        try:
            rec["ram_available_mb"], rec["cpu_temp_c"] = ram_available_mb(), cpu_temp_c()
        except Exception as e:
            rec["sys_error"] = str(e)
        now = time.time()
        if now - last_post >= POST_EVERY:
            last_post = now
            iaq_v = rec.get("iaq_approx")
            payload = {"device": saesapi.DEVICE_ID, "temperature": rec.get("temp_c"),
                       "pressure": rec.get("pressure_hpa"), "humidity": rec.get("humidity"),
                       # old PM2.5 field: higher = worse. IAQ score is higher = cleaner, so invert.
                       "air_quality": None if iaq_v is None else round(100 - iaq_v, 1),
                       "ram_value": rec.get("ram_available_mb"),
                       "system_temperature": rec.get("cpu_temp_c"),
                       "power_usage": rec.get("batt_v"),       # battery voltage, as in old logger
                       "db_level": latest_db()}
            missing = [k for k, v in payload.items() if v is None]   # server rejects nulls
            if missing:
                rec["posted"], rec["post_detail"] = False, "skipped, no value yet for: " + ",".join(missing)
            else:
                rec["posted"], rec["post_detail"] = saesapi.post_json("/device_metrics/environmental-parameters/", payload)
        path = os.path.join(DATA_DIR, "sensors-%s.jsonl" % rec["ts"][:10].replace("-", ""))
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(json.dumps(rec), flush=True)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
