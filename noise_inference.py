#!/usr/bin/python3
import subprocess
import requests
import datetime
import os
import fcntl
import math
import time

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from tflite_runtime.interpreter import Interpreter

# — endpoints & device ID —
AUDIO_ENDPOINT     = "https://noise-api.sunbird.ai/audio"
INFERENCE_ENDPOINT = "https://noise-api.sunbird.ai/device_metrics/sound-inference-data/"
DEVICE_ID          = "SEAS-2"

# ─── Feature flags ───────────────────────────────────────────────────────────
# Audio stays on the device (edge processing only, for privacy). Clips are
# always deleted after inference regardless of this flag.
UPLOAD_AUDIO = False

# — 19 classes, in the model's output order (alphabetical, = labels.json) —
CLASS_NAMES = [
    "animal", "bar-restaurant-nightclub", "boda-boda-motorcycle", "car-alarm",
    "car-or-truck", "community-radio", "construction-site", "crowd-noise",
    "fabrication-workshop", "generator", "hawker-vendor", "herbalists",
    "mobile-music", "motorvehicle-horn", "motorvehicle-siren", "other",
    "religious-venue", "school", "street-preacher",
]

MODEL_PATH      = "/home/pi/environmentsensor/quantizedmodels/seas_noise_classifier_v3.tflite"
COUNTER_FILE    = "/home/pi/environmentsensor/scripts/counter.txt"

# The model takes exactly 4 s of 16 kHz mono float32 audio in [-1, 1].
RECORD_SECONDS  = 4
SAMPLE_RATE     = 44100
TARGET_SR       = 16000
MODEL_SAMPLES   = RECORD_SECONDS * TARGET_SR

# Use the "plug" wrapper so ALSA does its rate-conversion and shares the device cleanly
ARECORD_DEV     = "plug:dmic_sv"

# Matches the environmental logger's cadence (~1 min)
INTERVAL_SECONDS = 60

# The I2S mic is an exclusive hw device; env_logger.py takes the same lock
MIC_LOCK = "/tmp/seas-mic.lock"

# ─── Audio + Inference helpers ───────────────────────────────────────────────

def load_audio(path, target_sr=TARGET_SR):
    waveform, sr = sf.read(path, dtype="float32")
    if waveform.ndim > 1:
        waveform = waveform.mean(axis=1)
    if sr != target_sr:
        g = math.gcd(sr, target_sr)
        waveform = resample_poly(waveform, target_sr // g, sr // g)
    waveform = waveform.astype(np.float32)
    # Trim / zero-pad to the fixed input length the model expects
    if len(waveform) < MODEL_SAMPLES:
        waveform = np.pad(waveform, (0, MODEL_SAMPLES - len(waveform)))
    return waveform[:MODEL_SAMPLES]

def load_model(model_path):
    interpreter = Interpreter(model_path=model_path, num_threads=4)
    interpreter.allocate_tensors()
    return interpreter

def run_inference(interpreter, audio_path):
    x = load_audio(audio_path)
    inp = interpreter.get_input_details()[0]
    out = interpreter.get_output_details()[0]
    interpreter.set_tensor(inp['index'], x)
    interpreter.invoke()

    # The exported graph already ends in a softmax: output is class probabilities
    probs = interpreter.get_tensor(out['index']).reshape(-1)
    idx   = int(np.argmax(probs))
    return CLASS_NAMES[idx], float(probs[idx])

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

def main(interpreter):
    # 1) Filename
    count, date = get_and_update_counter()
    fname = f"{count}.wav"

    try:
        # 2) Record
        try:
            with open(MIC_LOCK, "a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                subprocess.run(
                    ["arecord", "-D", ARECORD_DEV,
                     "-c1", "-r", str(SAMPLE_RATE),
                     "-f", "S16_LE", "-t", "wav",
                     "-d", str(RECORD_SECONDS),
                     "-V", "mono", "-v", fname],
                    check=True
                )
            print(f"[INFO] Recorded {fname}")
        except subprocess.CalledProcessError as e:
            print("ERROR: Recording failed:", e)
            return

        # 3) Inference
        label, prob = run_inference(interpreter, fname)
        print(f"[INFO] Inferred class: {label} Probability: ({prob:.4f})")

        # 4) Upload audio (only if UPLOAD_AUDIO flag is set)
        if UPLOAD_AUDIO:
            time_rec = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
            try:
                with open(fname, "rb") as f:
                    files = {"audio": (fname, f, "audio/wav")}
                    data  = {
                        "time_recorded": time_rec,
                        "device":        DEVICE_ID,
                    }
                    resp = requests.post(
                        AUDIO_ENDPOINT,
                        data=data,
                        files=files,
                        timeout=60
                    )
                print(f"[DEBUG] Audio upload code: {resp.status_code}")
                resp.raise_for_status()
                print("[INFO] Audio uploaded")
            except Exception as e:
                print("ERROR uploading audio:", e)
        else:
            print("[INFO] Audio upload skipped (UPLOAD_AUDIO=False)")

        # 5) Upload inference result
        try:
            payload = {
                "device":                DEVICE_ID,
                "inference_probability": prob,
                "inference_class":       label,
                "inferred_audio_name":   fname
            }
            resp2 = requests.post(INFERENCE_ENDPOINT, json=payload, timeout=10)
            print(f"[DEBUG] Inference upload code: {resp2.status_code}")
            print(f"[DEBUG] Inference server body: {resp2.text}")
            resp2.raise_for_status()
            print("[INFO] Inference data uploaded")
        except Exception as e:
            print("ERROR uploading inference:", e)
    finally:
        # 6) Cleanup — always runs, whatever happened above
        try:
            os.remove(fname)
            print(f"[INFO] Removed {fname}")
        except OSError as e:
            print("WARNING: Could not remove file:", e)

if __name__ == "__main__":
    try:
        interpreter = load_model(MODEL_PATH)
        while True:
            try:
                main(interpreter)
            except Exception as e:
                print("ERROR in inference cycle:", e)
            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nExiting on user request.")
