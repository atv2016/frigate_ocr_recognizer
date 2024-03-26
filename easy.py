# EasyOCR testing script
# Just takes a file path, can be a url and outputs the recognised text.

import sys
import easyocr
import torch
import gc
import os

# Do gc and memory cleanup as Pytorch is memory intensive
gc.collect()
torch.cuda.ipc_collect()
torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()
torch.cuda.reset_accumulated_memory_stats()

# You can actually use CPU but i could not get it to work and apparently works much slower.
reader = easyocr.Reader(['en'],gpu=True)

# Change parameters here. The larger the canvas size the more GPU memory will be used.

if "CANVAS_SIZE" in os.environ:
		CANVAS_SIZE=int(os.environ["CANVAS_SIZE"])
else:
   CANVAS_SIZE=""

if CANVAS_SIZE:
  print(f"Using custom canvas size of { CANVAS_SIZE }")
  result = reader.readtext(sys.argv[1], canvas_size=CANVAS_SIZE,detail=0)
else:
	print("Using default canvas size of 2560")
	result = reader.readtext(sys.argv[1],detail=0)

print(result)
# Clean up reader object
del(reader)
