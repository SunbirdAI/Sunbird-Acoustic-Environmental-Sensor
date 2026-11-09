# Wiring

Pin numbers are physical header pins on the Pi. If you use the SEAS sensor HAT, follow [the schematic](../hardware/seas-sensor-hat-schematic.pdf) instead.

## Microphone (INMP441, I²S)

| Microphone pin | Pi pin |
|---|---|
| VIN (3.3 V) | 3V3 (pin 1) |
| GND | GND (pin 9) |
| SD (Data) | GPIO18 / PCM_CLK (pin 12) |
| WS (LRCLK) | GPIO19 / PCM_FS (pin 35) |
| SCK (BitClk) | GPIO23 / PCM_DIN (pin 16) |

> **Check before relying on this table.** It is carried over from the original manual. The standard mapping for the `googlevoicehat-soundcard` overlay is BCLK = GPIO18 (pin 12), LRCLK = GPIO19 (pin 35), data = GPIO20 (pin 38). Confirm against your hardware.

The microphone is on the **left** channel (L/R pin to GND); the right channel is silent.

## BME680 (I²C)

| Sensor pin | Pi pin |
|---|---|
| VIN | 3V3 (pin 1) |
| GND | GND (pin 6) |
| SDA | SDA1 (pin 3) |
| SCL | SCL1 (pin 5) |

## Battery voltage (INA219, I²C)

On the same I²C bus as the BME680. The scripts expect the Waveshare UPS-style board at address `0x42`.

## PM2.5 sensor (PMS5003, UART, optional)

| Sensor pin | Pi pin |
|---|---|
| VIN (5 V) | 5V (pin 2) |
| GND | GND (pin 14) |
| TX | GPIO15 / UART RX (pin 10) |
| RX | GPIO14 / UART TX (pin 8) |

Without it, air quality comes from the BME680 gas sensor.

## Connectivity

Wi-Fi works out of the box. For field sites a SIM7600G-H 4G modem or HAT can be used; see [manual-install.md](manual-install.md#connectivity).
