# Rain sensor package

Scripts and model for classifying rain intensity (No Rain, Light Rain, Heavy Rain) from 5 s audio clips on the SAES sensor, as described in the associated HardwareX article.

| File | Purpose |
|---|---|
| `rain_classifier.tflite` | Quantized classifier head (516 kB). Input: 1024-dimensional YAMNet embedding. Output: Heavy Rain, Light Rain, No Rain |
| `inferliveaudioatdefinedintervals.py` | Records 5 s of audio every 10 s, extracts a YAMNet embedding and prints the predicted class |
| `recordaudiowithdb.sh` | Records a 5 s mono clip at 16 kHz and appends its RMS level in dB to the file name |
| `logCSVTPHvalues.sh` | Logs BME680 temperature, pressure and humidity to a daily CSV every 30 s |
| `requirements.txt` | Python packages used by the inference script |

The inference script expects the YAMNet SavedModel and `rain_classifier.tflite` under `/home/pi/InferenceRainSensor/savedsbmodels/`; edit the paths at the top of the script if you store them elsewhere.
