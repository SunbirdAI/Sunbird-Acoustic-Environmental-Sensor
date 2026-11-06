#!/usr/bin/env python3
import subprocess
import requests
import datetime
import os
import math
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from tflite_runtime.interpreter import Interpreter

# — your two endpoints & device ID —
AUDIO_ENDPOINT = "https://noise-sensors-dashboard.herokuapp.com/audio/"
INFERENCE_ENDPOINT = "https://noise-sensors-dashboard.herokuapp.com/device_metrics/sound-inference-data/"
DEVICE_ID = "SEAS-1"

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

MODEL_PATH    = "/home/pi/environmentsensor/quantizedmodels/seas_noise_classifier_v1.tflite"
COUNTER_FILE  = "counter.txt"
RECORD_SECONDS = 10
SAMPLE_RATE    = 44100
TARGET_SR      = 16000
ARECORD_DEV    = "dmic_sv"

def load_audio(path: str, target_sr: int = TARGET_SR) -> np.ndarray:
    """Read WAV, resample to 16 kHz mono float32."""
    waveform, sr = sf.read(path)
    if sr != target_sr:
        # polyphase resampling
        g = math.gcd(sr, target_sr)
        up = target_sr // g
        down = sr // g
        waveform = resample_poly(waveform, up, down, axis=0)
    if waveform.ndim > 1:
        waveform = waveform.mean(axis=1)
    return waveform.astype(np.float32)

def run_inference(model_path: str, audio_path: str):
    """Return (label, probability) for the given audio file."""
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

    exps = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
    probs = exps / np.sum(exps, axis=-1, keepdims=True)

    idx  = int(np.argmax(probs, axis=-1))
    label = class_names[idx]
    prob  = float(probs[0][idx] if probs.ndim > 1 else probs[idx])
    return label, prob

def get_and_update_counter():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE) as f:
            date, cnt = f.read().split(",")
            cnt = int(cnt)
            cnt = cnt + 1 if date == today else 1
    else:
        cnt = 1
    with open(COUNTER_FILE, "w") as f:
        f.write(f"{today},{cnt}")
    return cnt, today

def main():
    # 1) Determine filename
    count, date = get_and_update_counter()
    fname = f"{count}.wav"

    # 2) Record audio
    try:
        subprocess.run(
            ["arecord", "-D", ARECORD_DEV,
             "-c2", "-r", str(SAMPLE_RATE),
             "-f", "S32_LE", "-t", "wav",
             "-d", str(RECORD_SECONDS),
             "-V", "mono", "-v", fname],
            check=True
        )
        print(f"Recorded {fname}")
    except subprocess.CalledProcessError as e:
        print("Recording failed:", e)
        return

    # 3) Run inference
    label, prob = run_inference(MODEL_PATH, fname)
    print(f"Inferred: {label} ({prob:.4f})")

    # 4) Upload raw audio
    time_rec = f"{date}T{datetime.datetime.now().hour:02d}:{datetime.datetime.now().minute:02d}"
    try:
        with open(fname, "rb") as f:
            resp = requests.post(
                AUDIO_ENDPOINT,
                data={
                    "time_recorded": time_rec,
                    "device": DEVICE_ID,
                    "triggering_threshold": 50
                },
                files={"audio": f}
            )
        resp.raise_for_status()
        print("Audio uploaded")
    except Exception as e:
        print("Audio upload error:", e)

    # 5) Upload inference result
    try:
        payload = {
            "device": DEVICE_ID,
            "inference_probability": prob,
            "inference_class": label,
            "inferred_audio_name": fname
        }
        resp2 = requests.post(INFERENCE_ENDPOINT, json=payload)
        resp2.raise_for_status()
        print("Inference data uploaded")
    except Exception as e:
        print("Inference upload error:", e)

    # 6) Cleanup
    os.remove(fname)

if __name__ == "__main__":
    main()
