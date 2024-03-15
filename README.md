# Frigate OCR Recognizer

Identify OCR text using EasyOCR and Pytorch and add them as sublabels to [blakeblackshear/frigate](https://github.com/blakeblackshear/frigate) using Frigate events API and MQTT.

This is an experimental fork of [ljmerza/frigate_plate_recognizer](https://github.com/ljmerza/frigate_plate_recognizer/tree/master) and is very much in a beta state. Things will probably not work as they should.

Note the image size is currently very large +- 10Gb, because opencv and PyTorch being included. I will look at minimizing this at some point.

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

If no objects are speficied in the Frigate options, it will default to `[motorcycle, car, bus]`. You can detect OCR on any object but it will be much more accurate on stationary objects and on events of short notice, as well as being less CPU intensive. It will also work best on high resolution images (this is why by default we take the event once finalized, rather then the low resolution snapshot) or on large letters, like on the side of a car or van. 

If you do want to use snapshots, you have to make sure to not set the height, or crop the image, as well as set bounding_box: false so you get the full resolution and no extra text on the object detection which might confuse the OCR. The advantage of using snapshots, is that you will get faster detection and your automations will thus run faster.

Also keep in mind that it will detect the object, and then keep updating the snapshot per frame until the event is finalized. So if the object is not fully stationary (like a person), you might not get the most ideal snapsnot for text recognition (e.g. with a person it might detect you backwards and miss the text you are holding up.

It is also recommended to disable timestamps or logos on the cameras you are using as they will be part of the recognition. When text has been extracted, it will be added to the sublabel in frigate, and prefaced with OCR (on the sublabel filter it will take the last 30 characters or so).

Finally, currently the canvas_size given to EasyOCR is 1000. If you have the available GPU memory, you can leave that out for better image. I have to share the GPU with frigate and compreface, so i only have a little left i can use. But the larger the image, and the higher the resolution, the better. When you do change it, make sure to test if it works on a variety of your images as changing any setting to EasyOCR or given image, can have detrimental effects on text recognition. Sometimes making the canvas larger might have a worse effect, especially if you combine it with other EasyOCR parameters. My camera's have a 1080P stream, but it would be interesting to see what results a 4K camera would give.

```

### Running

```bash
docker run -v /path/to/config:/config -e TZ=Europe/London -it --gpus all -e NVIDIA_DRIVER_CAPABILITIES=all --privileged --rm --name frigate_ocr_recognizer atv2016/frigate_ocr_recognizer:latest
```

or using docker-compose:

```yml
services:
  frigate_ocr_recognizer:
    image: atv2016/frigate_ocr_recognizer:latest
    container_name: frigate_ocr_recognizer
    volumes:
      - /path/to/config:/config
    restart: unless-stopped
    environment:
      - TZ=Europe/London
```

https://hub.docker.com/r/atv2016/frigate_ocr_recognizer

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
    value_template: "{{ trigger.payload_json['ocr_text'] | regex_search('PRIME') }}"
```

And attach the appropriate action to it, like TTS or whatever you would like. Possibly in the future one could trigger on the watched_ocr string defined in the docker compose file. In theory, you could automate your house by holding up a sign in front of the camera (LIGHTS OFF or ALARM, or HELP) and you could then have HA perform it's automations.

Because we currently only work on the high resolution and clean snapshot, we have to wait for the event to end (frigate does not save the clean snapshot until after). This has implications obviously for automations, as the clean snapshot won't be available until the event ends. This means your automation won't run until the events ends either, so there might a slight delay, but it all depends on your use case and how you're event detection is configured in frigate.
