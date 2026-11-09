# Calibration

The reported `db_level` is `LAeq(dBFS) + SEAS_CAL_OFFSET_DB`, where LAeq is the A-weighted, energy-averaged level over about 5 s of the raw microphone signal.

The default offset, **123 dB**, is provisional. It is computed from the INMP441 datasheet (-26 dBFS at 94 dB SPL). Real units differ by a few dB (enclosure, mounting, microphone tolerance), so values are plausible but **not yet traceable**.

## Calibrate a unit

1. Place a Class 1/2 acoustic calibrator (94 or 114 dB at 1 kHz) over the microphone, or run the unit next to a reference meter (for example a Casella CEL-63x) for an hour.
2. Read the unit's value: `journalctl -u seas-env-logger | grep "Noise level"`.
3. New offset = old offset + (reference level − unit level).
4. Put it in `/etc/seas/seas.env` and restart `seas-env-logger`.

The same method, with results from the Gen-2 sensor, is documented in [urban-noise-sensor/docs/sensor-calibration.md](https://github.com/SunbirdAI/urban-noise-sensor/blob/main/docs/sensor-calibration.md).
