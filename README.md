# Sunbird Acoustic Environmental Sensor (SAES) v1 — Setup Manual

This manual guides you through setting up a Raspberry Pi–based acoustic environmental sensor using:

- **MEMS microphone (INMP441)** for acoustic data  
- **BME680** for temperature, humidity, pressure, and gas readings  
- **Plantower PMS5003** PM2.5 Air Quality Sensor and Breadboard Adapter Kit - PMS5003
- **Pi Zero 2W** raspberry pi of choice
- **TensorFlow Lite** for on-device edge inference
- **SIM7600G-H 4G modem breakout or HAT** data connectivity for remote deployments 

By the end, your Raspberry Pi will collect environmental and acoustic data, process it on the edge using machine learning, and upload results for further analysis.

---

## Table of Contents

1. [Prerequisites](#prerequisites)  
2. [Install Raspberry Pi OS](#install-raspberry-pi-os)  
3. [Enable I²S for MEMS Microphone](#enable-i%C2%B2s-for-mems-microphone)  
4. [Wiring Diagrams](#wiring-diagrams)  
   - [4.1 MEMS Microphone (INMP441)](#41-mems-microphone-inmp441)  
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
- INMP441 MEMS microphone (I²S)  
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
Link: https://learn.adafruit.com/adafruit-i2s-mems-microphone-breakout/raspberry-pi-wiring-test

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

## 4. Wiring Connections

### MEMS Microphone (INMP441)

| Microphone Pin | Pi Pin                     |
| -------------- | -------------------------- |
| VIN (3.3 V)    | 3V3 (Pin 1)                |
| GND            | GND (Pin 9)                |
| SD (Data)      | GPIO18 / PCM_CLK (Pin 12)  |
| WS (LRCLK)     | GPIO19 / PCM_FS (Pin 35)   |
| SCK (BitClk)   | GPIO23 / PCM_DIN (Pin 16)  |

### BME680 (I²C)

| Sensor Pin | Pi Pin         |
| ---------- | -------------- |
| VIN (3–5 V) | 3V3 (Pin 1)   |
| GND         | GND (Pin 6)   |
| SDA         | SDA1 (Pin 3)  |
| SCL         | SCL1 (Pin 5)  |

### PMSA003I PM2.5 Sensor (UART)

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
pip install sounddevice numpy pyserial adafruit-circuitpython-bme680

# Install I²S tools for microphone testing
sudo apt install i2s-tools -y
```

---

## 6. TensorFlow Lite Setup

```bash
# Install dependencies
sudo apt install libatlas-base-dev libjpeg-dev liblapack-dev -y

# the tools needed
$ sudo apt-get install cmake curl

# download the latest TensorFlow version (2.6.0)
$ wget -O tensorflow.zip https://github.com/tensorflow/tensorflow/archive/v2.6.0.zip

# unpack and give the folder a convenient name
$ unzip tensorflow.zip
$ mv tensorflow-2.6.0 tensorflow
$ cd tensorflow

# get the dependencies
$ ./tensorflow/lite/tools/make/download_dependencies.sh
# run the C++ installation (± 25 min)
$ ./tensorflow/lite/tools/make/build_rpi_lib.sh

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
## 8. Install Sound Meter Package to Read Decibels prior to Audio Capture
sudo apt-get update
sudo apt-get install -y portaudio19-dev python-dev alsa-utils
pip install soundmeter

Run this in the terminal to confirm soundmeter functionality 
```
soundmeter
```
```
$ soundmeter --collect --seconds 10
Collecting RMS values...
   154  Timeout
Collected result:
    min:        152
    max:        211
    avg:        156
```

## 9. Setup as a Meta Data Logging Systemd Service

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
## 10. Setup service to measure decibel, record sound, infer and upload it to the cloud
```bash
sudo nano /etc/systemd/system/noiseinference.service
```
Paste the following:
```ini
[Unit]
Description=Sound Inference Script
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/environmentsensor/scripts/inference.py
Restart=always
User=pi
WorkingDirectory=/home/pi/environmentsensor/scripts
Environment=PYTHONUNBUFFERED=1

# Uncomment below if root/sudo access is needed by the script:
# ExecStartPre=/bin/sleep 30
# CapabilityBoundingSet=CAP_SYS_ADMIN CAP_NET_ADMIN
# AmbientCapabilities=CAP_SYS_ADMIN CAP_NET_ADMIN
# or use sudo directly if needed and passwordless is set up
# ExecStart=/usr/bin/sudo /usr/bin/python3 /home/pi/environmentsensor/scripts/inference.py

[Install]
WantedBy=multi-user.target
```
Then reload, enable, and start the service:

```bash
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable noiseinference.service
sudo systemctl start noiseinference.service


# Check status
sudo systemctl status noiseinference.service

# View live logs
journalctl -u noiseinference.service -f
```
---

## 11. Setup service to measure sensor energy metrics, gps data and communicate with the raspberry pi 
```bash
sudo nano /etc/systemd/system/noisehardwaredata.service
```
Paste the following:
```ini
[Unit]
Description=Hardware Data Logger Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/environmentsensor/scripts
ExecStart=/usr/bin/python3 /home/pi/environmentsensor/scripts/hardwaredata.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Then reload, enable, and start the service:

```bash
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable noisehardwaredata.service
sudo systemctl start noisehardwaredata.service


# Check status
sudo systemctl status noisehardwaredata.service

# View live logs
journalctl -u noisehardwaredata.service -f
```

---

## 12. Setup as a Cron Job (Optional)

If you prefer scheduled runs instead of or alongside systemd:

```bash
crontab -e
```

Add the following line to run every 5 minutes:

```cron
*/5 * * * * /home/pi/environmentsensor/scripts/hardwaredata.py >> /home/pi/environmentsensor/logs/hardwaredata.log 2>&1
```

Verify with:

```bash
crontab -l
```
## 13. Communication Setup: WiFi / LTE modem sim7600G-h

**WiFi Setup (Recommended for Lab/Test Deployments)**
1. Ensure that the Raspberry Pi connects to your preferred WiFi network before deployment:
2. Open the Raspberry Pi terminal.
3. Configure WiFi using raspi-config or by editing wpa_supplicant.conf:

```bash
sudo nano /etc/wpa_supplicant/wpa_supplicant.conf
```
4. Add your network details:
```
network={
  ssid="YourNetworkName"
  psk="YourNetworkPassword"
}
```
Reboot to apply:

```bash
sudo reboot
```

**4G Cellular Setup (For Remote/Field Deployments)**

For remote locations without reliable WiFi, use the SIM7600G-H 4G modem.

**Option A: USB-Based Connection**
1. Connect the SIM7600G-H USB modem to your computer using a micro-USB male to micro-USB female cable.
2. Open a serial terminal tool (e.g., PuTTY, CoolTerm, or TeraTerm).
3. Identify the AT port, typically labeled as AT 9001 or similar.
4. Connect to the AT port using a baud rate of 115200.
5. Send the following command to switch the modem to hot plug mode:
```
bash
AT+CUSBPIDSWITCH=9011,1,1
```
6. Wait for the modem to restart.
7. Now connect the modem to the Raspberry Pi via a USB port.

Important: Disable WiFi on the Pi to avoid network conflicts when using the modem.

**Option B: HAT-Based Connection**

Alternatively, you can use the SIM7600G-H 4G HAT B by Waveshare:https://www.waveshare.com/sim7600g-h-4g-hat-b.htm

Product link: SIM7600G-H 4G HAT B (Waveshare)

Simply screw the HAT directly onto the Raspberry Pi GPIO pins.

Connect the micro-USB port of the HAT to the Pi for data and power.

Tested alternative: SIM7600G-H Breakout Module on AliExpress(https://www.aliexpress.com/i/4000078222573.html)

---

## 14. Device Structure

```
Sunbird-Acoustic-Environmental-Sensor/
│
├── environmentsensor/
│   ├── scripts/
│   │   ├── modifiedlogger.py
│   │   ├── inference.py
│   │   └── hardwaredata.py
│   │
│   ├── quantizedmodels/
│   │   └── inference_model.tflite
│   │
│   ├── logs/
│   ├── batterydata/
│   └── rawaudio/
│
├── wiring_diagrams/
├── requirements.txt
└── README.md

```

---

### Notes

- Always verify your sensor connections before powering on.  
- Use `raspi-config` to enable interfaces (I2C, UART, I²S) if needed.  
- To reduce power consumption when off-grid, consider disabling HDMI, Wi-Fi, and other unused interfaces.  
