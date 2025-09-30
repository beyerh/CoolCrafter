import pycrafter6500
import numpy as np
import PIL.Image
import time

# -----------------------------
# USER CONFIGURATION
# -----------------------------
TOTAL_PROJECTION_TIME_SEC = 24 * 60 * 60    # Total projection time: 24 hours
PULSE_INTERVAL_SEC = 60 * 60                # Pulse (image2) appears once per hour
PULSE_DURATION_SEC = 10 * 60                # Duration of image2 pulse: 10 minutes

def load_binary_image(path):
    """Load and convert an image to binary format (0 or 1)"""
    img = PIL.Image.open(path).convert("L")
    img_np = np.asarray(img)
    return (img_np > 127).astype(np.uint8)  # Convert to binary (0 or 1)

def setup_sequence(dlp, image1, image2, exposure_us=10000):
    """
    Set up a sequence with both images using DMD's internal triggering
    
    Args:
        dlp: DMD controller instance
        image1: First binary image (displayed for most of the time)
        image2: Second binary image (displayed during pulse)
        exposure_us: Exposure time in microseconds (default: 10,000 µs = 10ms)
    """
    # Define the sequence with both images
    images = [image1, image2]
    exposures = [exposure_us, exposure_us]  # Same exposure for both images
    trigger_ins = [False, False]           # No external trigger
    dark_times = [0, 0]                    # No dark time between frames
    trigger_outs = [0, 0]                  # No trigger out
    
    # Load the sequence (but don't start it yet)
    dlp.defsequence(images, exposures, trigger_ins, dark_times, trigger_outs, 1)  # Loop mode 1 = auto-repeat
    
    # Set to pattern on the fly mode
    dlp.changemode(3)  # Video mode
    dlp.stopsequence()
    
    # Start with image1 (frame 0)
    dlp.definepattern(0, exposure_us, 1, '111', False, 0, 0, 0, 0)
    dlp.definepattern(1, exposure_us, 1, '111', False, 0, 0, 0, 1)
    dlp.startsequence()

# -----------------------------
# MAIN
# -----------------------------
def main():
    print("Starting DMD pulse projection with fixed exposure")
    
    # Load images
    print("Loading images...")
    try:
        image1 = load_binary_image("image1.png")
        image2 = load_binary_image("image2.png")
        print("Images loaded successfully")
    except Exception as e:
        print(f"Error loading images: {e}")
        return

    # Initialize DMD
    print("Initializing DMD...")
    try:
        dlp = pycrafter6500.dmd()
        dlp.stopsequence()
        print("DMD initialized successfully")
        
        # Set up the sequence with both images
        print("Setting up projection sequence...")
        setup_sequence(dlp, image1, image2)
        print("Projection sequence ready")
        
    except Exception as e:
        print(f"Error initializing DMD: {e}")
        return

    # Timing setup
    start_time = time.time()
    end_time = start_time + TOTAL_PROJECTION_TIME_SEC
    cycle_number = 1

    print(f"\nStarting projection sequence ({(end_time - start_time)/3600:.1f} hours total)")
    print(f"   - Image 1 duration: {(PULSE_INTERVAL_SEC - PULSE_DURATION_SEC)/60:.1f} min")
    print(f"   - Image 2 duration: {PULSE_DURATION_SEC/60:.1f} min")
    print("\nPress Ctrl+C to stop projection\n")

    try:
        last_switch = time.time()
        next_switch = last_switch + (PULSE_INTERVAL_SEC - PULSE_DURATION_SEC)
        current_image = 0  # 0 for image1, 1 for image2
        
        # Start with image1
        dlp.definepattern(0, int(1e6), 1, '111', False, 0, 0, 0, 0)
        
        while time.time() < end_time:
            current_time = time.time()
            
            # Check if it's time to switch images
            if current_time >= next_switch:
                if current_image == 0:
                    # Switch to image2 (pulse)
                    dlp.definepattern(0, int(1e6), 1, '111', False, 0, 0, 0, 1)
                    next_switch = current_time + PULSE_DURATION_SEC
                    print(f"[Cycle {cycle_number}] Switched to image2 for {PULSE_DURATION_SEC/60:.1f} min...")
                    current_image = 1
                else:
                    # Switch back to image1
                    dlp.definepattern(0, int(1e6), 1, '111', False, 0, 0, 0, 0)
                    next_switch = current_time + (PULSE_INTERVAL_SEC - PULSE_DURATION_SEC)
                    print(f"[Cycle {cycle_number}] Switched to image1 for {(PULSE_INTERVAL_SEC - PULSE_DURATION_SEC)/60:.1f} min...")
                    current_image = 0
                    cycle_number += 1
                last_switch = current_time
            
            # Calculate and display time remaining
            time_remaining = (end_time - current_time) / 3600  # in hours
            if time_remaining > 0 and int(time.time()) % 60 == 0:  # Update every minute
                print(f"{time_remaining:.1f} hours remaining")
            
            # Small sleep to prevent busy waiting
            time.sleep(0.1)

        print("Projection complete!")

    except KeyboardInterrupt:
        print("\nProjection stopped by user")
    finally:
        # Clean up
        print("Cleaning up...")
        dlp.stopsequence()
        print("Done")

if __name__ == "__main__":
    main()
