"""
Test script for 8-bit grayscale image projection using the DMD.
Projects the hhu.tif image with 8-bit grayscale support.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pycrafter6500
import numpy as np
from PIL import Image
import time

# Load the 8-bit grayscale image
print("Loading 8-bit grayscale image...")
# Get the absolute path to the images folder
script_dir = os.path.dirname(os.path.abspath(__file__))
image_path = os.path.join(script_dir, "..", "images", "hhu.tif")
img = Image.open(image_path)

# Convert to grayscale if needed and ensure it's 8-bit
if img.mode != 'L':
    img = img.convert('L')

# Convert to numpy array
img_array = np.array(img, dtype=np.uint8)

# Resize to DMD resolution if needed (1920x1080)
if img_array.shape != (1080, 1920):
    print(f"Resizing image from {img_array.shape} to (1080, 1920)...")
    img = img.resize((1920, 1080), Image.LANCZOS)
    img_array = np.array(img, dtype=np.uint8)

print(f"Image shape: {img_array.shape}")
print(f"Image dtype: {img_array.dtype}")
print(f"Image value range: {img_array.min()} - {img_array.max()}")

# Put image in a list (required by defsequence_8bit)
images = [img_array]

# Initialize DMD controller
print("\nInitializing DMD controller...")
t0 = time.time()
dlp = pycrafter6500.dmd()

# Stop any running sequence
dlp.stopsequence()

# Set mode to pattern sequence mode (mode 3)
dlp.changemode(3)

# Configure timing parameters
# Exposure time in microseconds (adjust as needed for brightness)
# For 8-bit mode, the DMD will internally handle the bit plane timing
exposure = [100000]  # 100ms total exposure

# Dark time between patterns (0 for continuous projection)
dark_time = [0]

# Trigger settings
trigger_in = [False]   # No external trigger input
trigger_out = [1]      # Trigger output enabled

# Define the 8-bit sequence (repeat=0 means infinite loop)
print("\nDefining 8-bit grayscale sequence...")
dlp.defsequence_8bit(images, exposure, trigger_in, dark_time, trigger_out, 0)

t_start = time.time()
print(f"Startup time: {round(t_start - t0, 4)} sec")

# Start projecting the 8-bit grayscale pattern
print("\nStarting 8-bit grayscale projection...")
dlp.startsequence()

print("Projection active! Press Ctrl+C to stop.")

try:
    # Keep the script running
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n\nStopping projection...")
    dlp.stopsequence()
    print("Projection stopped.")
