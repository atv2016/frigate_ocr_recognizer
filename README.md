# Frigate OCR Recognizer

Identify OCR text using EasyOCR and Pytorch and add them as sublabels to [blakeblackshear/frigate](https://github.com/blakeblackshear/frigate) using Frigate events API and MQTT.

This is an experimental fork of [ljmerza/frigate_plate_recognizer](https://github.com/ljmerza/frigate_plate_recognizer/tree/master) and is very much in a beta state. Things will probably not work as they should.

Note the image size is currently very large +- 8Gb, 6Gb compressed, because OpenCV, PyTorch and Nvidia CUDA are being included. I will look at minimizing this at some point but no promises and it might not be possible. You will need a installation of Frigate, a MQTT broker like Mosquito and optionally you can have Home Assistant installed if you want to automate on it (or something else).

### Example

![Screenshot 2024-03-17 at 18 45 51](https://github.com/atv2016/frigate_ocr_recognizer/assets/16917203/cbf7abb5-9e21-4d00-91f5-ae709c5b7c5d)

Above example shows a sublabel in Frigate with filled in recognised text. It also shows the camera name and a timestamp, which is why we usually tell you to disable that on the stream, as it will also be recognized and muddle up your sublabels in Frigate.

### Why
1. You don't need internet access or get an account with Platerecognizer and limited API calls.
2. Get text recognition on anything, rather then just license plates. One could argue that without a sufficiently powerful ANPR camera both will most likely achieve the same thing. You can setup automations like:
   - Specific vehicles driving by or that are stationary in your road and reading the text
   - Perform license plate recognition in your driveway or further down the road
   - Put numbers on your wheelie bins and recognize if they have been put by the road
   - Talk to your home automation from outside by showing text on a piece paper
   - On top of face recognition, add word recognition before the front door unlocks
   - Add a silent alarm and call for help when someone holds up a trigger word
3. I only have low resolution<sub>1</sub> cameras and it can reliably detect text at 1-30 meters, depending on the size of the text. I will most likely be even better at long range or smaller text if you have even higher resolution camera's<sub>2</sub> (but remember your canvas size will grab a larger chunk of memory from your GPU<sub>3</sub>).
4. Object detection is great, but not fool proof. Using it with OCR makes it even better and more foolproof for your automations. And if i had to choose OCR over object or even color detection, i would actually choose OCR first. Object detection fails often, unless you really dial in your parameters or upload your own models, for which you need a lot of pictures. As objects can look alike, whereas digits or letters are always unique. Ofcourse OCR needs a certain text size, which is why it is ideal for vans or trucks that have lettering on the side, but i have seen it work on surprisingly small sizes as well. I will show some examples below.
5. And ofcourse, you don't <ins>have</ins> to wait for objects to have letters or numbers, as mentioned you can label your own stuff and automate on this.
6. OCR works on the entire field of view, rather then one device that you have to place somewhere and have limited range, like a infrared or ultrasonic device that does exhibit those constraints.

On the first screenshot below you can see Amazon Prime and Thames Water vans, both recognized, and this is while they are driving, at an angle.
![Screenshot 2024-03-20 at 06 40 42](https://github.com/atv2016/frigate_ocr_recognizer/assets/16917203/c3bda13a-4d0e-4ad9-886b-830aa722a585)
The second screenshot you see Amazon Prime stationary, as well as a DPD delivery van and truck again driving, at an angle (notice how EasyOCR picks up 2x DPD, one on the side and one on the back) and this is at least 20 meters away.
![Screenshot 2024-03-20 at 06 41 21](https://github.com/atv2016/frigate_ocr_recognizer/assets/16917203/22c211a7-0a9c-4d12-959d-d1b8305a2f86)

<sub>1</sub> 1920x1280, 1080P upscaled is considered low resolution nowadays. However, i personally won't be upgrading any time soon as it adds a considerable amount of CPU cycles to video processing as well as memory on the GPU card that you will ne needing, so for me it is the sweet spot right now.

<sub>2</sub> 4K and above.
<sub>3</sub> It is highly recommended to use a GPU with EasyOCR. Bonus is that you can also use it with Frigate, if you are not already. I am currently using a [ASUS NVIDIA GeForce GT 730 Graphics Card (PCIe 2.0, 2GB GDDR5 Memory, 4x HDMI Ports, Single-slot Design, Passive Cooling](https://www.amazon.co.uk/gp/product/B09DVN7QWH/ref=ppx_yo_dt_b_search_asin_title?ie=UTF8&psc=1) and i share this between Frigate and Compreface. I currently have Compreface shut down as i cannot run both EasyOCR and Frigate within 4Gb, so i need a new machine at some point.

### Setup

Create a `config.yml` file in your docker volume with the following contents:

```yml
frigate:
  frigate_url: http://127.0.0.1:5000
  mqtt_server: 127.0.0.1
  mqtt_username: username
  mqtt_password: password
  main_topic: frigate
  return_topic: ocr_recognizer
  frigate_plus: false
  camera:
    - driveway_camera
  objects:
    - car
    - person
  min_score: .8
ocr_recognizer:
  token: xxxxxxxxxx
  regions: 
    - us-ca
logger_level: INFO
```

Update your frigate url, mqtt server settings. If you are using mqtt authentication, update the username and password. Update the camera name(s) to match the camera name in your frigate config.

You can also filter by zones and/or cameras. If you want to filter by zones, add `zones` to your config:

```yml
frigate:
  # ...
  zones:
    - front_door
    - back_door
```

If no objects are specified in the Frigate options, it will default to `[motorcycle, car, bus]`. You can detect OCR on any object but it will be much more accurate on stationary objects and on events of short notice, as well as being less CPU intensive. It will also work best on high resolution images, or on large letters, like on the side of a car or van, with no other text other then the object of focus. This is why we advocate to use either snapshots (the default) but with no crop, height restrictions, timestamp, and bounding box configured or use the use_clean_snapshots option in the config.yml described below. The latter will take a little longer for the event to finalize and OCR to kick in, but you will get better results on high resolution images if you don't want to change your snapshots setting, and you don't need to configure anything extra as with the use_clean_snapshots=false (the default) option.

In some cases, even though you want to detect cars, it is beneficial to also detect persons because if this person gets out of the car or van that is the object of interest and walks in front of your camera, or any person, that has your object still in the background, the object by now is most likely stationary and you get a better frame and thus better text recognition. Moving vehicles don't always produce the best frames. Ofcourse adding person as an object will somewhat increase your processing as it will do all person objects, and process all events that match these objects (cars and person), but the end result is better recognition. Another option if you want to detect almost anything, is to lower the object score to 0.1, you will most likely get a hit on almost anything (e.g. any motion).

As mentioned, if you do want to use snapshots, you have to make sure to not set the height in frigate for the camera, or crop the image, as well as set bounding_box: false (don't just comment it out as it will then use the default value) and timestamp to false so you get the full resolution and make sure there is no extra text on the object detection which might confuse the OCR. The advantage of using snapshots, is that you will get faster detection and your automations will thus run faster.

To use snapshots (the default option) you have to set:

In your config.yml :
```frigate:
  use_clean_snapshots: false # By default we use the API snapshot
```
In your frigate configuration file:
```
    snapshots:
      enabled: true
      timestamp: false
      bounding_box: false
      crop: false
      #height: 500
```
If you set ```use_clean_snapshots= true``` then you don't have to change anything in your frigate configuration.

Also keep in mind that it will detect the object, and then keep updating the snapshot per frame until the event is finalized. So if the object is not fully stationary (like a person), you might not get the most ideal snapsnot for text recognition (e.g. with a person it might detect you backwards and miss the text you are holding up.

It is also recommended to disable any logos on the cameras you are using as they will be part of the recognition. When text has been extracted, it will be added to the sublabel in frigate, and prefaced with OCR (on the sublabel filter it will take the last 30 characters or so).

Finally, currently the canvas_size given to EasyOCR is 1000. If you have the available GPU memory, you can leave that out for better image. I have to share the GPU with frigate and compreface, so i only have a little left i can use. But the larger the image, and the higher the resolution, the better. My camera's have a 1080P stream, but it would be interesting to see what results a 4K camera would give. 

When you do change it and you have customised EasyOCR recognition (i would not recommend it, but see bottom of this article) make sure to test if it works on a variety of your images as changing any setting to EasyOCR or given image, can have detrimental effects on text recognition. Sometimes making the canvas larger (or smaller) might have a worse effect, especially if you combine it with other EasyOCR parameters, and when you do finetune it more with said parameters, even a minor thing as removing the timestamps or logo's can affect recognition. 

### Building
This is only needed if you are re-building your own image because you changed the source.
```
sudo docker build -t <docker namespace>/frigate_ocr_recognizer:v1.0.0-yourtag . --no-cache
```
If using semantic versioning, or do:
```
sudo docker build -t <docker namespace>/frigate_ocr_recognizer . --no-cache
```
To get the latest tag assigned by docker. Note that it is not recommended to use the latest tag but rather a version tag as per the first example if you don't want things to break unexpectedly.

Optional: 
If you want to upload to docker public registry using a semantic tag (or leave it out to get the latest tag).
```
sudo docker build -t <docker namespace>/frigate_ocr_recognizer:v1.0.0-yourtag . --no-cache
sudo docker login
sudo docker push <docker namespace/frigate_ocr_recognizer:v1.0.0-yourtag
```
### Running
You can use docker run to run your own image you just build in the previous step:
```
sudo docker run -e TZ=Europe/London -it --gpus all -e NVIDIA_DRIVER_CAPABILITIES=all --privileged -v ./:/config --rm frigate_ocr_recognizer:v1.0.0-yourtag (or latest)
```
Or run it from the docker registry by prefacing it with the namespace from docker (if you build your own image make sure to do that as well, e.g. ```-t <docker_namespace```, otherwise docker push might give you problems).

```bash
sudo docker run -e TZ=Europe/London -it --gpus all -e NVIDIA_DRIVER_CAPABILITIES=all --privileged -v ./:/config --rm
frigate_ocr_recognizer atv2016/frigate_ocr_recognizer:v1.0.0-yourtag (or latest)
```
or just use the docker-compose supplied:

```yml
services:
  frigate_ocr_recognizer:
    image: atv2016/frigate_ocr_recognizer:latest
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    privileged: true
    container_name: frigate_ocr_recognizer
    volumes:
      - ./:/config
    restart: unless-stopped
    environment:
      - TZ=Europe/London
      - NVIDIA_DRIVER_CAPABILITIES=all
```
And execute:
```
sudo docker-compose up -d
```
[Docker repository](https://hub.docker.com/r/atv2016/frigate_ocr_recognizer)

### Debugging

set `logger_level` in your config to `DEBUG` to see more logging information:

```yml
logger_level: DEBUG
```

Logs will be in `/config/frigate_ocr_recognizer.log`

### Save Snapshot Images to Path

If you want frigate-ocr-recognizer to automatically save snapshots of recognized ocr, add the following to your config.yml:

```yml
frigate:
  use_clean_snapshots: false # By default we use the API snapshot
  save_snapshots: True # Saves a snapshot called [Camera Name]_[timestamp].png
  draw_box: True # Optional - Draws a box around the ocr on the snapshot along with the OCR text (Required Frigate plus setting)
  always_save_snapshot: True # Optional - will save a snapshot of every event sent to frigate_ocr_recognizer, even if no plate is detected
```

Snapshots will be saved into the '/ocr' directory within your container - to access them directly, map an additional volume within your docker-compose, e.g.:

```yml
services:
  frigate_ocr_recognizer:
    image: atv2016/frigate_ocr_recognizer:latest
    container_name: frigate_ocr_recognizer
    volumes:
      - /path/to/config:/config
      - /path/to/ocr:/ocr:rw
    restart: unless-stopped
    environment:
      - TZ=Europe/London
```

### Monitor Watched OCR text

If you want frigate-ocr-recognizer to check recognized ocr text against a list of watched ocr text for close matches, add the following to your config.yml:

```yml
frigate:
  watched_ocr: #list of ocr text to watch.
    -  PRIME
    -  THANK YOU
```

If a watched ocr text is found in the list of ocr returned by easyOCR, the response will be updated to use that text. The original ocr will be added to the MQTT response as an additional `original_ocr` field.

### Automations

A simple way of automating would be to trigger on the frigate/events topic :

```
alias: Frigate OCR
description: ""
trigger:
  - platform: mqtt
    topic: frigate/ocr_recognizer
condition:
  - condition: template
    value_template: "{{ trigger.payload_json['ocr_text'] | regex_search('PRIME|PRIME') }}"
```

And attach the appropriate action to it, like TTS or whatever you would like. Some of regex_search expression i use are PRIME,DPD, ROYAL MAIL,MORRISONS, THAMES WATER etc. Currently every recognised text is in upper case, so make sure you search on those when using regular expression statements. Possibly in the future one could trigger on the watched_ocr string defined in the docker compose file but i have not looked at that possibility yet (although the return MQTT topic does get updated as per plate recognizer). It is <ins>fully achievable</ins> that you could automate your house by holding up a sign in front of the camera (LIGHTS OFF or ALARM, or HELP) and you could then have HA perform it's automations.

Remember, if you use the ```use_clean_snapshots=false``` option you will have to wait until the event has signaled it's last message.
This has implications obviously for automations, as the clean snapshot won't be available until the event has finished (as opposed to a regular API snapshot which will be immediately available). This means your automation won't run until the events ends either, so there might a slight delay, but in the end it all depends on your use case and also how your event detection is configured in frigate.

### EasyOCR optimization

You can give a variety of options to EasyOCR, and you can test them out by using the easy.py script that is included in the repo. Look on the [JadedAI](https://github.com/JaidedAI/EasyOCR) website for the full API reference. You can adjust batch size, scale, margin, canvas and a whole lot more. That said, i found the default to work the best for my needs in the end.

Open easy.py and update:
```
result = reader.readtext(sys.argv[1], canvas_size=1000,detail=0)
```
To whatever parameters you want to add to the call. Save the file, and then run it like so:

```
python3 easy.py <filepath (can be http)>
```
And it will return what it found. It is very bare bones so there is no error handling or anything. But it serves as a quick way to test if an image works with your parameters.

### Copyright
[EasyOCR](https://github.com/JaidedAI/EasyOCR) is copyright EasyOCR and [JadedAI](https://jaded.ai) and comes with a Apache 2.0 license, which is included in this repository as custom. All files in this repository are also released under that same license, again as per custom.
