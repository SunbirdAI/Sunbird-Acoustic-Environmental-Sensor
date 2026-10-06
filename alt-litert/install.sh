#!/usr/bin/env bash
# Installs the ai-edge-litert alternative pipeline as two systemd services.
# Run from this folder as your normal user (it uses sudo only for system files).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"; USER_NAME="$(id -un)"

[ "$(uname -m)" = "aarch64" ] || { echo "ai-edge-litert needs a 64-bit OS (aarch64); found $(uname -m)"; exit 1; }
ls "$DIR"/models/*.tflite >/dev/null 2>&1 || { echo "Put your .tflite model in $DIR/models/ first (see README)"; exit 1; }

sudo apt-get install -y python3-venv i2c-tools alsa-utils
sudo usermod -aG i2c,audio "$USER_NAME"
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --upgrade pip
"$DIR/venv/bin/pip" install ai-edge-litert numpy requests smbus2 bme680

[ -f /etc/default/saes ] || sudo tee /etc/default/saes >/dev/null <<CFG
# Per-device settings, read by both services
SAES_DEVICE_ID=SEAS-X
SAES_MODEL=$DIR/models/noise_classifier_combined_noflex.tflite
# dBFS -> reported db_level. Uncalibrated placeholder; remove the line to stop reporting db_level.
SAES_DB_OFFSET=100
# SAES_UPLOAD=0   # uncomment to run without posting to the API
CFG
for s in sensors inference; do
  sed "s#@USER@#$USER_NAME#g; s#@DIR@#$DIR#g" "$DIR/saes-$s.service.in" | sudo tee /etc/systemd/system/saes-$s.service >/dev/null
done
sudo systemctl daemon-reload
echo "Edit /etc/default/saes (set SAES_DEVICE_ID and SAES_MODEL), log out/in for group changes, then:"
echo "  sudo systemctl enable --now saes-sensors saes-inference"
