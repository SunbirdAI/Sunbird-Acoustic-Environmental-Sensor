# Sunbird Acoustic Environmental Sensor (SAES)Setup Manual

This manual guides you through setting up a Raspberry Pi–based acoustic sensor system using:

* MEMS microphone (INMP411)
* BME680 environmental sensor (I²C)
* Plant-tower PM2.5 sensor (UART/I²C)
* TensorFlow Lite on the edge for inference

At the end, you can publish this in a GitHub repository.

---

## 1. Prerequisites

* Raspberry Zero 2W, Pi 4 (or 3B+/3A+) with microSD card slot
* 16 GB (or larger) microSD card
* USB power supply (5 V, ≥3 A)
* MEMS microphone breakout (INMP411)
* BME680 breakout (I²C)
* Plant-tower PM2.5 breakout (UART/I²C) from Adafruit
* Jumper wires, breadboard or soldered headers
* Internet connection for setup
* sim7600e/sim7600g-h for LTE  connection

## 2. Install Raspbian OS

1. Download Raspberry Pi OS (32-bit, lite or desktop) from the [official site](https://www.raspberrypi.com/software/).
2. Use Raspberry Pi Imager or balenaEtcher to write the image to the microSD.
3. Insert microSD, power on, and follow on-screen prompts.
4. Update & upgrade packages:

   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo reboot
   ```

## 3. Enable I²S for MEMS Microphone

The INMP411 uses the I²S bus.

1. Open config:

   ```bash
   sudo nano /boot/config.txt
   ```
2. Add at the end:

   ```ini
   dtparam=i2s=on
   dtoverlay=googlevoicehat-soundcard
   ```

   > *Note: `googlevoicehat-soundcard` overlay works with many I²S MEMS mics.*
3. Save and reboot:

   ```bash
   sudo reboot
   ```

## 4. Wiring Diagrams

### 4.1 MEMS Microphone (INMP411)

| Microphone Pin | Pi Pin                     |
| -------------- | -------------------------- |
| VIN (3.3 V)    | 3V3 (Pin 1)                |
| GND            | GND (Pin 9)                |
| SD (Data)      | GPIO18 / PCM\_CLK (Pin 12) |
| WS (LRCLK)     | GPIO19 / PCM\_FS  (Pin 35) |
| SCK (BitClk)   | GPIO23 / PCM\_DIN (Pin 16) |

### 4.2 BME680 (I²C)

| Sensor Pin | Pi Pin       |
| ---------- | ------------ |
| VIN (3–5V) | 3V3 (Pin 1)  |
| GND        | GND (Pin 6)  |
| SDA        | SDA1 (Pin 3) |
| SCL        | SCL1 (Pin 5) |

### 4.3 PMSA003I PM2.5 Sensor (UART)

| Sensor Pin | Pi Pin                   |
| ---------- | ------------------------ |
| VIN (5 V)  | 5V (Pin 2)               |
| GND        | GND (Pin 14)             |
| TX         | GPIO15 (UART RX, Pin 10) |
| RX         | GPIO14 (UART TX, Pin 8)  |

## 5. Install Required Libraries

We'll create a single virtual environment and install all required packages at once.

```bash
# Install Python venv support
sudo apt install python3-pip python3-venv -y

# Create and activate the virtual environment
python3 -m venv ~/envs/sensor-env
source ~/envs/sensor-env/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install all sensor and ML libraries in one go
pip install bme680 adafruit-circuitpython-pmsa003i sounddevice numpy pyserial tflite-runtime

# Install I²S tools for microphone testing
sudo apt install i2s-tools -y
```

### 5.1 I²S MEMS Microphone Test

```bash
arecord --format=S32_LE --rate=16000 --channels=2 test.wav
aplay test.wav
```

## 6. TensorFlow Lite Setup

TensorFlow Lite Setup

Follow Qengineering’s guide:
[https://qengineering.eu/install-tensorflow-2-lite-on-raspberry-pi-4.html](https://qengineering.eu/install-tensorflow-2-lite-on-raspberry-pi-4.html)

Key steps summary:

1. Install dependencies:

   ```bash
   sudo apt install libatlas-base-dev libjpeg-dev liblapack-dev -y
   pip install tflite-runtime
   ```
2. Verify installation:

   ```python
   import tflite_runtime.interpreter as tflite
   print("TFLite runtime ready")
   ```

Here are the two sections in Markdown form—just copy & paste them into your README:

## 8. Setup as a Systemd Service

To ensure your logging script runs on boot and restarts if it crashes, create a systemd service:

1. **Create the service file**  
   ```bash
   sudo nano /etc/systemd/system/logdata.service
````

2. **Paste the following contents**:

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
3. **Save and exit** (`Ctrl+O`, `Enter`, `Ctrl+X`).
4. **Reload systemd** to pick up the new unit:

   ```bash
   sudo systemctl daemon-reload
   ```
5. **Enable and start the service**:

   ```bash
   sudo systemctl enable logdata.service
   sudo systemctl start logdata.service
   ```
6. **Verify it's running**:

   ```bash
   sudo systemctl status logdata.service
   ```
7. **View live logs**:

   ```bash
   journalctl -u logdata.service -f
   ```

## 9. Setup as a Cron Job

If you prefer running the inference script on a schedule (e.g., every 5 minutes), use cron:

1. **Edit the crontab** for the `pi` user:

   ```bash
   crontab -e
   ```
2. **Add this line** to run the script every 5 minutes and append output to your log:

   ```cron
   */5 * * * * /home/pi/environmentsensor/scripts/record-infer-noise-upload.py >> /home/pi/environmentsensor/logs/record-infer.log 2>&1
   ```
3. **Save and exit** (`Ctrl+O`, `Enter`, `Ctrl+X`).
4. **Verify your crontab entries**:

   ```bash
   crontab -l
   ```

```
```
````markdown
