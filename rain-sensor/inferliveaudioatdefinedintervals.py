"""Live rain-intensity inference on the SAES sensor.

Records a short clip with arecord, extracts YAMNet embeddings with the 8-bit
quantized YAMNet front end inside the SAES noise model
(seas_noise_classifier_v1.tflite), averages them over time and classifies the
result with rain_classifier.tflite. Uses only the TFLite interpreter
(tflite-runtime), not the full TensorFlow package.
"""
import math
import os
import resource
import subprocess
import sys
import time

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

try:
    from tflite_runtime.interpreter import Interpreter
except ImportError:  # e.g. development machines with LiteRT instead
    from ai_edge_litert.interpreter import Interpreter

# --- Parameters ---
SAMPLE_RATE = 16000          # Hz expected by YAMNet
DURATION = 5                 # seconds recorded per classification
INTERVAL = 10                # seconds between classifications
CLASS_NAMES = {0: "Heavy Rain", 1: "Light Rain", 2: "No Rain"}

MODEL_DIR = os.environ.get("SAES_MODEL_DIR", "/home/pi/InferenceRainSensor/savedsbmodels")
FRONTEND_PATH = os.path.join(MODEL_DIR, "seas_noise_classifier_v1.tflite")
CLASSIFIER_PATH = os.path.join(MODEL_DIR, "rain_classifier.tflite")
WAV_PATH = os.environ.get("SAES_WAV_PATH", "/home/pi/InferenceRainSensor/recorded_file.wav")


def peak_memory_mb():
    """Peak resident memory of this process in MB (kB on Linux, bytes on macOS)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024


def record_audio(file_path, duration=DURATION, sample_rate=SAMPLE_RATE):
    subprocess.run([
        "arecord", "-D", "plughw:1", "-c2", "-r", str(sample_rate),
        "-f", "S16_LE", "-t", "wav", "-d", str(duration), file_path,
    ], check=False)


def load_audio(path):
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        g = math.gcd(int(sr), SAMPLE_RATE)
        audio = resample_poly(audio, SAMPLE_RATE // g, int(sr) // g).astype(np.float32)
    return audio[: SAMPLE_RATE * DURATION]


class RainClassifier:
    def __init__(self, frontend_path=FRONTEND_PATH, classifier_path=CLASSIFIER_PATH):
        # The noise model holds a quantized YAMNet followed by the noise head.
        # Keep intermediate tensors so the YAMNet embeddings can be read out.
        self.yamnet = Interpreter(model_path=frontend_path,
                                  experimental_preserve_all_tensors=True)
        self.embedding_index = next(
            d["index"] for d in self.yamnet.get_tensor_details()
            if "global_average_pooling2d/Mean" in d["name"]
            and len(d["shape"]) == 2 and d["shape"][-1] == 1024)
        self.head = Interpreter(model_path=classifier_path)
        self.head.allocate_tensors()
        self.head_in = self.head.get_input_details()[0]["index"]
        self.head_out = self.head.get_output_details()[0]["index"]

    def embed(self, audio):
        """Mean YAMNet embedding (1024,) of a mono 16 kHz waveform."""
        inp = self.yamnet.get_input_details()[0]["index"]
        self.yamnet.resize_tensor_input(inp, [len(audio)])
        self.yamnet.allocate_tensors()
        self.yamnet.set_tensor(inp, audio)
        self.yamnet.invoke()
        embeddings = self.yamnet.get_tensor(self.embedding_index)
        return embeddings.reshape(-1, 1024).mean(axis=0)

    def predict(self, audio):
        self.head.set_tensor(self.head_in, self.embed(audio).reshape(1, 1024).astype(np.float32))
        self.head.invoke()
        scores = self.head.get_tensor(self.head_out)[0]
        idx = int(np.argmax(scores))
        return idx, CLASS_NAMES[idx]


def main():
    clf = RainClassifier()
    print(f"Models loaded, peak memory {peak_memory_mb():.0f} MB")
    try:
        while True:
            record_audio(WAV_PATH)
            idx, name = clf.predict(load_audio(WAV_PATH))
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {idx} ({name})  "
                  f"peak memory {peak_memory_mb():.0f} MB")
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("Process interrupted by user.")


if __name__ == "__main__":
    main()
