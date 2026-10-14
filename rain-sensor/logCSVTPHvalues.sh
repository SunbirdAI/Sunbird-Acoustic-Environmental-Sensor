#!/bin/bash

log_dir="/home/pi/WeatherStationResources/TPH Data"
log_file="$log_dir/sensor_data_$(date +'%Y-%m-%d').csv"

# Create the log directory if it doesn't exist
mkdir -p "$log_dir"

# Create a new log file if it's a new day
if [ ! -f "$log_file" ]; then
    echo "timestamp,temperature(C),pressure(hPa),humidity(%RH)" > "$log_file"
fi

# Function to log sensor data
log_sensor_data() {
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    echo "$timestamp,$1" >> "$log_file"
}

echo "Polling:"
while true; do
    output=$(python3 - <<END
import bme680

try:
    sensor = bme680.BME680(bme680.I2C_ADDR_PRIMARY)
except (RuntimeError, IOError):
    sensor = bme680.BME680(bme680.I2C_ADDR_SECONDARY)

sensor.set_humidity_oversample(bme680.OS_2X)
sensor.set_pressure_oversample(bme680.OS_4X)
sensor.set_temperature_oversample(bme680.OS_8X)
sensor.set_filter(bme680.FILTER_SIZE_3)

if sensor.get_sensor_data():
    output = '{0:.2f},{1:.2f},{2:.2f}'.format(
        sensor.data.temperature,
        sensor.data.pressure,
        sensor.data.humidity)
    print(output)
END
)

    log_sensor_data "$output"
    echo "$output"
    sleep 30  # Poll every 30 seconds
done
