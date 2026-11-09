# Data format

Base URL: `https://noise-api.sunbird.ai` (docs: `/api/docs/`). Both calls are `POST` with a JSON body, once a minute.

## `/device_metrics/environmental-parameters/`

```json
{"device": "SEAS-2", "temperature": 30.6, "pressure": 869.9, "humidity": 53.0,
 "air_quality": 94.6, "ram_value": 215, "system_temperature": 52.1,
 "power_usage": 8.236, "db_level": 53.25}
```

| Field | Meaning |
|---|---|
| `temperature` °C, `pressure` hPa, `humidity` % | BME680 |
| `air_quality` | PM2.5 if a PMS5003 is attached, otherwise a 0-100 BME680 gas index (100 = cleanest). The baseline is re-measured over 30 s at each service start. |
| `ram_value` | available RAM, MB |
| `system_temperature` | CPU temperature, °C |
| `power_usage` | battery **voltage** (V), kept as is for now |
| `db_level` | dB(A), see [calibration](calibration.md) |

## `/device_metrics/sound-inference-data/`

```json
{"device": "SEAS-2", "inference_probability": 0.40, "inference_class": "car-alarm",
 "inferred_audio_name": "56.wav"}
```

`inference_class` is one of: animal, bar-restaurant-nightclub, boda-boda-motorcycle, car-alarm, car-or-truck, community-radio, construction-site, crowd-noise, fabrication-workshop, generator, hawker-vendor, herbalists, mobile-music, motorvehicle-horn, motorvehicle-siren, other, religious-venue, school, street-preacher.

`inferred_audio_name` is only a counter-based label. The audio itself is deleted right after classification and never uploaded.
