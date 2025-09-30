#!/usr/bin/env python3
"""
Simple grayscale image projection using the DMD.
Configure the settings in the CONFIG section below.
"""
import numpy as np
import time
import os
from PIL import Image

# ===== CONFIGURATION =====
# Path to the image file (None to use default test pattern)
IMAGE_PATH = None  # e.g., "patterns/gradient.png" or "path/to/your/image.jpg"

# DMD display settings
BASE_EXPOSURE_US = 200  # Base exposure time in microseconds (for LSB)
COLOR = '111'           # Color channels ('111' for white, '100' for red, '010' for green, '001' for blue)
DMD_WIDTH = 1920        # DMD display width in pixels
DMD_HEIGHT = 1080       # DMD display height in pixels

# ===== END OF CONFIGURATION =====

def load_image(image_path):
    """Load and preprocess an image for DMD projection."""
    try:
        # Open and convert to grayscale
        img = Image.open(image_path).convert('L')
        
        # Resize to target dimensions (maintaining aspect ratio)
        img.thumbnail((DMD_WIDTH, DMD_HEIGHT), Image.Resampling.LANCZOS)
        
        # Create a new image with target size and paste the resized image
        result = Image.new('L', (DMD_WIDTH, DMD_HEIGHT), 0)  # Black background
        result.paste(img, ((DMD_WIDTH - img.width) // 2, 
                          (DMD_HEIGHT - img.height) // 2))
        
        return np.array(result, dtype=np.uint8)
    except Exception as e:
        print(f"Error loading image: {e}")
        return None

def create_test_pattern():
    """Create a simple test pattern if no image is provided."""
    # Create a horizontal gradient
    x = np.linspace(0, 255, DMD_WIDTH, dtype=np.uint8)
    y = np.linspace(0, 255, DMD_HEIGHT, dtype=np.uint8)
    return np.outer(y, x).astype(np.uint8)

def main():
    # Import the DMD library
    try:
        import pycrafter6500_grayscale as dmd_lib
    except ImportError:
        print("Error: Could not import pycrafter6500_grayscale.")
        print("Please install the required dependencies: pip install pyusb numpy pillow")
        return
    
    # Load or create image
    if IMAGE_PATH and os.path.exists(IMAGE_PATH):
        print(f"Loading image: {IMAGE_PATH}")
        pattern = load_image(IMAGE_PATH)
    else:
        print("No valid image specified, using test pattern")
        pattern = create_test_pattern()
    
    if pattern is None:
        print("Failed to load/create image pattern")
        return
    
    # Save the pattern for reference
    os.makedirs('output', exist_ok=True)
    output_path = os.path.join('output', 'current_pattern.png')
    Image.fromarray(pattern).save(output_path)
    print(f"Saved pattern to: {output_path}")
    
    # Initialize and display
    try:
        print("Initializing DMD...")
        dmd = dmd_lib.dmd()
        print("DMD initialized successfully.")
        
        print(f"Displaying pattern (exposure: {BASE_EXPOSURE_US}µs, color: {COLOR})...")
        print("Press Ctrl+C to stop.")
        
        dmd.display_grayscale_image(
            pattern,
            base_exposure_us=BASE_EXPOSURE_US,
            color=COLOR,
            trigger_in=False,
            dark_time=0,
            trigger_out=0
        )
        
        # Keep running until interrupted
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping display...")
        dmd.stopsequence()
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
