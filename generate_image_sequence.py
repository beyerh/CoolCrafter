"""
Generate 24 1-bit pattern images for flipbook animation testing.
Creates a rotating line and expanding circle pattern.
"""
import numpy as np
from PIL import Image, ImageDraw
import os
import math

# DMD resolution
WIDTH = 1920
HEIGHT = 1080
NUM_FRAMES = 24

# Create output directory
output_dir = os.path.join(os.path.dirname(__file__), 'images', 'sequence')
os.makedirs(output_dir, exist_ok=True)

print(f"Generating {NUM_FRAMES} flipbook frames...")
print(f"Output directory: {output_dir}")

# Center point
cx, cy = WIDTH // 2, HEIGHT // 2

for frame in range(NUM_FRAMES):
    # Create black background (0 = black)
    img = Image.new('L', (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(img)
    
    # Calculate rotation angle (full 360° rotation)
    angle = (frame / NUM_FRAMES) * 2 * math.pi
    
    # Pattern 1: Rotating line from center extending to screen edges
    # Use diagonal distance to reach corners
    line_length = int(math.sqrt(WIDTH**2 + HEIGHT**2) / 2)  # ~1100px
    end_x = cx + int(line_length * math.cos(angle))
    end_y = cy + int(line_length * math.sin(angle))
    draw.line([(cx, cy), (end_x, end_y)], fill=255, width=12)
    
    # Pattern 2: Large expanding and contracting circle
    # Use most of the vertical space (500px radius at max)
    radius_variation = math.sin(angle) * 250 + 350  # Range: 100-600px
    draw.ellipse([
        cx - radius_variation, cy - radius_variation,
        cx + radius_variation, cy + radius_variation
    ], outline=255, width=8)
    
    # Pattern 3: Larger moving secondary circle orbiting farther out
    offset_angle = angle + math.pi / 2  # 90° offset
    orbit_distance = 550  # Larger orbit
    small_radius = 100  # Larger circle
    small_cx = cx + int(orbit_distance * math.cos(offset_angle))
    small_cy = cy + int(orbit_distance * math.sin(offset_angle))
    draw.ellipse([
        small_cx - small_radius, small_cy - small_radius,
        small_cx + small_radius, small_cy + small_radius
    ], fill=255)
    
    # Pattern 4: Frame number indicator (bottom corner to avoid overlap)
    draw.text((WIDTH - 200, HEIGHT - 80), f"Frame {frame + 1:02d}/{NUM_FRAMES}", fill=255)
    
    # Convert to binary (0 or 1) for 1-bit mode
    img_array = np.array(img)
    binary_array = (img_array > 128).astype(np.uint8) * 255
    
    # Save as PNG
    output_img = Image.fromarray(binary_array)
    filename = f"frame_{frame+1:02d}.png"
    filepath = os.path.join(output_dir, filename)
    output_img.save(filepath)
    
    print(f"  Generated: {filename}")

print(f"\n✓ Successfully generated {NUM_FRAMES} frames!")
print(f"  Location: {output_dir}")
print(f"\nTo test in GUI:")
print("  1. Launch gui.py")
print("  2. Add all images from images/sequence/")
print("  3. Select 'Sequence Mode'")
print("  4. Start projection")
