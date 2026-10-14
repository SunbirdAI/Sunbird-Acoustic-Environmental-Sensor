# Rain sensor package

Scripts and model for classifying rain intensity (No Rain, Light Rain, Heavy Rain) from 5 s audio clips on the SAES sensor, as described in the associated HardwareX article.

| File | Purpose |
|---|---|
| `rain_classifier.tflite` | Classifier head (516 kB). Input: 1024-dimensional YAMNet embedding. Output: Heavy Rain, Light Rain, No Rain |
| `inferliveaudioatdefinedintervals.py` | Records 5 s of audio every 10 s, extracts YAMNet embeddings with the YAMNet TFLite model, classifies them and prints the predicted class and peak memory. Needs only `tflite-runtime` |
| `recordaudiowithdb.sh` | Records a 5 s mono clip at 16 kHz and appends its RMS level in dB to the file name |
| `logCSVTPHvalues.sh` | Logs BME680 temperature, pressure and humidity to a daily CSV every 30 s |
| `requirements.txt` | Python packages used by the inference script |

## Setup

```bash
pip install -r requirements.txt
mkdir -p /home/pi/InferenceRainSensor/savedsbmodels
cp rain_classifier.tflite /home/pi/InferenceRainSensor/savedsbmodels/
curl -L -o /home/pi/InferenceRainSensor/savedsbmodels/yamnet.tflite \
  "https://tfhub.dev/google/lite-model/yamnet/tflite/1?lite-format=tflite"
python3 inferliveaudioatdefinedintervals.py
```

`yamnet.tflite` is Google's YAMNet audio-event model (Apache-2.0, about 16 MB). To use other locations, set the `SAES_MODEL_DIR` and `SAES_WAV_PATH` environment variables.

On the 714 labelled clips of the Sunbird AI Rain Sensor Dataset (doi:10.17632/zhd8w29kz4.1) this pipeline classifies 93.8 % of clips correctly (these clips include those used for training).
