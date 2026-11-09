#!/usr/bin/env bash
# =============================================================================
# Sunbird Acoustic Environmental Sensor (SEAS) - one-command installer
#
# Target : Raspberry Pi Zero 2 W / Pi 3 / Pi 4, Raspberry Pi OS Bullseye
#          32-bit (Python 3.9), logged in as the default user "pi".
#
# Usage  : sudo bash install.sh --device-id SEAS-4
#   or   : curl -fsSL https://raw.githubusercontent.com/SunbirdAI/Sunbird-Acoustic-Environmental-Sensor/main/install.sh \
#            | sudo bash -s -- --device-id SEAS-4
#
# Options:
#   --device-id ID   Name this unit reports to the API (e.g. SEAS-4). Asked for if omitted.
#   --with-battery   Also enable the battery monitor service (off by default, see docs).
#   --reboot         Reboot automatically at the end (otherwise you are asked).
#   -h, --help       Show this help.
#
# Safe to re-run: it updates scripts/model/services and leaves your data alone.
# =============================================================================

set -euo pipefail

REPO_URL="https://github.com/SunbirdAI/Sunbird-Acoustic-Environmental-Sensor"
DEVICE_ID="${DEVICE_ID:-}"
WITH_BATTERY=0
AUTO_REBOOT=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --device-id)    DEVICE_ID="${2:-}"; shift 2 ;;
        --with-battery) WITH_BATTERY=1; shift ;;
        --reboot)       AUTO_REBOOT=1; shift ;;
        -h|--help)      sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1 (try --help)" >&2; exit 1 ;;
    esac
done

# -- Output helpers -----------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[FAIL]${NC} $*" >&2; exit 1; }
section() { echo -e "\n${YELLOW}== $* ==${NC}"; }

# -- Pre-flight ---------------------------------------------------------------
[[ $EUID -eq 0 ]] || error "Run with sudo:  sudo bash install.sh --device-id SEAS-4"

REAL_USER="${SUDO_USER:-pi}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
[[ "$REAL_HOME" == "/home/pi" ]] || error "The scripts expect to live in /home/pi (found $REAL_HOME). Log in as user 'pi'."

if [[ -z "$DEVICE_ID" ]]; then
    if [[ -r /dev/tty ]]; then
        read -r -p "Device ID for this unit (e.g. SEAS-4): " DEVICE_ID < /dev/tty
    fi
fi
[[ "$DEVICE_ID" =~ ^[A-Za-z0-9_-]+$ ]] || error "Give a device ID such as SEAS-4:  --device-id SEAS-4"

[[ "$(uname -m)" == "armv7l" ]] || warn "Expected 32-bit ARM (armv7l), found $(uname -m); the tflite-runtime wheel may not exist."
PY_VER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
[[ "$PY_VER" == "3.9" ]] || warn "Expected Python 3.9 (Bullseye), found $PY_VER."
curl -fsS --max-time 10 -o /dev/null https://noise-api.sunbird.ai/ || warn "Cannot reach noise-api.sunbird.ai (no internet?). Install continues; uploads will fail until it is reachable."

BASE="$REAL_HOME/environmentsensor"
SCRIPTS_DIR="$BASE/scripts"
MODELS_DIR="$BASE/quantizedmodels"
MODEL_FILE="seas_noise_classifier_v3.tflite"
info "Installing as '$REAL_USER' for device '$DEVICE_ID' into $BASE"

# -- Find the repo files (next to this script, or download them) ---------------
SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [[ ! -f "$SRC/pi/noise_inference.py" ]]; then
    section "Downloading the repository"
    apt-get install -y git >/dev/null
    SRC="$(mktemp -d)"
    git clone --depth 1 "$REPO_URL" "$SRC"
fi
[[ -f "$SRC/models/$MODEL_FILE" ]] || error "Model $MODEL_FILE not found in $SRC/models"

# =============================================================================
section "1/8  System packages"
# =============================================================================
apt-get update -y
apt-get install -y \
    python3-pip python3-numpy python3-scipy python3-smbus python3-serial \
    libsndfile1 alsa-utils i2c-tools git curl

# =============================================================================
section "2/8  Python packages"
# =============================================================================
# Raspberry Pi OS points pip at piwheels, which has prebuilt 32-bit ARM wheels.
python3 -m pip install --no-input --upgrade \
    tflite-runtime soundfile requests bme680 \
    adafruit-circuitpython-pm25 adafruit-circuitpython-ina219

python3 - <<'PYCHECK'
import sys
mods = ["tflite_runtime.interpreter", "numpy", "scipy.signal", "soundfile",
        "requests", "serial", "smbus", "bme680", "adafruit_pm25.uart"]
bad = []
for m in mods:
    try:
        __import__(m); print("   ok   ", m)
    except Exception as e:
        print("   MISSING", m, "-", e); bad.append(m)
sys.exit(1 if bad else 0)
PYCHECK
info "Python packages ready."

# =============================================================================
section "3/8  Sensors and microphone (I2C, UART, I2S)"
# =============================================================================
CONFIG=/boot/config.txt
[[ -f /boot/firmware/config.txt ]] && CONFIG=/boot/firmware/config.txt
CONFIG_BEFORE=$(md5sum "$CONFIG")

add_line() { grep -qxF "$1" "$CONFIG" || echo "$1" >> "$CONFIG"; }
add_line "dtparam=i2c_arm=on"
add_line "dtparam=i2s=on"
add_line "dtoverlay=googlevoicehat-soundcard"
add_line "enable_uart=1"
raspi-config nonint do_i2c 0 || warn "Could not enable I2C through raspi-config."
for g in i2c audio dialout gpio spi; do
    getent group "$g" >/dev/null && usermod -aG "$g" "$REAL_USER"
done
NEED_REBOOT=0
[[ "$CONFIG_BEFORE" == "$(md5sum "$CONFIG")" ]] || NEED_REBOOT=1

# ALSA: dmic_hw (raw mic, used for dB(A)) and dmic_sv (mic with software gain, used by the classifier).
if grep -q "dmic_sv" /etc/asound.conf 2>/dev/null; then
    info "/etc/asound.conf already defines dmic_sv - left untouched."
else
    [[ -f /etc/asound.conf ]] && cp /etc/asound.conf "/etc/asound.conf.bak-$(date +%Y%m%d)"
    cat > /etc/asound.conf <<'ALSA'
# SEAS: I2S MEMS microphone (googlevoicehat overlay)
pcm.dmic_hw {
    type hw
    card sndrpigooglevoicehat
    channels 2
    format S32_LE
}
pcm.dmic_sv {
    type softvol
    slave.pcm dmic_hw
    control {
        name "Boost Capture Volume"
        card sndrpigooglevoicehat
    }
    min_dB -3.0
    max_dB 30.0
}
ALSA
    info "Wrote /etc/asound.conf (dmic_hw, dmic_sv)."
fi

# =============================================================================
section "4/8  Files"
# =============================================================================
install -d -o "$REAL_USER" -g "$REAL_USER" "$SCRIPTS_DIR" "$MODELS_DIR" "$BASE/logs" "$BASE/batterydata"
for f in noise_inference.py env_logger.py battery_monitor.py; do
    install -m 755 -o "$REAL_USER" -g "$REAL_USER" "$SRC/pi/$f" "$SCRIPTS_DIR/$f"
done
install -m 644 -o "$REAL_USER" -g "$REAL_USER" "$SRC/models/$MODEL_FILE" "$MODELS_DIR/$MODEL_FILE"
info "Scripts -> $SCRIPTS_DIR,  model -> $MODELS_DIR/$MODEL_FILE"

# One small config file holds the per-device settings (edit it, then restart the services).
install -d /etc/seas
if [[ -f /etc/seas/seas.env ]]; then
    sed -i "s/^SEAS_DEVICE_ID=.*/SEAS_DEVICE_ID=${DEVICE_ID}/" /etc/seas/seas.env
else
    cat > /etc/seas/seas.env <<EOF
# Per-device settings for the SEAS services. After editing:  sudo systemctl restart seas-env-logger seas-noise-inference
SEAS_DEVICE_ID=${DEVICE_ID}
# Microphone calibration: SPL = LAeq(dBFS) + this offset. 123 is PROVISIONAL (INMP441 datasheet).
# Replace it with a value measured against a calibrator or reference meter, see docs/calibration.md.
SEAS_CAL_OFFSET_DB=123.0
EOF
fi

# =============================================================================
section "5/8  Memory (512 MB swap)"
# =============================================================================
if [[ -f /etc/dphys-swapfile ]]; then
    CUR=$(awk -F= '/^CONF_SWAPSIZE/ {print $2}' /etc/dphys-swapfile)
    if [[ "${CUR:-0}" -lt 512 ]]; then
        cp /etc/dphys-swapfile "/etc/dphys-swapfile.bak-$(date +%Y%m%d)"
        sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=512/' /etc/dphys-swapfile
        dphys-swapfile swapoff || true
        dphys-swapfile setup
        dphys-swapfile swapon
    fi
    echo "vm.swappiness=20" > /etc/sysctl.d/99-swappiness.conf
    sysctl -q -p /etc/sysctl.d/99-swappiness.conf || true
    info "Swap: $(free -m | awk '/Swap/ {print $2}') MB"
else
    warn "dphys-swapfile not found; swap not changed."
fi

# =============================================================================
section "6/8  Services"
# =============================================================================
write_service() {   # name, description, script
    cat > "/etc/systemd/system/$1.service" <<EOF
[Unit]
Description=$2
After=network-online.target
Wants=network-online.target

[Service]
User=$REAL_USER
WorkingDirectory=$SCRIPTS_DIR
EnvironmentFile=/etc/seas/seas.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 $SCRIPTS_DIR/$3
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
}
write_service seas-env-logger      "SEAS environmental logger (BME680, power, dB(A))" env_logger.py
write_service seas-noise-inference "SEAS noise classifier (on-device, no audio uploaded)" noise_inference.py
SERVICES=(seas-env-logger seas-noise-inference)
if [[ $WITH_BATTERY -eq 1 ]]; then
    write_service seas-battery-monitor "SEAS battery monitor" battery_monitor.py
    SERVICES+=(seas-battery-monitor)
fi
systemctl daemon-reload
systemctl enable "${SERVICES[@]}"
info "Enabled: ${SERVICES[*]}"

cat > /usr/local/bin/seas-status <<'EOF'
#!/usr/bin/env bash
# Quick health check for a SEAS unit.
echo "Device : $(grep -h '^SEAS_DEVICE_ID' /etc/seas/seas.env | cut -d= -f2)"
for s in seas-env-logger seas-noise-inference seas-battery-monitor; do
    systemctl list-unit-files "$s.service" >/dev/null 2>&1 && printf '%-22s %s\n' "$s" "$(systemctl is-active $s)"
done
echo; echo "Last uploads:"
journalctl -u seas-env-logger -u seas-noise-inference -n 400 --no-pager 2>/dev/null \
    | grep -E 'Noise level|Inferred class|upload code|POST .* 20[01]' | tail -6
echo; free -m | head -2; vcgencmd measure_temp
EOF
chmod +x /usr/local/bin/seas-status

# =============================================================================
section "7/8  Start"
# =============================================================================
if arecord -l 2>/dev/null | grep -qi googlevoicehat && [[ $NEED_REBOOT -eq 0 ]]; then
    systemctl restart "${SERVICES[@]}"
    info "Microphone present: services started."
else
    warn "Microphone/interfaces become available after a reboot; services start automatically then."
    NEED_REBOOT=1
fi

# =============================================================================
section "8/8  Done"
# =============================================================================
cat <<EOF

  Device ID : $DEVICE_ID   (change in /etc/seas/seas.env)
  Check     : seas-status
  Live logs : journalctl -u seas-env-logger -u seas-noise-inference -f

  Note: the dB(A) reading uses a provisional calibration until you calibrate
  this unit (docs/calibration.md). No audio is stored or uploaded.

EOF
if [[ $NEED_REBOOT -eq 1 ]]; then
    if [[ $AUTO_REBOOT -eq 1 ]]; then
        echo "Rebooting in 5 s..."; sleep 5; reboot
    elif [[ -r /dev/tty ]]; then
        read -r -p "Reboot now to finish setup? [Y/n] " ans < /dev/tty
        [[ "${ans:-Y}" =~ ^[Yy] ]] && reboot || echo "Remember to reboot: sudo reboot"
    else
        echo "Reboot to finish setup:  sudo reboot"
    fi
fi
