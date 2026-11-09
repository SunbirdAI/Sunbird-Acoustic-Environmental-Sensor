# Troubleshooting

Start with `seas-status`.

| Symptom | Check / fix |
|---|---|
| Service not active | `journalctl -u seas-env-logger -n 50`; the installer enables restart on failure, so repeated failures show up there. |
| No `201` in the logs | No internet or API unreachable: `curl -I https://noise-api.sunbird.ai`. |
| `arecord: no soundcards` | I²S overlay not loaded: check `/boot/config.txt`, wiring, reboot. |
| Microphone busy | The two services share the mic through `/tmp/seas-mic.lock`; stop any manual `arecord` first. |
| Out of memory / very slow | `free -m` should show 512 MB swap; the classifier needs about 200 MB. Re-run `install.sh` to fix swap. |
| Air quality dropped after a restart | The gas baseline is re-measured at each start; give it a few minutes. |
| `db_level` looks too high or low | Calibrate: [calibration.md](calibration.md). |
| BME680 / INA219 not found | `sudo i2cdetect -y 1` should list `0x76`/`0x77` (BME680) and `0x42` (INA219). |

Roll back to an earlier model: copy it from `models/archive/` to `/home/pi/environmentsensor/quantizedmodels/` and change `MODEL_PATH` in `noise_inference.py`.
