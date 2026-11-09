# Sunbird Environmental Acoustic Sensor (SEAS)

A low-cost sensor node on a Raspberry Pi Zero 2 W that measures **noise level (dB(A))**, **recognises the type of noise on the device**, and records **temperature, humidity, pressure, air quality and power**. Everything is uploaded to the Sunbird noise API. **No audio ever leaves the device.**

| Measured | How | Rate |
|---|---|---|
| Noise level, dB(A) | I²S MEMS mic (INMP441), A-weighted LAeq | every 60 s |
| Noise type (19 classes, e.g. boda-boda, generator, crowd) | YAMNet + TRILL model, runs on the Pi | every 60 s |
| Temperature, humidity, pressure, gas / air quality | BME680 (optional PMS5003 for PM2.5) | every 60 s |
| Battery voltage, RAM, CPU temperature | INA219, system | every 60 s |

> Looking for the Arduino Mega / GSM Gen-2 sensor? That is a different design: [SunbirdAI/urban-noise-sensor](https://github.com/SunbirdAI/urban-noise-sensor). Both report to the same API.

## Install (one command)

On a Pi running Raspberry Pi OS Bullseye 32-bit, logged in as `pi`, with internet and the hardware wired ([wiring](docs/wiring.md)):

```bash
curl -fsSL https://raw.githubusercontent.com/SunbirdAI/seas/main/install.sh | sudo bash -s -- --device-id SEAS-4
```

Use your own unit's name for `--device-id`. It finishes by offering to reboot. It:

1. installs the system and Python packages (TFLite, BME680, INA219 …);
2. enables I²C / I²S / UART and configures the microphone;
3. copies the scripts and the model to `/home/pi/environmentsensor/`;
4. sets 512 MB of swap (the model needs about 200 MB of RAM);
5. installs and starts two services that restart on failure and start at boot.

It is safe to run again to update a unit. Add `--with-battery` to also enable the (experimental) battery monitor service, or `--reboot` to skip the prompt.

Prefer to do it by hand, or something failed? See [docs/manual-install.md](docs/manual-install.md).

## Check that it works

```bash
seas-status                                      # services, last uploads, memory, temperature
journalctl -u seas-env-logger -u seas-noise-inference -f   # live logs
```

You should see `201` after each upload, one environmental and one classification per minute.

## Services and settings

| Service | Script | Sends |
|---|---|---|
| `seas-env-logger` | [pi/env_logger.py](pi/env_logger.py) | temperature, humidity, pressure, air quality, RAM, CPU temperature, battery voltage, dB(A) |
| `seas-noise-inference` | [pi/noise_inference.py](pi/noise_inference.py) | predicted noise class + probability |
| `seas-battery-monitor` | [pi/battery_monitor.py](pi/battery_monitor.py) | optional, off by default |

Per-device settings (device ID, calibration offset) live in `/etc/seas/seas.env`. After editing: `sudo systemctl restart seas-env-logger seas-noise-inference`.

## Documentation

- [Wiring](docs/wiring.md) · [Manual install](docs/manual-install.md) · [Calibration](docs/calibration.md) · [Data format and API](docs/data-format.md) · [Troubleshooting](docs/troubleshooting.md)

## Repository layout

```
install.sh        one-command installer
pi/               scripts that run on the sensor
models/           noise classifier (v3 = YAMNet + TRILL); older versions in models/archive/
hardware/         PCB, schematic, enclosure
docs/             guides
rain-sensor/      rain detection from audio (separate pipeline)
legacy/           earlier scripts, kept for reference
```

## Known limitations

- The dB(A) value uses a **provisional** calibration offset (from the microphone datasheet) until each unit is calibrated. See [docs/calibration.md](docs/calibration.md).
- `power_usage` is currently the battery **voltage**, not watts.
- Model accuracy is about 67 % on the test set; confidence is low in quiet places.

## License

Different parts use different licenses, as is usual for open hardware.

| What | Where | License | File |
|---|---|---|---|
| Firmware and scripts | `pi/`, `install.sh`, `rain-sensor/` | GNU GPL v3.0 | [LICENSE](LICENSE) |
| Hardware design files (PCB, schematic, enclosure) | `hardware/` | CERN-OHL-W-2.0 | [LICENSE-HARDWARE](LICENSE-HARDWARE) |
| Documentation and trained models | `README.md`, `docs/`, `models/`, `rain-sensor/*.tflite` | CC BY 4.0 | [LICENSE-DOCS](LICENSE-DOCS) |

Copyright (c) Sunbird AI Ltd.
