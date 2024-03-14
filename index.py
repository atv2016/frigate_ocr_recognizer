#!/bin/python3

from datetime import datetime

import os
import sqlite3
import time
import logging

import paho.mqtt.client as mqtt
import yaml
import sys
import json
import requests

# EasyOCR & PyTorch
import easyocr
import torch
import gc

import io
from PIL import Image, ImageDraw, UnidentifiedImageError, ImageFont
import difflib

mqtt_client = None
config = None
first_message = True
_LOGGER = None

VERSION = '1.8.13'

CONFIG_PATH = '/config/config.yml'
DB_PATH = '/config/frigate_ocr_recogizer.db'
LOG_FILE = '/config/frigate_ocr_recogizer.log'
CLEAN_SNAPSHOT_PATH = '/ocr'

DATETIME_FORMAT = "%Y-%m-%d_%H-%M"

#PLATE_RECOGIZER_BASE_URL = 'https://api.platerecognizer.com/v1/plate-reader'
DEFAULT_OBJECTS = ['car', 'motorcycle', 'bus']
CURRENT_EVENTS = {}


def on_connect(mqtt_client, userdata, flags, rc):
    _LOGGER.info("MQTT Connected")
    mqtt_client.subscribe(config['frigate']['main_topic'] + "/events")

def on_disconnect(mqtt_client, userdata, rc):
    if rc != 0:
        _LOGGER.warning("Unexpected disconnection, trying to reconnect")
        while True:
            try:
                mqtt_client.reconnect()
                break
            except Exception as e:
                _LOGGER.warning(f"Reconnection failed due to {e}, retrying in 60 seconds")
                time.sleep(60)
    else:
        _LOGGER.error("Expected disconnection")

def set_sublabel(frigate_url, frigate_event_id, sublabel, score):
    post_url = f"{frigate_url}/api/events/{frigate_event_id}/sub_label"
    _LOGGER.debug(f'sublabel: {sublabel}')
    _LOGGER.debug(f'sublabel url: {post_url}')

    # frigate limits sublabels to 20 characters currently
    if len(sublabel) > 20:
        sublabel = sublabel[:20]

    sublabel = 'OCR:' + str(sublabel).upper() # plates are always upper cased

    # Submit the POST request with the JSON payload
    payload = { "subLabel": sublabel }
    headers = { "Content-Type": "application/json" }
    response = requests.post(post_url, data=json.dumps(payload), headers=headers)

    percent_score = "{:.1%}".format(score)

    # Check for a successful response
    if response.status_code == 200:
        _LOGGER.info(f"Sublabel set successfully to: {sublabel} with {percent_score} confidence")
    else:
        _LOGGER.error(f"Failed to set sublabel. Status code: {response.status_code}")

def ocr_recognizer(image):
    
    # Do gc and memory cleanup as Pytorch is memory intensive
    gc.collect()
    torch.cuda.ipc_collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.reset_accumulated_memory_stats()

    reader = easyocr.Reader(['en'],gpu=True)


    result = reader.readtext(image, canvas_size=1000,detail=0)

    # Clean up reader object
    del(reader)
    
    ocr_text= result
    score = None
    
    watched_ocr, watched_score, fuzzy_score = check_watched_ocr(ocr_text)
    if fuzzy_score:
        return ocr_text, score, watched_ocr, fuzzy_score
    elif watched_ocr: 
        return ocr_text, ocr_score, watched_ocr, None
    else:
        return ocr_text, score, None, None

def check_watched_ocr(ocr_text):
    config_watched_ocr = config['frigate'].get('watched_ocr', [])
    if not config_watched_ocr:
        _LOGGER.debug("Skipping checking Watched OCR because watched_ocr is not set")
        return None, None, None
    
    config_watched_ocr = [str(x).lower() for x in config_ocr_plates] #make sure watched_ocr are all lower case
    
    #Step 1 - test if top ocr is a watched ocr
    matching_ocr = str(ocr_text).lower() in config_watched_ocr 
    if matching_ocr:
        _LOGGER.info(f"Recognised OCR is a Watched OCR: {ocr_text}")
        return None, None, None  
    
def send_mqtt_message(ocr_text, ocr_score, frigate_event_id, after_data, formatted_start_time, watched_ocr, fuzzy_score):
    if not config['frigate'].get('return_topic'):
        return

    if watched_ocr:
        message = {
            'ocr_text': str(watched_ocr).upper(),
            'score': ocr_score,
            'frigate_event_id': frigate_event_id,
            'camera_name': after_data['camera'],
            'start_time': formatted_start_time,
            'fuzzy_score': fuzzy_score,
            'original_plate': str(ocr_text).upper()
        }
    else:
        message = {
            'ocr_text': str(ocr_text).upper(),
            'score': ocr_score,
            'frigate_event_id': frigate_event_id,
            'camera_name': after_data['camera'],
            'start_time': formatted_start_time
        }

    _LOGGER.debug(f"Sending MQTT message: {message}")

    main_topic = config['frigate']['main_topic']
    return_topic = config['frigate']['return_topic']
    topic = f'{main_topic}/{return_topic}'

    mqtt_client.publish(topic, json.dumps(message))

def has_common_value(array1, array2):
    return any(value in array2 for value in array1)

def save_image(config, after_data, frigate_url, frigate_event_id, ocr_text):
    if not config['frigate'].get('save_clean_snapshots', False):
        _LOGGER.debug(f"Skipping saving clean snapshot because save_clean_snapshots is set to false")
        return
    
    # get latest Event Data from Frigate API
    event_url = f"{frigate_url}/api/events/{frigate_event_id}"
    
    final_attribute = get_final_data(event_url) 
         
    # get latest clean snapshot
    clean_snapshot = get_clean_snapshot(after_data['camera'],frigate_event_id, frigate_url, False)
    if not clean_snapshot:
        return

    image = Image.open(io.BytesIO(bytearray(clean_snapshot)))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("./Arial.ttf", size=14)
    
    if final_attribute:
        image_width, image_height = image.size
        dimension_1 = final_attribute[0]['box'][0]
        dimension_2 = final_attribute[0]['box'][1]
        dimension_3 = final_attribute[0]['box'][2]
        dimension_4 = final_attribute[0]['box'][3]

        ocr_box = (
            dimension_1 * image_width,
            dimension_2 * image_height,
            (dimension_1 + dimension_3) * image_width,
            (dimension_2 + dimension_4) * image_height
        )
        draw.rectangle(ocr_box, outline="red", width=2) 
        _LOGGER.debug(f"Drawing OCR Box: {ocr_box}")
        
        if ocr_text:
            draw.text(
                (
                    (dimension_1 * image_width)+  5,
                    ((dimension_2 + dimension_4) * image_height) + 5
                ), 
                str(ocr_text).upper(), 
                font=font
            )      

    # save image
    timestamp = datetime.now().strftime(DATETIME_FORMAT)
    image_name = f"{after_data['camera']}_{timestamp}.png"
    if ocr_text:
        image_name = f"{str(ocr_text).upper()}_{image_name}"

    image_path = f"{CLEAN_SNAPSHOT_PATH}/{image_name}"
    _LOGGER.info(f"Saving image with path: {image_path}")
    image.save(image_path)

def check_first_message():
    global first_message
    if first_message:
        first_message = False
        _LOGGER.debug("Skipping first message")
        return True
    return False

def check_invalid_event(before_data, after_data):
    # check if it is from the correct camera or zone
    config_zones = config['frigate'].get('zones', [])
    config_cameras = config['frigate'].get('camera', [])

    matching_zone = any(value in after_data['current_zones'] for value in config_zones) if config_zones else True
    matching_camera = after_data['camera'] in config_cameras if config_cameras else True

    # Check if either both match (when both are defined) or at least one matches (when only one is defined)
    if not (matching_zone and matching_camera):
        _LOGGER.debug(f"Skipping event: {after_data['id']} because it does not match the configured zones/cameras")
        return True

    # check if it is a valid object
    valid_objects = config['frigate'].get('objects', DEFAULT_OBJECTS)
    if(after_data['label'] not in valid_objects):
        _LOGGER.debug(f"is not a correct label: {after_data['label']}")
        return True

    # limit api calls to plate checker api by only checking the best score for an event
    if(before_data['top_score'] == after_data['top_score'] and after_data['id'] in CURRENT_EVENTS) and not config['frigate'].get('frigate_plus', False):
        _LOGGER.debug(f"duplicated snapshot from Frigate as top_score from before and after are the same: {after_data['top_score']} {after_data['id']}")
        return True
    return False

def get_clean_snapshot(camera,frigate_event_id, frigate_url, cropped):
    _LOGGER.debug(f"Getting clean snapshot for event: {frigate_event_id}, Crop: {cropped}")
    clean_snapshot_url = f"{frigate_url}/clips/{camera}-{frigate_event_id}-clean.png"
    _LOGGER.debug(f"event URL: {clean_snapshot_url}")

    # get snapshot
    response = requests.get(clean_snapshot_url, params={ "crop": cropped, "quality": 100 })

    # Check if the request was successful (HTTP status code 200)
    if response.status_code != 200:
        _LOGGER.error(f"Error getting clean snapshot (event still in progress): {response.status_code}")
        return

    return response.content

def get_license_plate_attribute(after_data):
    if config['frigate'].get('frigate_plus', False):
        attributes = after_data.get('current_attributes', [])
        license_plate_attribute = [attribute for attribute in attributes if attribute['label'] == 'license_plate']
        return license_plate_attribute
    else:
        return None
    
def get_final_data(event_url):
    if config['frigate'].get('frigate_plus', False):
        response = requests.get(event_url)
        if response.status_code != 200:
            _LOGGER.error(f"Error getting final data: {response.status_code}")
            return
        event_json = response.json()
        event_data = event_json.get('data', {})
    
        if event_data:
            attributes = event_data.get('attributes', [])
            final_attribute = [attribute for attribute in attributes if attribute['label'] == 'license_plate']
            return final_attribute
        else:
            return None
    else:
        return None
    

def is_valid_license_plate(after_data):
    # if user has frigate plus then check license plate attribute
    after_license_plate_attribute = get_license_plate_attribute(after_data)
    if not any(after_license_plate_attribute):
        _LOGGER.debug(f"no license_plate attribute found in event attributes")
        return False

    # check min score of license plate attribute
    license_plate_min_score = config['frigate'].get('license_plate_min_score', 0)
    if after_license_plate_attribute[0]['score'] < license_plate_min_score:
        _LOGGER.debug(f"license_plate attribute score is below minimum: {after_license_plate_attribute[0]['score']}")
        return False

    return True

def is_duplicate_event(frigate_event_id):
     # see if we have already processed this event
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""SELECT * FROM plates WHERE frigate_event = ?""", (frigate_event_id,))
    row = cursor.fetchone()
    conn.close()

    if row is not None:
        _LOGGER.debug(f"Skipping event: {frigate_event_id} because it has already been processed")
        return True

    return False

def get_ocr(clean_snapshot):
    # try to get plate number
    orc_text = None
    ocr_score = None

    if config.get('ocr_recognizer'):
        ocr_text, ocr_score , watched_ocr, fuzzy_score = ocr_recognizer(clean_snapshot)
    else:
        _LOGGER.error("OCR Recognizer is not configured")
        return None, None, None, None

    # check OCR Recognizer score
    min_score = config['frigate'].get('min_score')
    score_too_low = min_score and plate_score and plate_score < min_score

    if not fuzzy_score and score_too_low:
        _LOGGER.info(f"Score is below minimum: {ocr_score} ({ocr_text})")
        return None, None, None, None

    return ocr_text, ocr_score, watched_ocr, fuzzy_score

def store_plate_in_db(ocr_text, ocr_score, frigate_event_id, after_data, formatted_start_time):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    _LOGGER.info(f"Storing OCR text in database: {ocr_text} with score: {ocr_score}")

    cursor.execute("""INSERT INTO plates (detection_time, score, plate_number, frigate_event, camera_name) VALUES (?, ?, ?, ?, ?)""",
        (formatted_start_time, ocr_score, ocr_text, frigate_event_id, after_data['camera'])
    )

    conn.commit()
    conn.close()

def on_message(client, userdata, message):
    if check_first_message():
        return

    # get frigate event payload
    payload_dict = json.loads(message.payload)
    _LOGGER.debug(f'mqtt message: {payload_dict}')

    before_data = payload_dict.get('before', {})
    after_data = payload_dict.get('after', {})
    type = payload_dict.get('type','')
    
    frigate_url = config['frigate']['frigate_url']
    frigate_event_id = after_data['id']
    camera = after_data['camera']
    
    if type == 'end' and after_data['id'] in CURRENT_EVENTS:
        _LOGGER.debug(f"CLEARING EVENT: {frigate_event_id} after {CURRENT_EVENTS[frigate_event_id]} calls to AI engine")
        del CURRENT_EVENTS[frigate_event_id]
    
    if check_invalid_event(before_data, after_data):
        return

    if is_duplicate_event(frigate_event_id):
        return

 #   frigate_plus = config['frigate'].get('frigate_plus', False)
 #   if frigate_plus and not is_valid_license_plate(after_data):
 #       return
    
    if not type == 'end' and not after_data['id'] in CURRENT_EVENTS:
        CURRENT_EVENTS[frigate_event_id] =  0
        
    clean_snapshot = get_clean_snapshot(camera,frigate_event_id, frigate_url, True)

    if not clean_snapshot:
        del CURRENT_EVENTS[frigate_event_id] # remove existing id from current events due to clean snapshot failure - will try again next frame
        return

    _LOGGER.debug(f"Using EasyOCR on finished event: {frigate_event_id}")
    if frigate_event_id in CURRENT_EVENTS:
        if config['frigate'].get('max_attempts', 0) > 0 and CURRENT_EVENTS[frigate_event_id] > config['frigate'].get('max_attempts', 0):
            _LOGGER.debug(f"Maximum number of AI attempts reached for event {frigate_event_id}: {CURRENT_EVENTS[frigate_event_id]}")
            return
        CURRENT_EVENTS[frigate_event_id] += 1

    ocr_text, ocr_score, watched_ocr, fuzzy_score = get_ocr(clean_snapshot)
    if ocr_text:
        start_time = datetime.fromtimestamp(after_data['start_time'])
        formatted_start_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
        
        if watched_ocr:
            store_plate_in_db(watched_ocr, ocr_score, frigate_event_id, after_data, formatted_start_time)
        else:
            store_plate_in_db(ocr_text, ocr_score, frigate_event_id, after_data, formatted_start_time)
        set_sublabel(frigate_url, frigate_event_id, watched_ocr if watched_ocr else ocr_text, ocr_score)

        send_mqtt_message(ocr_text, ocr_score, frigate_event_id, after_data, formatted_start_time, watched_ocr, fuzzy_score)
         
    if ocr_text or config['frigate'].get('always_save_clean_snapshot', False):
        save_image(
            config=config,
            after_data=after_data,
            frigate_url=frigate_url,
            frigate_event_id=frigate_event_id,
            plate_number=watched_ocr if watched_ocr else ocr_text
        )

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detection_time TIMESTAMP NOT NULL,
            score TEXT NOT NULL,
            plate_number TEXT NOT NULL,
            frigate_event TEXT NOT NULL UNIQUE,
            camera_name TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def load_config():
    global config
    with open(CONFIG_PATH, 'r') as config_file:
        config = yaml.safe_load(config_file)

    if CLEAN_SNAPSHOT_PATH:
        if not os.path.isdir(CLEAN_SNAPSHOT_PATH):
            os.makedirs(CLEAN_SNAPSHOT_PATH)

def run_mqtt_client():
    global mqtt_client
    _LOGGER.info(f"Starting MQTT client. Connecting to: {config['frigate']['mqtt_server']}")
    now = datetime.now()
    current_time = now.strftime("%Y%m%d%H%M%S")

    # setup mqtt client
    mqtt_client = mqtt.Client("FrigateOCRRecognizer" + current_time)
    mqtt_client.on_message = on_message
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_connect = on_connect

    # check if we are using authentication and set username/password if so
    if config['frigate'].get('mqtt_username', False):
        username = config['frigate']['mqtt_username']
        password = config['frigate'].get('mqtt_password', '')
        mqtt_client.username_pw_set(username, password)

    mqtt_client.connect(config['frigate']['mqtt_server'])
    mqtt_client.loop_forever()

def load_logger():
    global _LOGGER
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.setLevel(config.get('logger_level', 'INFO'))

    # Create a formatter to customize the log message format
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Create a console handler and set the level to display all messages
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)

    # Create a file handler to log messages to a file
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Add the handlers to the logger
    _LOGGER.addHandler(console_handler)
    _LOGGER.addHandler(file_handler)

def main():
    load_config()
    setup_db()
    load_logger()

    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    _LOGGER.info(f"Time: {current_time}")
    _LOGGER.info(f"Python Version: {sys.version}")
    _LOGGER.info(f"Frigate OCR Recognizer Version: {VERSION}")
    _LOGGER.debug(f"config: {config}")

 #   if config.get('plate_recognizer'):
 #       _LOGGER.info(f"Using Plate Recognizer API")
 #   else:
 #       _LOGGER.info(f"Using CodeProject.AI API")


    run_mqtt_client()


if __name__ == '__main__':
    main()
