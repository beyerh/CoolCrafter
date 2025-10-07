"""
Script to alternate between two images with specified durations.
Supports both 1-bit binary and 8-bit grayscale images.
Projects image1 for a set duration, then image2 for another duration, and repeats.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pycrafter6500
import numpy
import PIL.Image
import cv2
import time

# ============================================================================
# CONFIGURATION - Edit these parameters
# ============================================================================
# Get the absolute path to the images folder
script_dir = os.path.dirname(os.path.abspath(__file__))
IMAGE1_PATH = os.path.join(script_dir, "..", "images", "image1.png")  # First image to project
IMAGE2_PATH = os.path.join(script_dir, "..", "images", "image2.png")  # Second image to project
IMAGE1_DURATION_SEC = 29 * 60         # Duration to show image1 (seconds)
IMAGE2_DURATION_SEC = 1 * 60          # Duration to show image2 (seconds)
TOTAL_RUNTIME_MIN   = 24 * 60         # Total projection time (minutes)

# Image mode: '1bit' for binary, '8bit' for grayscale
IMAGE1_MODE = '8bit'                  # Mode for image1
IMAGE2_MODE = '1bit'                  # Mode for image2
# ============================================================================

def load_and_convert_image(image_path, mode='1bit'):
    """Load an image and convert it to the specified format.
    
    Parameters:
    - image_path: Path to the image file
    - mode: '1bit' for binary (0-1) or '8bit' for grayscale (0-255)
    """
    print(f"Loading {image_path} in {mode} mode...")
    
    # Load image
    img = PIL.Image.open(image_path)
    
    # Convert to grayscale if needed
    if img.mode != 'L':
        img = img.convert('L')
    
    # Resize to DMD resolution if needed
    if img.size != (1920, 1080):
        print(f"  Resizing from {img.size} to (1920, 1080)...")
        img = img.resize((1920, 1080), PIL.Image.LANCZOS)
    
    # Convert to numpy array
    image = numpy.array(img)
    
    if mode == '1bit':
        # Convert to binary (0 or 1)
        image = image // 129
        print(f"  Converted to 1-bit binary (values: {image.min()}-{image.max()})")
    elif mode == '8bit':
        # Keep as 8-bit grayscale (0-255)
        image = image.astype(numpy.uint8)
        print(f"  Loaded as 8-bit grayscale (values: {image.min()}-{image.max()})")
    else:
        raise ValueError(f"Invalid mode: {mode}. Use '1bit' or '8bit'")
    
    return image

def project_image(dlp, image, duration_seconds, mode='1bit'):
    """Project a single image for the specified duration.
    
    Parameters:
    - dlp: DMD controller object
    - image: Numpy array of the image
    - duration_seconds: How long to project the image
    - mode: '1bit' or '8bit'
    """
    images = [image]
    
    # Pattern timing
    if mode == '8bit':
        # For 8-bit, use longer exposure for better grayscale rendering
        exposure = [100000]  # 100ms
    else:
        # For 1-bit, use shorter exposure
        exposure = [4046]  # ~4ms
    
    dark_time = [0]
    trigger_in = [False]
    trigger_out = [1]
    
    # Define and start the sequence (repeat=0 for continuous)
    if mode == '8bit':
        dlp.defsequence_8bit(images, exposure, trigger_in, dark_time, trigger_out, 0)
    else:
        dlp.defsequence(images, exposure, trigger_in, dark_time, trigger_out, 0)
    
    dlp.startsequence()
    
    # Wait for the specified duration
    time.sleep(duration_seconds)
    
    # Stop the sequence
    dlp.stopsequence()

def main():
    cycle_duration_sec = IMAGE1_DURATION_SEC + IMAGE2_DURATION_SEC
    total_runtime_sec = TOTAL_RUNTIME_MIN * 60
    total_cycles = int(total_runtime_sec / cycle_duration_sec)
    
    print("=" * 60)
    print("Timed Alternating Image Projection (8-bit Support)")
    print("=" * 60)
    print(f"Image 1: {IMAGE1_PATH} ({IMAGE1_MODE}) - Duration: {IMAGE1_DURATION_SEC} sec ({IMAGE1_DURATION_SEC/60:.1f} min)")
    print(f"Image 2: {IMAGE2_PATH} ({IMAGE2_MODE}) - Duration: {IMAGE2_DURATION_SEC} sec ({IMAGE2_DURATION_SEC/60:.1f} min)")
    print(f"Cycle duration: {cycle_duration_sec} sec ({cycle_duration_sec/60:.1f} min)")
    print(f"Total runtime: {TOTAL_RUNTIME_MIN} min ({TOTAL_RUNTIME_MIN/60:.1f} hours)")
    print(f"Total cycles: {total_cycles}")
    print("=" * 60)
    
    # Use configured durations
    image1_duration_sec = IMAGE1_DURATION_SEC
    image2_duration_sec = IMAGE2_DURATION_SEC
    
    # Load images
    t0 = time.time()
    image1 = load_and_convert_image(IMAGE1_PATH, IMAGE1_MODE)
    image2 = load_and_convert_image(IMAGE2_PATH, IMAGE2_MODE)
    
    # Initialize DMD controller
    print("Initializing DMD controller...")
    dlp = pycrafter6500.dmd()
    dlp.stopsequence()
    dlp.changemode(3)  # Pattern sequence mode
    
    t_start = time.time()
    print(f"Startup time: {round(t_start - t0, 4)} sec\n")
    
    # Main projection loop
    try:
        for cycle in range(1, total_cycles + 1):
            print(f"\n[Cycle {cycle}/{total_cycles}]")
            
            # Project image 1
            print(f"  Projecting {IMAGE1_PATH} ({IMAGE1_MODE}) for {IMAGE1_DURATION_SEC} sec ({IMAGE1_DURATION_SEC/60:.1f} min)...")
            start_time = time.time()
            project_image(dlp, image1, image1_duration_sec, IMAGE1_MODE)
            elapsed = time.time() - start_time
            print(f"  Completed in {elapsed:.1f} sec ({elapsed/60:.2f} min)")
            
            # Project image 2
            print(f"  Projecting {IMAGE2_PATH} ({IMAGE2_MODE}) for {IMAGE2_DURATION_SEC} sec ({IMAGE2_DURATION_SEC/60:.1f} min)...")
            start_time = time.time()
            project_image(dlp, image2, image2_duration_sec, IMAGE2_MODE)
            elapsed = time.time() - start_time
            print(f"  Completed in {elapsed:.1f} sec ({elapsed/60:.2f} min)")
            
            # Calculate and display progress
            progress = (cycle / total_cycles) * 100
            elapsed_total = time.time() - t_start
            remaining_hours = (total_runtime_sec - elapsed_total) / 3600
            print(f"  Progress: {progress:.1f}% | Elapsed: {elapsed_total/3600:.2f} hours | Remaining: {remaining_hours:.2f} hours")
        
        print("\n" + "=" * 60)
        print("All cycles completed successfully!")
        total_time = time.time() - t_start
        print(f"Total runtime: {total_time/3600:.2f} hours")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user!")
        dlp.stopsequence()
        print("Projection stopped.")
    except Exception as e:
        print(f"\nError occurred: {e}")
        dlp.stopsequence()
        print("Projection stopped.")

if __name__ == "__main__":
    main()
