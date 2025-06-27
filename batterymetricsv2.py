#!/usr/bin/python3
import serial
import time
import csv
import os
import json

# — SERIAL PORT CONFIGURATION —
ser = serial.Serial(
    port='/dev/ttyS0',
    baudrate=9600,
    timeout=1,
    rtscts=False,
    dsrdtr=False
)

# — LOG DIRECTORY —
LOG_DIR = "/home/pi/environmentsensor/batterydata"
os.makedirs(LOG_DIR, exist_ok=True)

# CSV FIELDNAMES FOR BATTERY —
fieldnames = [
    "Timestamp",
    "Charge_Level (%)",
    "Voltage (mV)",
    "Current (mA)",
    "Battery_Capacity (mAh)",
    "Power (mW)",
    "Health (%)"
]


def send_data(data: str) -> None:
    """Send a UTF-8–encoded string over UART."""
    if ser.is_open:
        ser.write(data.encode('utf-8'))
        print(f"Sent: {data}")


def receive_data() -> str | None:
    """Read one line from UART and return as a stripped UTF-8 string."""
    if not ser.is_open:
        return None

    try:
        raw = ser.readline()
        data = raw.decode('utf-8', errors='ignore').strip()
        if data:
            print(f"Received: {data}")
        return data
    except UnicodeDecodeError as e:
        print(f"UnicodeDecodeError: {e}")
        return None


def request_data_handshake(desc: str, send_cmd: str, expect_resp: str) -> bool:
    """Perform a simple send/expect handshake; handle shutdown command."""
    print(f"Requesting {desc} data handshake...")
    send_data(send_cmd)
    response = receive_data()

    if response == "LOWPOWER-SHUTDOWN":
        os.system("sudo shutdown -h now")
        return True

    if response == expect_resp:
        print("Request Data Handshake Acknowledged.")
        return True

    print("Handshake failed.")
    return False


def parse_data(raw_data: str, log_kind: str) -> dict | None:
    """Parse 'battery' or 'location' data strings into a dict."""
    try:
        if log_kind == "battery":
            parts = [x.strip() for x in raw_data.split('|')]
            return {
                "Charge_Level": parts[0].strip('%'),
                "Voltage": parts[1].strip(' mV'),
                "Current": parts[2].strip(' mA'),
                "Battery_Capacity": parts[3].split(' / ')[0],
                "Power": parts[4].strip(' mW'),
                "Health": parts[5].strip('%'),
            }

        if log_kind == "location":
            lat, lon, alt = [x.strip() for x in raw_data.split(',')]
            return {"latitude": lat, "longitude": lon, "altitude": alt}

    except (IndexError, ValueError):
        print("Error parsing data:", raw_data)
    return None


def log_data_to_csv(parsed: dict, kind: str) -> None:
    """Append parsed data to the appropriate CSV log file."""
    if kind == "battery":
        today = time.strftime("%Y-%m-%d")
        csv_file = os.path.join(LOG_DIR, f"NoiseSensor_Log_{today}.csv")
    elif kind == "location":
        csv_file = os.path.join(LOG_DIR, "gpsDataLog.csv")
    elif kind == "combined":
        csv_file = os.path.join(LOG_DIR, "mainLog.csv")
    else:
        print("Invalid logKind. Use 'battery', 'location' or 'combined'.")
        return

    file_exists = os.path.isfile(csv_file)
    fieldnames = ["Timestamp"] + list(parsed.keys())

    with open(csv_file, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        entry = {"Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), **parsed}
        writer.writerow(entry)
        print("Logged to CSV:", entry)


def request_battery_data() -> None:
    if request_data_handshake("Battery", "RDHS", "RDHS-ACK"):
        resp = receive_data()
        if resp:
            data = parse_data(resp, "battery")
            if data:
                log_data_to_csv(data, "battery")


def request_location_data() -> None:
    if request_data_handshake("Location", "RLOCHS", "RLOCHS-ACK"):
        resp = receive_data()
        if resp:
            data = parse_data(resp, "location")
            if data:
                log_data_to_csv(data, "location")


def request_power_status() -> None:
    if request_data_handshake("Power_Status", "PSHS", "PSHS-ACK"):
        resp = receive_data()
        if resp == "LOWPOWER-SHUTDOWN":
            os.system("sudo shutdown -h now")


def request_combined_data() -> dict:
    """Fetch battery and location data in sequence, log each, then write combined logs."""
    combined = {}
    got_batt = got_loc = False

    time.sleep(3)
    if request_data_handshake("Battery", "RDHS", "RDHS-ACK"):
        resp = receive_data()
        if resp:
            batt = parse_data(resp, "battery")
            if batt:
                combined.update(batt)
                log_data_to_csv(batt, "battery")
                got_batt = True

    time.sleep(3)
    if request_data_handshake("Location", "RLOCHS", "RLOCHS-ACK"):
        resp = receive_data()
        if resp:
            loc = parse_data(resp, "location")
            if loc:
                combined.update(loc)
                log_data_to_csv(loc, "location")
                got_loc = True

    if got_batt and got_loc:
        log_data_to_csv(combined, "combined")
        json_path = os.path.join(LOG_DIR, "combined_data.json")
        with open(json_path, "w") as jf:
            json.dump(combined, jf, indent=4)

    return combined


if __name__ == "__main__":
    try:
        time.sleep(2)
        print("MCU Communication Start-up")
        while True:
            request_combined_data()
            time.sleep(3)
            request_power_status()

    except KeyboardInterrupt:
        print("\nExiting program.")

    finally:
        print("Program terminated. Press Ctrl+C to restart.")
