"""Record a 4 s clip from the mic, classify it with a waveform->probabilities
TFLite model (ai-edge-litert), append one JSON line per clip. Audio is recorded to
tmpfs and deleted; no raw audio is kept."""
import json, os, socket, subprocess, time, wave
from datetime import datetime, timezone
import numpy as np
import saesapi
from ai_edge_litert.interpreter import Interpreter

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.environ.get("SAES_MODEL", os.path.join(HERE, "models/noise_classifier_combined_noflex.tflite"))
LABELS = os.environ.get("SAES_LABELS", os.path.join(HERE, "models/labels.json"))
DEVICE = os.environ.get("SAES_MIC", "plughw:CARD=Device,DEV=0")
THREADS = int(os.environ.get("SAES_THREADS", 4))
SILENCE_DBFS = float(os.environ.get("SAES_SILENCE_DBFS", -60))
DATA_DIR = os.environ.get("SAES_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
SR, N = 16000, 64000
TMP = "/dev/shm/saes_clip.wav"

def record():
    subprocess.run(["arecord", "-q", "-D", DEVICE, "-c1", "-r", str(SR), "-f", "S16_LE",
                    "-t", "wav", "-d", "4", TMP], check=True, timeout=15)
    with wave.open(TMP) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    os.remove(TMP)
    return a

def fix_length(a):                       # same as repo features.fix_length (center crop / pad)
    if len(a) < N:
        pad = N - len(a); return np.pad(a, (pad // 2, pad - pad // 2))
    s = (len(a) - N) // 2
    return a[s:s + N]

CONF_MIN = float(os.environ.get("SAES_CONF_MIN", 0.30))   # below this the class is reported as "other"
POST_EVERY = int(os.environ.get("SAES_INFER_POST_S", 60))
# dashboard's existing class spellings (old model list had these typos)
LEGACY = {"religious-venue": "regilious-venue", "boda-boda-motorcycle": "boda-boda-motocyle"}
HP_HZ = float(os.environ.get("SAES_HIGHPASS_HZ", 120))

def highpass(a):                          # drops mains hum (50/100/150 Hz); YAMNet ignores <125 Hz anyway
    S = np.fft.rfft(a)
    S[np.fft.rfftfreq(len(a), 1 / SR) < HP_HZ] = 0
    return np.fft.irfft(S, len(a)).astype(np.float32)

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    labels = json.load(open(LABELS))
    it = Interpreter(model_path=MODEL, num_threads=THREADS); it.allocate_tensors()
    inp, out = it.get_input_details()[0], it.get_output_details()[0]
    host = socket.gethostname()
    best, window_start, seq = None, time.time(), 0
    print("model", os.path.basename(MODEL), "mic", DEVICE, flush=True)
    while True:
        rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": host,
               "model": os.path.basename(MODEL)}
        try:
            a = highpass(fix_length(record()))
            rms = float(np.sqrt(np.mean(a ** 2)))
            rec["rms_dbfs"] = round(20 * np.log10(max(rms, 1e-9)), 1)
            if rec["rms_dbfs"] < SILENCE_DBFS:
                rec["label"] = "silence"
            else:
                peak = float(np.max(np.abs(a)))
                x = (a / peak if peak > 1e-8 else a).astype(np.float32)
                t = time.perf_counter()
                it.set_tensor(inp["index"], x); it.invoke()
                p = it.get_tensor(out["index"]).reshape(-1)
                rec["infer_ms"] = round((time.perf_counter() - t) * 1000)
                top = np.argsort(p)[::-1][:3]
                rec["label"], rec["confidence"] = labels[top[0]], round(float(p[top[0]]), 3)
                rec["top3"] = [[labels[i], round(float(p[i]), 3)] for i in top]
        except Exception as e:
            rec["error"] = str(e); time.sleep(5)
        if "rms_dbfs" in rec:
            json.dump({"t": time.time(), "rms_dbfs": rec["rms_dbfs"]}, open(os.path.join(DATA_DIR, "last_noise.json"), "w"))
        if "confidence" in rec and (best is None or rec["confidence"] > best["confidence"]):
            best = rec
        if time.time() - window_start >= POST_EVERY:
            if best is not None:                 # one result per window: the most confident clip
                seq += 1
                cls = best["label"] if best["confidence"] >= CONF_MIN else "other"
                payload = {"device": saesapi.DEVICE_ID, "inference_probability": best["confidence"],
                           "inference_class": LEGACY.get(cls, cls),
                           # name only; audio is never stored or uploaded (privacy)
                           "inferred_audio_name": "%s_%03d.wav" % (best["ts"][:10].replace("-", ""), seq)}
                rec["posted"], rec["post_detail"] = saesapi.post_json("/device_metrics/sound-inference-data/", payload)
            best, window_start = None, time.time()
        path = os.path.join(DATA_DIR, "noise-%s.jsonl" % rec["ts"][:10].replace("-", ""))
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(json.dumps(rec), flush=True)

if __name__ == "__main__":
    main()
