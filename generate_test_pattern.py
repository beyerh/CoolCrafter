#!/usr/bin/env python3
"""
Generate test patterns for DMD projection.
This script creates various grayscale test patterns and saves them as PNG files.
"""
import numpy as np
from PIL import Image
import os

def create_gradient_pattern(width=1920, height=1080):
    """Create a gradient test pattern."""
    x = np.linspace(0, 255, width, dtype=np.uint8)
    y = np.linspace(0, 255, height, dtype=np.uint8)
    return np.outer(y, x).astype(np.uint8)

def create_circles_pattern(width=1920, height=1080):
    """Create a pattern with concentric circles."""
    y_indices, x_indices = np.ogrid[:height, :width]
    center_x, center_y = width // 2, height // 2
    distance = np.sqrt((x_indices - center_x)**2 + (y_indices - center_y)**2)
    return (np.sin(distance / 20) * 127 + 128).astype(np.uint8)

def create_checkerboard_pattern(width=1920, height=1080, square_size=50):
    """Create a grayscale checkerboard pattern."""
    pattern = np.zeros((height, width), dtype=np.uint8)
    for i in range(0, height, square_size * 2):
        for j in range(0, width, square_size * 2):
            # Create 2x2 squares of different intensities
            pattern[i:i+square_size, j:j+square_size] = 64
            pattern[i+square_size:i+2*square_size, j+square_size:j+2*square_size] = 64
            pattern[i:i+square_size, j+square_size:j+2*square_size] = 192
            pattern[i+square_size:i+2*square_size, j:j+square_size] = 192
    return pattern

def save_pattern(pattern, filename):
    """Save the pattern as a PNG file."""
    dirname = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(dirname, filename)
    Image.fromarray(pattern).save(filepath)
    print(f"Saved: {filepath}")

def main():
    # Create output directory if it doesn't exist
    os.makedirs("patterns", exist_ok=True)
    
    # Generate and save patterns
    patterns = [
        (create_gradient_pattern(), "gradient.png"),
        (create_circles_pattern(), "circles.png"),
        (create_checkerboard_pattern(), "checkerboard.png")
    ]
    
    for pattern, filename in patterns:
        save_pattern(pattern, os.path.join("patterns", filename))
    
    print("\nPatterns generated successfully!")
    print("Use test_grayscale.py to display them on the DMD.")

if __name__ == "__main__":
    main()
