Sunbird Acoustic Environmental Sensor (SAES) — Setup Manual
This manual guides you through setting up a Raspberry Pi–based acoustic environmental sensor using:
MEMS microphone (INMP411) for acoustic data


BME680 for temperature, humidity, pressure, and gas readings


Plantower PMSA003I PM2.5 sensor


TensorFlow Lite for on-device edge inference


By the end, your Raspberry Pi will collect environmental and acoustic data, process it on the edge using machine learning, and upload results for further analysis.

Table of Contents
Prerequisites


Install Raspberry Pi OS


Enable I²S for MEMS Microphone


Wiring Diagrams


Install Required Libraries


TensorFlow Lite Setup


Running and Testing the Microphone


Setup as a systemd Service


Setup as a Cron Job (Optional)


File Structure (Recommended Repo Organization)



1. Prerequisites
Hardware:
Raspberry Pi Zero 2W, Pi 4, or Pi 3B+/3A+


16 GB (or larger) microSD card


5 V / ≥3 A USB power supply


INMP411 MEMS microphone (I²S)


BME680 environmental sensor (I²C)


Plantower PMSA003I PM2.5 sensor (UART/I²C)


SIM7600E/SIM7600G-H module for LTE connectivity (optional)


Jumper wires, breadboard or soldered headers


Internet connection (for setup)



2. Install Raspberry Pi OS
Download Raspberry Pi OS (32-bit lite or desktop)
 👉 https://www.raspberrypi.com/software/


Flash microSD using Raspberry Pi Imager or balenaEtcher.


Insert microSD, boot, and complete initial setup.


Update and upgrade:


sudo apt update && sudo apt upgrade -y
sudo reboot


3. Enable I²S for MEMS Microphone
The INMP411 uses I²S bus. Enable it as follows:
sudo nano /boot/config.txt

At the end, add:
dtparam=i2s=on
dtoverlay=googlevoicehat-soundcard

Note: The googlevoicehat-soundcard overlay works with most I²S MEMS microphones.
Reboot:
sudo reboot


4. Wiring Diagrams
4.1 MEMS Microphone (INMP411)
Microphone Pin
Pi Pin
VIN (3.3 V)
3V3 (Pin 1)
GND
GND (Pin 9)
SD (Data)
GPIO18 / PCM_CLK (Pin 12)
WS (LRCLK)
GPIO19 / PCM_FS (Pin 35)
SCK (BitClk)
GPIO23 / PCM_DIN (Pin 16)

4.2 BME680 (I²C)
Sensor Pin
Pi Pin
VIN (3–5V)
3V3 (Pin 1)
GND
GND (Pin 6)
SDA
SDA1 (Pin 3)
SCL
SCL1 (Pin 5)

4.3 PMSA003I PM2.5 Sensor (UART)
Sensor Pin
Pi Pin
VIN (5 V)
5V (Pin 2)
GND
GND (Pin 14)
TX
GPIO15 (UART RX, Pin 10)
RX
GPIO14 (UART TX, Pin 8)


5. Install Required Libraries
First, set up a virtual environment for clean dependency management:
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


6. TensorFlow Lite Setup
You will use TensorFlow Lite for edge inference. Simplest method:
# Install dependencies
sudo apt install libatlas-base-dev libjpeg-dev liblapack-dev -y

# Install tflite-runtime
pip install tflite-runtime

Verify TensorFlow Lite:
import tflite_runtime.interpreter as tflite
print("TFLite runtime ready")

For detailed builds, see QEngineering guide

7. I²S MEMS Microphone Test
Record audio:
arecord --format=S32_LE --rate=16000 --channels=2 test.wav

Playback:
aplay test.wav


8. Setup as a Systemd Service
Create a systemd service to run your sensor logger on boot:
sudo nano /etc/systemd/system/logdata.service

Paste:
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

Reload and enable service:
sudo systemctl daemon-reload
sudo systemctl enable logdata.service
sudo systemctl start logdata.service

Check status:
sudo systemctl status logdata.service

Live logs:
journalctl -u logdata.service -f


9. Setup as a Cron Job (Optional)
If you prefer to schedule inference periodically:
crontab -e

Add:
*/5 * * * * /home/pi/environmentsensor/scripts/record-infer-noise-upload.py >> /home/pi/environmentsensor/logs/record-infer.log 2>&1

Verify:
crontab -l


10. Recommended Repo Structure
For your GitHub repo:
Sunbird-Acoustic-Env-Sensor/
│
├── environmentsensor/
│   └── scripts/
│       ├── modifiedlogger.py
│       ├── record-infer-noise-upload.py
│       └── inference_model.tflite
│
├── logs/
├── README.md  <-- (this file)
├── wiring_diagrams/
└── requirements.txt


Notes
Always verify your sensor connections before powering.


Use raspi-config to enable interfaces (I2C, UART, I2S if necessary).


Disable HDMI, Wi-Fi, and other interfaces to reduce power if running off-grid.




