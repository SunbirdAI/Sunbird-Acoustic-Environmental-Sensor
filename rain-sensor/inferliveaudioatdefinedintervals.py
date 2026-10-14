import os
import librosa
import pandas as pd
import tensorflow as tf
import tensorflow_hub as hub
import numpy as np
import psutil
import subprocess
import time

# --- Data Parameters ---
SAMPLE_RATE = 16000  # Hz
DURATION = 5  # seconds
INTERVAL = 10  # seconds between each classification
CLASS_NAMES = {0: "Heavy Rain", 1: "Light Rain", 2: "No Rain"}

def get_memory_usage():
    """
    Returns the current memory usage in MB.
    """
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss / (1024 ** 2)  # in MB

def get_file_size(path):
    """
    Returns the size of the file in MB.
    """
    return os.path.getsize(path) / (1024 ** 2)  # in MB

def record_audio(file_path, duration=DURATION, sample_rate=SAMPLE_RATE):
    """
    Records an audio file using the arecord command.
    
    Args:
        file_path: Path to save the recorded audio file.
        duration: Duration of the recording in seconds.
        sample_rate: Sample rate of the recording in Hz.
    """
    command = [
        "arecord",
        "-D", "plughw:1",
        "-c2",
        "-r", str(sample_rate),
        "-f", "S16_LE",
        "-t", "wav",
        "-d", str(duration),
        file_path
    ]
    subprocess.run(command)

# --- Inference with TFLite Model ---
def predict_with_tflite_model(tflite_model_path, yamnet_model, wav_file, memory_log):
    """
    Predicts the rain category using the TFLite model.

    Args:
        tflite_model_path: Path to the TFLite model file.
        wav_file: Path to the WAV file.
        memory_log: List to log memory usage at various points.

    Returns:
        Predicted rain category (0, 1, or 2) and class name.
    """
    # Log memory usage before loading TFLite model
    memory_log.append(("Before loading TFLite model", get_memory_usage(), None, None))
    
    # Load audio and extract embeddings
    audio, _ = librosa.load(wav_file, sr=SAMPLE_RATE, duration=DURATION)
    audio_data = tf.convert_to_tensor(audio, dtype=tf.float32)

    scores, embeddings, spectrogram = yamnet_model(audio_data)
    embedding = embeddings.numpy().mean(axis=0)

    # Load the TFLite model and allocate tensors
    interpreter = tf.lite.Interpreter(model_path=tflite_model_path)
    interpreter.allocate_tensors()

    # Log memory usage after loading TFLite model
    memory_log.append(("After loading TFLite model", get_memory_usage(), get_file_size(tflite_model_path), "TFLite model"))

    # Get input and output tensors
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    # Set input tensor
    interpreter.set_tensor(input_details[0]['index'], np.expand_dims(embedding, axis=0).astype(np.float32))

    # Log memory usage before TFLite inference
    memory_log.append(("Before TFLite inference", get_memory_usage(), None, None))
    
    # Run inference
    interpreter.invoke()

    # Log memory usage after TFLite inference
    memory_log.append(("After TFLite inference", get_memory_usage(), None, None))

    # Get output tensor
    output_data = interpreter.get_tensor(output_details[0]['index'])

    # Get predicted class
    predicted_class = np.argmax(output_data)
    return predicted_class, CLASS_NAMES[predicted_class]

# yamnet_model = hub.load('https://tfhub.dev/google/yamnet/1')

# --- Example Usage ---
memory_log = []

# Log memory usage before loading YAMNet model
memory_log.append(("Before loading YAMNet model", get_memory_usage(), None, None))
yamnet_model_path = '/home/pi/InferenceRainSensor/savedsbmodels/yamnet'
yamnet_model = tf.keras.models.load_model(yamnet_model_path)
# Log memory usage after loading YAMNet model
memory_log.append(("After loading YAMNet model", get_memory_usage(), get_file_size(yamnet_model_path), "YAMNet model"))

# Path to your TFLite model
tflite_model_path = '/home/pi/InferenceRainSensor/savedsbmodels/rain_classifier.tflite'

# Continuous recording and inference
try:
    while True:
        # Record an audio file
        recorded_wav_file = '/home/pi/InferenceRainSensor/recorded_file.wav'
        record_audio(recorded_wav_file)

        # Make prediction with TFLite model
        tflite_prediction, class_name = predict_with_tflite_model(tflite_model_path, yamnet_model, recorded_wav_file, memory_log)

        # Print memory log as a table
        memory_df = pd.DataFrame(memory_log, columns=["Step", "Memory Usage (MB)", "File Size (MB)", "Model Type"])
        print(memory_df)

        print(f'TFLite Model Prediction: {tflite_prediction} ({class_name})')

        # Clear memory log for the next iteration
        memory_log.clear()

        # Wait for the specified interval before the next iteration
        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("Process interrupted by user.")
