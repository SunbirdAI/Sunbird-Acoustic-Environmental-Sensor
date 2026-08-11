#!/usr/bin/env bash
# =============================================================================
# Sunbird Acoustic Environmental Sensor (SAES) — Installer
# Target: Raspberry Pi OS Bullseye 32-bit (armv7l, Python 3.9)
# Usage : sudo bash install.sh
# =============================================================================

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
section() { echo -e "\n${YELLOW}━━━━  $*  ━━━━${NC}"; }

# ── Must run as root ──────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || error "Run as root: sudo bash install.sh"

# ── Resolve the real user (the one who called sudo) ──────────────────────────
REAL_USER="${SUDO_USER:-pi}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
info "Installing for user: $REAL_USER (home: $REAL_HOME)"

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_DIR="$REAL_HOME/environmentsensor"
SCRIPTS_DIR="$REPO_DIR/scripts"
MODELS_DIR="$REPO_DIR/quantizedmodels"
LOGS_DIR="$REPO_DIR/logs"
BATTERY_DIR="$REPO_DIR/batterydata"
AUDIO_DIR="$REPO_DIR/rawaudio"
VENV_DIR="$REAL_HOME/envs/sensor-env"

# Bullseye Python is 3.9; confirm
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
[[ "$PY_VER" == "3.9" ]] || warn "Expected Python 3.9 (Bullseye), found $PY_VER — tflite-runtime wheel may differ"

# ── Architecture check ────────────────────────────────────────────────────────
ARCH=$(uname -m)
[[ "$ARCH" == "armv7l" ]] || warn "Expected armv7l (32-bit), found $ARCH"

# =============================================================================
section "1 · System update"
# =============================================================================
apt-get update -y

# =============================================================================
section "2 · System packages"
# =============================================================================
apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    cmake \
    curl \
    wget \
    git \
    alsa-utils \
    portaudio19-dev \
    libatlas-base-dev \
    libjpeg-dev \
    liblapack-dev \
    libopenblas-dev \
    libhdf5-dev \
    i2c-tools \
    libi2c-dev \
    libffi-dev \
    libssl-dev \
    python3-smbus \
    python3-serial \
    libglib2.0-dev \
    udev

info "System packages installed."

# =============================================================================
section "3 · Enable I2C, I2S, UART interfaces"
# =============================================================================
CONFIG=/boot/config.txt

enable_overlay() {
    local line="$1"
    grep -qF "$line" "$CONFIG" || echo "$line" >> "$CONFIG"
}

# I2C
raspi-config nonint do_i2c 0
enable_overlay "dtparam=i2c_arm=on"

# UART (for batterymetricsv2 on /dev/ttyS0 and PM2.5 on USB-UART)
raspi-config nonint do_serial 2          # enable hardware UART, disable login shell on serial
enable_overlay "enable_uart=1"

# I2S for INMP441 microphone
enable_overlay "dtparam=i2s=on"
enable_overlay "dtoverlay=googlevoicehat-soundcard"

info "Interfaces enabled in $CONFIG — reboot required (done at end of install)."

# =============================================================================
section "4 · ALSA config for plug:dmic_sv device alias"
# =============================================================================
# inference.py records via: arecord -D plug:dmic_sv
# This creates the dmic_sv PCM that googlevoicehat exposes, then wraps it
# with the plug layer for rate conversion (44100 → device native).
cat > /etc/asound.conf << 'ALSA_EOF'
# SAES — ALSA configuration
# Mono capture from the I2S MEMS microphone via googlevoicehat-soundcard overlay

pcm.dmic_sv {
    type hw
    card 0
    device 0
    format S32_LE
    rate 44100
    channels 2
}

pcm.!default {
    type asym
    capture.pcm "dmic_capture"
    playback.pcm "null"
}

pcm.dmic_capture {
    type plug
    slave.pcm "dmic_sv"
}

ctl.!default {
    type hw
    card 0
}
ALSA_EOF

info "ALSA config written to /etc/asound.conf"

# =============================================================================
section "5 · Add $REAL_USER to i2c, audio, dialout, gpio groups"
# =============================================================================
for grp in i2c audio dialout gpio spi; do
    getent group "$grp" &>/dev/null && usermod -aG "$grp" "$REAL_USER" && info "Added $REAL_USER to $grp"
done

# =============================================================================
section "6 · Create directory structure"
# =============================================================================
for d in "$SCRIPTS_DIR" "$MODELS_DIR" "$LOGS_DIR" "$BATTERY_DIR" "$AUDIO_DIR"; do
    mkdir -p "$d"
    chown -R "$REAL_USER:$REAL_USER" "$d"
done
info "Directory tree created under $REPO_DIR"

# =============================================================================
section "7 · Python virtual environment"
# =============================================================================
if [[ ! -d "$VENV_DIR" ]]; then
    sudo -u "$REAL_USER" python3 -m venv "$VENV_DIR"
    info "venv created at $VENV_DIR"
else
    info "venv already exists at $VENV_DIR — skipping creation"
fi

VENV_PIP="$VENV_DIR/bin/pip"
VENV_PY="$VENV_DIR/bin/python3"

sudo -u "$REAL_USER" "$VENV_PIP" install --upgrade pip wheel setuptools

# =============================================================================
section "8 · Install tflite-runtime (armv7l Bullseye)"
# =============================================================================
# Google Coral index hosts official armv7l wheels for tflite-runtime on Python 3.9
info "Installing tflite-runtime from Google Coral index..."
sudo -u "$REAL_USER" "$VENV_PIP" install tflite-runtime \
    --extra-index-url https://google-coral.github.io/py-repo/ \
    || error "Failed to install tflite-runtime. Check internet connection."
info "tflite-runtime installed."


# =============================================================================
section "9 · Install Python dependencies"
# =============================================================================
sudo -u "$REAL_USER" "$VENV_PIP" install \
    numpy \
    scipy \
    soundfile \
    requests \
    pyserial \
    bme680 \
    adafruit-circuitpython-pm25 \
    adafruit-circuitpython-ina219 \
    adafruit-blinka \
    RPi.GPIO \
    sysv-ipc

# PyAudio needs portaudio19-dev (installed in step 2) — build from source inside venv
sudo -u "$REAL_USER" "$VENV_PIP" install pyaudio

# soundmeter depends on pyaudio
sudo -u "$REAL_USER" "$VENV_PIP" install soundmeter

info "Python dependencies installed."

# =============================================================================
section "10 · Verify critical imports"
# =============================================================================
sudo -u "$REAL_USER" "$VENV_PY" - << 'PYCHECK'
import sys
errors = []
mods = [
    ("tflite_runtime.interpreter", "tflite-runtime"),
    ("numpy",                       "numpy"),
    ("scipy.signal",                "scipy"),
    ("soundfile",                   "soundfile"),
    ("requests",                    "requests"),
    ("serial",                      "pyserial"),
    ("bme680",                      "bme680"),
    ("adafruit_pm25",               "adafruit-circuitpython-pm25"),
    ("adafruit_ina219",             "adafruit-circuitpython-ina219"),
    ("soundmeter",                  "soundmeter"),
]
for mod, pkg in mods:
    try:
        __import__(mod)
        print(f"  ✓  {pkg}")
    except ImportError as e:
        print(f"  ✗  {pkg}  — {e}")
        errors.append(pkg)
if errors:
    print(f"\nFailed imports: {errors}", file=sys.stderr)
    sys.exit(1)
else:
    print("\nAll imports OK.")
PYCHECK

info "Import verification passed."

# =============================================================================
section "11 · Copy application scripts"
# =============================================================================
# Assumes this installer lives in the repo root beside the .py files.
INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS=( inference.py modifiedlogger.py batterymetricsv2.py metadatalogger.py record-infer-pushtoserver.py )

for s in "${SCRIPTS[@]}"; do
    if [[ -f "$INSTALLER_DIR/$s" ]]; then
        cp "$INSTALLER_DIR/$s" "$SCRIPTS_DIR/$s"
        chown "$REAL_USER:$REAL_USER" "$SCRIPTS_DIR/$s"
        chmod +x "$SCRIPTS_DIR/$s"
        info "Copied $s → $SCRIPTS_DIR/"
    else
        warn "$s not found next to install.sh — copy it manually to $SCRIPTS_DIR/"
    fi
done

# =============================================================================
section "12 · Model placeholder"
# =============================================================================
MODEL_FILE="seas_noise_classifier_v1.tflite"
if [[ -f "$INSTALLER_DIR/quantizedmodels/$MODEL_FILE" ]]; then
    cp "$INSTALLER_DIR/quantizedmodels/$MODEL_FILE" "$MODELS_DIR/$MODEL_FILE"
    chown "$REAL_USER:$REAL_USER" "$MODELS_DIR/$MODEL_FILE"
    info "Copied $MODEL_FILE → $MODELS_DIR/"
elif [[ -f "$INSTALLER_DIR/$MODEL_FILE" ]]; then
    cp "$INSTALLER_DIR/$MODEL_FILE" "$MODELS_DIR/$MODEL_FILE"
    chown "$REAL_USER:$REAL_USER" "$MODELS_DIR/$MODEL_FILE"
    info "Copied $MODEL_FILE → $MODELS_DIR/"
else
    warn "Model not found in repo — copy it manually before starting services:"
    warn "  cp seas_noise_classifier_v1.tflite $MODELS_DIR/"
fi

# =============================================================================
section "13 · systemd services"
# =============================================================================
EXEC_PREFIX="$VENV_DIR/bin/python3"

# Helper to write a service file
write_service() {
    local name="$1" desc="$2" script="$3"
    cat > "/etc/systemd/system/${name}.service" << EOF
[Unit]
Description=${desc}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${REAL_USER}
WorkingDirectory=${SCRIPTS_DIR}
ExecStart=${EXEC_PREFIX} ${SCRIPTS_DIR}/${script}
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
    info "Service file written: /etc/systemd/system/${name}.service"
}

write_service "seas-inference"    "SAES Noise Inference & Upload"          "inference.py"
write_service "seas-envlogger"    "SAES Environmental Data Logger"         "modifiedlogger.py"
write_service "seas-batterydata"  "SAES Battery & GPS Telemetry"           "batterymetricsv2.py"

systemctl daemon-reload

for svc in seas-inference seas-envlogger seas-batterydata; do
    systemctl enable "$svc"
    info "Enabled $svc (will start on next boot)"
done

# =============================================================================
section "14 · soundmeter PATH for systemd"
# =============================================================================
# inference.py calls soundmeter via absolute path /home/pi/.local/bin/soundmeter
# which won't exist inside the venv. Create a symlink into the venv bin dir.
SOUNDMETER_BIN="$VENV_DIR/bin/soundmeter"
if [[ -f "$SOUNDMETER_BIN" ]]; then
    # Also create the legacy path inference.py hard-codes
    mkdir -p "$REAL_HOME/.local/bin"
    ln -sf "$SOUNDMETER_BIN" "$REAL_HOME/.local/bin/soundmeter" \
        && chown -h "$REAL_USER:$REAL_USER" "$REAL_HOME/.local/bin/soundmeter"
    info "Symlinked soundmeter → $REAL_HOME/.local/bin/soundmeter"
fi

# =============================================================================
section "15 · Convenience alias (activate venv)"
# =============================================================================
BASHRC="$REAL_HOME/.bashrc"
if ! grep -q "sensor-env" "$BASHRC" 2>/dev/null; then
    echo "" >> "$BASHRC"
    echo "# SAES sensor venv" >> "$BASHRC"
    echo "alias seas='source $VENV_DIR/bin/activate'" >> "$BASHRC"
    chown "$REAL_USER:$REAL_USER" "$BASHRC"
    info "Added 'seas' alias to $BASHRC (run 'seas' to activate venv)"
fi

# =============================================================================
section "Done — summary"
# =============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          SAES Installation Complete                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Model: if not in repo, copy it manually:"
echo "       cp seas_noise_classifier_v1.tflite $MODELS_DIR/"
echo ""
echo "  2. Reboot (required for I2S + UART overlays to load):"
echo "       sudo reboot"
echo ""
echo "  3. After reboot, test the microphone:"
echo "       arecord -D plug:dmic_sv -c2 -r 44100 -f S32_LE -d 3 test.wav"
echo "       aplay test.wav"
echo ""
echo "  4. Start services manually to verify before relying on autostart:"
echo "       sudo systemctl start seas-inference"
echo "       sudo systemctl start seas-envlogger"
echo "       sudo systemctl start seas-batterydata"
echo ""
echo "  5. Check logs:"
echo "       journalctl -u seas-inference -f"
echo "       journalctl -u seas-envlogger -f"
echo "       journalctl -u seas-batterydata -f"
echo ""
echo "  6. Update DEVICE_ID in scripts if deploying multiple nodes:"
echo "       $SCRIPTS_DIR/inference.py      (DEVICE_ID = \"SEAS-1\")"
echo "       $SCRIPTS_DIR/modifiedlogger.py (device = \"SEAS-1\")"
echo ""
warn "A reboot is required for I2S and UART overlays to take effect."
echo ""
