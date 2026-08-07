#!/usr/bin/python3
import subprocess
import requests
import datetime
import os
import math
import re
import sys
import time

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from tflite_runtime.interpreter import Interpreter
from math import log10

# — your two endpoints & device ID —
AUDIO_ENDPOINT     = "https://noise-sensors-dashboard.herokuapp.com/audio/"
INFERENCE_ENDPOINT = "https://noise-sensors-dashboard.herokuapp.com/device_metrics/sound-inference-data/"
DEVICE_ID          = "SEAS-1"

# — class names for your 19-class noise model —
class_names = {
     1: 'car-or-truck',         2: 'motorvehicle-horn',
     3: 'boda-boda-motocyle',   4: 'motorvehicle-siren',
     5: 'car-alarm',            6: 'mobile-music',
     7: 'hawker-vendor',        8: 'community-radio',
     9: 'regilious-venue',     10: 'herbalists',
    11: 'construction-site',   12: 'fabrication-workshop',
    13: 'generator',           14: 'bar-restaurant-nightclub',
    15: 'animal',              16: 'crowd-noise',
    17: 'school',              18: 'street-preacher',
     0: 'other'
}

MODEL_PATH      = "/home/pi/environmentsensor/quantizedmodels/seas_noise_classifier_v1.tflite"
#COUNTER_FILE    = "counter.txt"
COUNTER_FILE = "/home/pi/environmentsensor/scripts/counter.txt"

RECORD_SECONDS  = 5
SAMPLE_RATE     = 44100
TARGET_SR       = 16000

# Use the "plug" wrapper so ALSA does its rate-conversion and shares the device cleanly
ARECORD_DEV     = "plug:dmic_sv"

# how many seconds to sample for dynamic threshold
SOUND_METER_DUR = 5

# ─── SoundMeter helper ───────────────────────────────────────────────────────

def get_avg_rms(duration):
    try:
        proc = subprocess.run(
            ["/home/pi/.local/bin/soundmeter", "--collect", "--seconds", str(duration)],
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        print("✗ soundmeter failed:", e, file=sys.stderr)
        sys.exit(1)

    m = re.search(r'avg:\s*(\d+)', proc.stdout)
    if not m:
        print("⚠️ Could not parse avg from soundmeter output:\n", proc.stdout, file=sys.stderr)
        sys.exit(1)
    return int(m.group(1))

def rms_to_dbfs(rms):
    if rms <= 0:
        return float("-inf")
    return 20 * log10(rms / 32767)

# ─── Audio + Inference helpers ───────────────────────────────────────────────

def load_audio(path, target_sr=TARGET_SR):
    waveform, sr = sf.read(path)
    if sr != target_sr:
        g = math.gcd(sr, target_sr)
        waveform = resample_poly(waveform, target_sr//g, sr//g, axis=0)
    if waveform.ndim > 1:
        waveform = waveform.mean(axis=1)
    return waveform.astype(np.float32)

def run_inference(model_path, audio_path):
    x = load_audio(audio_path)
    interpreter = Interpreter(model_path=model_path)
    inp = interpreter.get_input_details()[0]
    interpreter.resize_tensor_input(inp['index'], x.shape)
    interpreter.allocate_tensors()
    interpreter.set_tensor(inp['index'], x)
    interpreter.invoke()

    out = interpreter.get_output_details()[0]
    raw = interpreter.get_tensor(out['index'])
    scale, zp = out['quantization']
    if scale > 0:
        logits = (raw.astype(np.float32) - zp) * scale
    else:
        logits = raw.astype(np.float32)

    exps = np.exp(logits - np.max(logits, keepdims=True))
    probs = exps / np.sum(exps, keepdims=True)

    idx   = int(np.argmax(probs, axis=-1))
    label = class_names[idx]
    prob  = float(probs[0][idx] if probs.ndim > 1 else probs[idx])
    return label, prob

def get_and_update_counter():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    cnt = 1

    # Try to read an existing counter
    if os.path.exists(COUNTER_FILE):
        try:
            with open(COUNTER_FILE, "r") as f:
                content = f.read().strip()
            prev_date, prev_cnt = content.split(",", 1)
            if prev_date == today:
                cnt = int(prev_cnt) + 1
            else:
                cnt = 1
        except Exception:
            # file is empty, malformed, or contains a single value:
            cnt = 1

    # Write back today's date and the updated count
    with open(COUNTER_FILE, "w") as f:
        f.write(f"{today},{cnt}")

    return cnt, today


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    # 0) Dynamic threshold
    print(f"[INFO] Sampling {SOUND_METER_DUR}s for threshold…")
    threshold = get_avg_rms(SOUND_METER_DUR)
    dbfs      = rms_to_dbfs(threshold)
    print(f"[INFO] → avg RMS = {threshold}, ~{dbfs:.1f} dBFS")

    # give ALSA a moment to free the HAT
    time.sleep(5)

    # 1) Filename
    count, date = get_and_update_counter()
    fname = f"{count}.wav"

    # 2) Record
    try:
        subprocess.run(
            ["arecord", "-D", ARECORD_DEV,
             "-c2", "-r", str(SAMPLE_RATE),
             "-f", "S32_LE", "-t", "wav",
             "-d", str(RECORD_SECONDS),
             "-V", "mono", "-v", fname],
            check=True
        )
        print(f"[INFO] Recorded {fname}")
    except subprocess.CalledProcessError as e:
        print("ERROR: Recording failed:", e)
        return

    # 3) Inference
    label, prob = run_inference(MODEL_PATH, fname)
    print(f"[INFO] Inferred class: {label} Probability: ({prob:.4f})")

    # 4) Upload audio (dBFS as triggering_threshold, cast to int)
    time_rec = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    try:
        threshold_value = int(round(abs(dbfs), 0))
        with open(fname, "rb") as f:
            files = {"audio": (fname, f, "audio/wav")}
            data  = {
                "time_recorded":        time_rec,
                "device":               DEVICE_ID,
                "triggering_threshold": threshold_value
            }

            resp = requests.post(
                AUDIO_ENDPOINT,
                data=data,
                files=files,
                timeout=15
            )
        print(f"[DEBUG] Audio upload code: {resp.status_code}")
        print(f"[DEBUG] Audio server body: {resp.text}")
        resp.raise_for_status()
        print("[INFO] Audio uploaded")
    except Exception as e:
        print("ERROR uploading audio:", e)

    # 5) Upload inference result
    try:
        payload = {
            "device":               DEVICE_ID,
            "inference_probability": prob,
            "inference_class":      label,
            "inferred_audio_name":  fname
        }
        resp2 = requests.post(INFERENCE_ENDPOINT, json=payload, timeout=10)
        print(f"[DEBUG] Inference upload code: {resp2.status_code}")
        print(f"[DEBUG] Inference server body: {resp2.text}")
        resp2.raise_for_status()
        print("[INFO] Inference data uploaded")
    except Exception as e:
        print("ERROR uploading inference:", e)

    # 6) Cleanup
    try:
        os.remove(fname)
        print(f"[INFO] Removed {fname}")
    except OSError as e:
        print("WARNING: Could not remove file:", e)

if __name__ == "__main__":
    try:
        while True:
            main()
            # wait 5 minutes before next run
            time.sleep(5 * 60)
    except KeyboardInterrupt:
        print("\nExiting on user request.")
