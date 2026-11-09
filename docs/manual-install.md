# Manual install

Use this if you do not want to run `install.sh`, or to understand what it does. Assumes Raspberry Pi OS Bullseye 32-bit, user `pi`.

## 1. Flash the OS

Raspberry Pi Imager → Raspberry Pi OS (32-bit, Bullseye), set a hostname, enable SSH, add Wi-Fi. Then:

```bash
sudo apt update && sudo apt upgrade -y
```

## 2. Interfaces

Append to `/boot/config.txt`, then run `sudo raspi-config nonint do_i2c 0`:

```
dtparam=i2c_arm=on
dtparam=i2s=on
dtoverlay=googlevoicehat-soundcard
enable_uart=1
```

## 3. Packages

```bash
sudo apt install -y python3-pip python3-numpy python3-scipy python3-smbus python3-serial libsndfile1 alsa-utils i2c-tools
python3 -m pip install tflite-runtime soundfile requests bme680 adafruit-circuitpython-pm25 adafruit-circuitpython-ina219
```

## 4. Microphone

Create `/etc/asound.conf` with the `dmic_hw` and `dmic_sv` devices shown in `install.sh` (section 3/8). Reboot, then test:

```bash
arecord -D dmic_hw -c2 -r 44100 -f S32_LE -d 3 test.wav && aplay test.wav
```

## 5. Files

```bash
mkdir -p ~/environmentsensor/{scripts,quantizedmodels,logs,batterydata}
cp pi/*.py ~/environmentsensor/scripts/
cp models/seas_noise_classifier_v3.tflite ~/environmentsensor/quantizedmodels/
```

## 6. Settings and services

Create `/etc/seas/seas.env`:

```
SEAS_DEVICE_ID=SEAS-4
SEAS_CAL_OFFSET_DB=123.0
```

Create `/etc/systemd/system/seas-env-logger.service` (and the same for `seas-noise-inference` with `noise_inference.py`):

```ini
[Unit]
Description=SEAS environmental logger
After=network-online.target
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/environmentsensor/scripts
EnvironmentFile=/etc/seas/seas.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 /home/pi/environmentsensor/scripts/env_logger.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now seas-env-logger seas-noise-inference
```

## 7. Swap

Set `CONF_SWAPSIZE=512` in `/etc/dphys-swapfile`, then `sudo dphys-swapfile swapoff && sudo dphys-swapfile setup && sudo dphys-swapfile swapon`.

## Connectivity
### WiFi Setup (Recommended for Lab/Test Deployments)
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

### 4G Cellular Setup (For Remote/Field Deployments)

For remote locations without reliable WiFi, use the SIM7600G-H 4G modem.

### Option A: USB-Based Connection
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

### Option B: HAT-Based Connection

Alternatively, you can use the SIM7600G-H 4G HAT B by Waveshare:https://www.waveshare.com/sim7600g-h-4g-hat-b.htm

Product link: SIM7600G-H 4G HAT B (Waveshare)

Simply screw the HAT directly onto the Raspberry Pi GPIO pins.

Connect the micro-USB port of the HAT to the Pi for data and power.

Tested alternative: SIM7600G-H Breakout Module on AliExpress(https://www.aliexpress.com/i/4000078222573.html)

