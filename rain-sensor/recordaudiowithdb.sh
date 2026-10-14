#!/bin/bash

counter=0
max_recordings=1

trap 'echo "Maximum recording limit reached. Stopping script."; exit 0' SIGINT

while [ $counter -lt $max_recordings ]; do
    filename="/home/pi/WeatherStationResources/AudioRecords/$(date +%Y-%m-%d_%H-%M-%S).wav"
    
    timeout 5s arecord -D plughw:1 -c1 -r 16000 -f S32_LE -t wav -V mono -v "$filename"
    
    echo $?
    
    if [ $? -eq 124 ]; then
        echo "Recording Finished"
    fi
    
    # Measure decibel level
    #decibel=$(sox "$filename" -n stat 2>&1 | grep "RMS lev dB" | awk '{print $4}')
    #db_tmp=$(sox $filename -n stat 2>&1 | grep "RMS.*amplitude" | cut -d":" -f2 | tr -d '[:space:]')
    #decibel=$(echo "20 * l($db_tmp)/l(10)" | bc -l)
    
    # Append dB level to filename
    #new_filename="${filename%.wav}_${decibel}dB.wav"
    #mv "$filename" "$new_filename"
    
	# Measure the amplitude using sox
	db_tmp=$(sox "$filename" -n stat 2>&1 | grep "RMS.*amplitude" | cut -d":" -f2 | tr -d '[:space:]')

	# Check if the amplitude value is empty or not
	if [ -z $db_tmp ]; then
		echo "Error: Unable to extract RMS amplitude value from the audio file."
		exit 1
	fi

	# Compute the decibel level
	  
    #d#ecibel=$(echo "20 * l($db_tmp)/l(10)" | bc -l | xargs printf "%.2f")
    decibel=$(echo "20 * l($db_tmp)/l(10)" | bc -l | awk '{print $0 < 0 ? $0 * -1 : $0}' | xargs printf "%.2f")

	# Check if the decibel calculation produced a valid result
	if [ -z $decibel ]; then
		echo "Error: Unable to compute decibel level."
		exit 1
	fi

	# Append dB level to filename
	new_filename="${filename%.wav}_${decibel}dB.wav"
	
	echo $new_filename
	
	mv $filename $new_filename

    echo "Recording saved as: $new_filename"
    
    sleep 1 # Optional pause between recordings (adjust as needed)
    
    counter=$((counter+1))
done
