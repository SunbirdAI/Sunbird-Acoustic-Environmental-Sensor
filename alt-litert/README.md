# SAES alternative pipeline: `ai-edge-litert` on 64-bit boards

An **alternative** to the original `tflite-runtime` pipeline in the repo root, which is unchanged.
Use this one when you want to run the newer waveform-in / probabilities-out classifiers
(see `urban-noise-classifier`) on a 64-bit Raspberry Pi OS or Orange Pi image.

Status: **works end to end on an Orange Pi Zero 2W (4 GB)**, uploading to the live API. Known gaps are listed below.

## What differs from the original pipeline

| | Original (repo root) | This folder |
|---|---|---|
| Runtime | `tflite-runtime`, 32-bit OK | `ai-edge-litert` (PyPI wheels are **aarch64 only**, Python 3.10-3.14) |
| Model input | audio resampled and fed to a quantised model | raw 16 kHz mono 4 s waveform; features are inside the model |
| Air quality | PMS5003 PM2.5 (ug/m3, higher = worse) | **No PM sensor**: approximate IAQ from BME680 gas + humidity, inverted so higher = worse |
| Power | INA219 via Adafruit libs | INA219 via `smbus2`, UPS HAT (A) at I2C **0x42** |
| Audio | 10 s clips, raw audio uploaded to `/audio/` | **No audio is stored or uploaded** (privacy). Only the class + probability are sent |
| Services | 3 systemd units | 2 units: `saes-sensors`, `saes-inference` |

## Memory: choose the model for your board

Measured with `ai-edge-litert`, 4 s clip:

| Model | Peak RAM | Latency (4 threads) | Fits a 512 MB board? |
|---|---|---|---|
| YAMNet + head (3.4 MB) | ~60 MB | ~130 ms | yes |
| YAMNet + TRILL combined (27 MB) | ~480-515 MB | ~2.6 s | **no** (killed by the OOM killer on a Pi Zero 2 W) |

The `.tflite` files are not in this repo. Put one in `models/` and point `SAES_MODEL` at it.

## Setup

1. 64-bit OS, I2C enabled. Raspberry Pi: `dtparam=i2c_arm=on`. Orange Pi: `overlays=pi-i2c1` in `/boot/orangepiEnv.txt`.
2. `sudo i2cdetect -y <bus>` should show the BME680 (0x76/0x77) and the UPS HAT (0x42). Set `SAES_I2C_BUS` if it is not bus 2.
3. Copy your `.tflite` into `models/` (labels are in `models/labels.json`, 19 classes).
4. `./install.sh`, edit `/etc/default/saes`, then `sudo systemctl enable --now saes-sensors saes-inference`.

Microphone: the default is a USB mic (`plughw:CARD=Device,DEV=0`; override with `SAES_MIC`). A 50 Hz mains hum
was seen on a USB mic; the inference service high-passes at 120 Hz (`SAES_HIGHPASS_HZ`) since the model ignores
everything below ~125 Hz anyway. INMP441 over I2S: works with the `googlevoicehat-soundcard` overlay on a
Raspberry Pi; Orange Pi images ship no I2S overlay, so a custom one is needed.

## API behaviour

Data endpoints are at the API root (`https://noise-api.sunbird.ai/device_metrics/...`, not under `/api/`).
The server rejects `null` fields, so the sensor service skips a post until every field has a value
(`air_quality` needs the BME680 baseline, about 10 minutes after start; a stable baseline takes hours).
Class names are mapped to the dashboard's existing spellings (`regilious-venue`, `boda-boda-motocyle`).
Predictions below `SAES_CONF_MIN` (0.30) are reported as `other`. At most one result per 60 s is posted.

## Known gaps

- `db_level` is dBFS plus a **placeholder offset** (`SAES_DB_OFFSET`). It is not a calibrated sound level.
- UPS shunt resistance is assumed (`SAES_SHUNT_OHMS`, 0.01 ohm). Battery voltage and percent do not depend on it; the current does.
- The IAQ score is an approximation, not Bosch BSEC, and the early baseline is biased while the gas sensor warms up.
- The model has no class for quiet ambience, wind or rain, so quiet rooms come out as low-confidence `other`.
