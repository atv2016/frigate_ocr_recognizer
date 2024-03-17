# EasyOCR testing script
# Just takes a file path, can be a url and outputs the recognised text.

import sys
import easyocr
import torch
import gc

# Do gc and memory cleanup as Pytorch is memory intensive
gc.collect()
torch.cuda.ipc_collect()
torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()
torch.cuda.reset_accumulated_memory_stats()

# You can actually use CPU but i could not get it to work and apparently works much slower.
reader = easyocr.Reader(['en'],gpu=True)

# Change parameters here. The larger the canvas size the more GPU memory will be used.

result = reader.readtext(sys.argv[1], canvas_size=1000,detail=0)

print(result)
# Clean up reader object
del(reader)
