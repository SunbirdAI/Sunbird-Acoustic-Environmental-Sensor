# Rain sensor package

Scripts and model for classifying rain intensity (No Rain, Light Rain, Heavy Rain) from 5 s audio clips on the SAES sensor, as described in the associated HardwareX article.

| File | Purpose |
|---|---|
| `rain_classifier.tflite` | Classifier head (516 kB). Input: 1024-dimensional YAMNet embedding. Output: Heavy Rain, Light Rain, No Rain |
| `inferliveaudioatdefinedintervals.py` | Records 5 s of audio every 10 s, extracts YAMNet embeddings with the quantized front end of the noise model, classifies them and prints the predicted class and peak memory. Needs only `tflite-runtime` |
| `recordaudiowithdb.sh` | Records a 5 s mono clip at 16 kHz and appends its RMS level in dB to the file name |
| `logCSVTPHvalues.sh` | Logs BME680 temperature, pressure and humidity to a daily CSV every 30 s |
| `requirements.txt` | Python packages used by the inference script |

## Setup

```bash
pip install -r requirements.txt
mkdir -p /home/pi/InferenceRainSensor/savedsbmodels
cp rain_classifier.tflite ../quantizedmodels/seas_noise_classifier_v1.tflite \
   /home/pi/InferenceRainSensor/savedsbmodels/
python3 inferliveaudioatdefinedintervals.py
```

The script reuses the 8-bit quantized YAMNet inside `seas_noise_classifier_v1.tflite` (4.2 MB) as its feature extractor, so no separate YAMNet download is needed: the rain pipeline is 4.2 MB + 516 kB. To use other locations, set the `SAES_MODEL_DIR` and `SAES_WAV_PATH` environment variables.

On the 714 labelled clips of the Sunbird AI Rain Sensor Dataset (doi:10.17632/zhd8w29kz4.1) this pipeline classifies 94.4 % of clips correctly (these clips include those used for training; 93.8 % with the float32 YAMNet TFLite model).

The embedding tensor is located by name (`global_average_pooling2d/Mean`), so if the noise model is re-exported the script may need updating.
