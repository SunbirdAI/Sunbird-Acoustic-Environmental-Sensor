# Sunbird Acoustic Environmental Sensor (SAES) — Setup Manual

This manual guides you through setting up a Raspberry Pi–based acoustic environmental sensor using:

- **MEMS microphone (INMP411)** for acoustic data  
- **BME680** for temperature, humidity, pressure, and gas readings  
- **Plantower PMSA003I** PM2.5 sensor  
- **TensorFlow Lite** for on-device edge inference  

By the end, your Raspberry Pi will collect environmental and acoustic data, process it on the edge using machine learning, and upload results for further analysis.

---

## Table of Contents

1. [Prerequisites](#prerequisites)  
2. [Install Raspberry Pi OS](#install-raspberry-pi-os)  
3. [Enable I²S for MEMS Microphone](#enable-i%C2%B2s-for-mems-microphone)  
4. [Wiring Diagrams](#wiring-diagrams)  
   - [4.1 MEMS Microphone (INMP411)](#41-mems-microphone-inmp411)  
   - [4.2 BME680 (I²C)](#42-bme680-i%C2%B2c)  
   - [4.3 PMSA003I PM2.5 Sensor (UART)](#43-pmsa003i-pm25-sensor-uart)  
5. [Install Required Libraries](#install-required-libraries)  
6. [TensorFlow Lite Setup](#tensorflow-lite-setup)  
7. [I²S MEMS Microphone Test](#i%C2%B2s-mems-microphone-test)  
8. [Setup as a Systemd Service](#setup-as-a-systemd-service)  
9. [Setup as a Cron Job (Optional)](#setup-as-a-cron-job-optional)  
10. [Repo Structure](#recommended-repo-structure)  

---

## 1. Prerequisites

**Hardware:**

- Raspberry Pi Zero 2W, Pi 4, or Pi 3B+/3A+  
- 16 GB (or larger) microSD card  
- 5 V / ≥ 3 A USB power supply  
- INMP411 MEMS microphone (I²S)  
- BME680 environmental sensor (I²C)  
- Plantower PMSA003I PM2.5 sensor (UART/I²C)  
- SIM7600E/SIM7600G-H module for LTE connectivity (optional)  
- Jumper wires, breadboard or soldered headers  
- Internet connection (for setup)  

---

## 2. Install Raspberry Pi OS

1. Download Raspberry Pi OS (32-bit lite or desktop) from  
   https://www.raspberrypi.com/software/  
2. Flash microSD using Raspberry Pi Imager or balenaEtcher.  
3. Insert microSD, boot, and complete initial setup.  
4. Update and upgrade:

   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo reboot
   ```

---

## 3. Enable I²S for MEMS Microphone

1. Edit `/boot/config.txt`:

   ```bash
   sudo nano /boot/config.txt
   ```

2. Append at the end:

   ```
   dtparam=i2s=on
   dtoverlay=googlevoicehat-soundcard
   ```

3. Reboot:

   ```bash
   sudo reboot
   ```

> **Note:** The `googlevoicehat-soundcard` overlay works with most I²S MEMS microphones.

---

## 4. Wiring Diagrams

### 4.1 MEMS Microphone (INMP411)

| Microphone Pin | Pi Pin                     |
| -------------- | -------------------------- |
| VIN (3.3 V)    | 3V3 (Pin 1)                |
| GND            | GND (Pin 9)                |
| SD (Data)      | GPIO18 / PCM_CLK (Pin 12)  |
| WS (LRCLK)     | GPIO19 / PCM_FS (Pin 35)   |
| SCK (BitClk)   | GPIO23 / PCM_DIN (Pin 16)  |

### 4.2 BME680 (I²C)

| Sensor Pin | Pi Pin         |
| ---------- | -------------- |
| VIN (3–5 V) | 3V3 (Pin 1)   |
| GND         | GND (Pin 6)   |
| SDA         | SDA1 (Pin 3)  |
| SCL         | SCL1 (Pin 5)  |

### 4.3 PMSA003I PM2.5 Sensor (UART)

| Sensor Pin | Pi Pin                   |
| ---------- | ------------------------ |
| VIN (5 V)  | 5V (Pin 2)               |
| GND        | GND (Pin 14)             |
| TX         | GPIO15 (UART RX, Pin 10) |
| RX         | GPIO14 (UART TX, Pin 8)  |

---

## 5. Install Required Libraries

```bash
# Install venv tools
sudo apt install python3-pip python3-venv -y

# Create and activate virtual environment
python3 -m venv ~/envs/sensor-env
source ~/envs/sensor-env/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install required Python libraries
pip install bme680 adafruit-circuitpython-pmsa003i sounddevice numpy pyserial tflite-runtime

# Install I²S tools for microphone testing
sudo apt install i2s-tools -y
```

---

## 6. TensorFlow Lite Setup

```bash
# Install dependencies
sudo apt install libatlas-base-dev libjpeg-dev liblapack-dev -y

# Install tflite-runtime (inside your venv)
pip install tflite-runtime

# Verify TensorFlow Lite
python3 - <<EOF
import tflite_runtime.interpreter as tflite
print("TFLite runtime ready")
EOF
```

For detailed builds and optimizations, see the QEngineering guide.

---

## 7. I²S MEMS Microphone Test

**Record audio:**

```bash
arecord --format=S32_LE --rate=16000 --channels=2 test.wav
```

**Playback:**

```bash
aplay test.wav
```

---

## 8. Setup as a Systemd Service

Create and enable a systemd service to run your logger on boot:

```bash
sudo nano /etc/systemd/system/logdata.service
```

Paste the following:

```ini
[Unit]
Description=Environment Sensor Logging Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/environmentsensor/scripts/modifiedlogger.py
Restart=always
User=pi
WorkingDirectory=/home/pi/environmentsensor/scripts
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Then reload, enable, and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable logdata.service
sudo systemctl start logdata.service

# Check status
sudo systemctl status logdata.service

# View live logs
journalctl -u logdata.service -f
```

---

## 9. Setup as a Cron Job (Optional)

If you prefer scheduled runs instead of or alongside systemd:

```bash
crontab -e
```

Add the following line to run every 5 minutes:

```cron
*/5 * * * * /home/pi/environmentsensor/scripts/record-infer-noise-upload.py >> /home/pi/environmentsensor/logs/record-infer.log 2>&1
```

Verify with:

```bash
crontab -l
```

---

## 10. Repo Structure

```
Sunbird-Acoustic-Env-Sensor/
│
├── environmentsensor/
│   └── scripts/
│       ├── modifiedlogger.py
│       ├── record-infer-noise-upload.py
│       └── inference_model.tflite
│
├── logs/
├── wiring_diagrams/
├── requirements.txt
└── README.md  <-- this file
```

---

### Notes

- Always verify your sensor connections before powering on.  
- Use `raspi-config` to enable interfaces (I2C, UART, I²S) if needed.  
- To reduce power consumption when off-grid, consider disabling HDMI, Wi-Fi, and other unused interfaces.  
