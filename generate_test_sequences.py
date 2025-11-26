#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate test pattern sequences for DMD testing.

This script creates two sets of test patterns:
1. 400 1-bit patterns (black/white) in 'test_patterns/1bit_sequence/'
2. 50 8-bit grayscale patterns in 'test_patterns/8bit_sequence/'

Each sequence is designed to create a smooth animation when displayed in order.
"""

import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import math
import shutil

def create_directories():
    """Create output directories if they don't exist."""
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_patterns')
    dirs = {
        'base': base_dir,
        '1bit': os.path.join(base_dir, '1bit_sequence'),
        '8bit': os.path.join(base_dir, '8bit_sequence')
    }
    
    # Remove existing directories if they exist
    for d in [dirs['1bit'], dirs['8bit']]:
        if os.path.exists(d):
            shutil.rmtree(d)
    
    # Create new directories
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    
    return dirs

def generate_1bit_sequence(output_dir, width=1920, height=1080, num_patterns=400):
    """Generate 1-bit test patterns."""
    print(f"Generating {num_patterns} 1-bit patterns...")
    
    for i in range(num_patterns):
        # Create a new image with white background
        img = Image.new('1', (width, height), color=1)  # 1 = white in 1-bit mode
        draw = ImageDraw.Draw(img)
        
        # Calculate pattern parameters based on frame number
        phase = (2 * math.pi * i) / 100  # Complete cycle every 100 frames
        
        # Draw a moving square
        size = min(width, height) // 4
        x = int((width - size) * (0.5 + 0.4 * math.sin(phase)))
        y = int((height - size) * (0.5 + 0.4 * math.cos(phase)))
        
        # Draw the square (black on white)
        draw.rectangle([x, y, x + size, y + size], fill=0)
        
        # Add frame number
        draw.text((10, 10), f"Frame {i+1}/{num_patterns}", fill=0)
        
        # Save as 1-bit PNG
        filename = os.path.join(output_dir, f'pattern_{i:04d}.png')
        img.save(filename, 'PNG')
        
        if (i + 1) % 50 == 0:
            print(f"  - Generated {i+1}/{num_patterns} patterns")
    
    print(f"1-bit patterns saved to: {output_dir}")

def generate_8bit_sequence(output_dir, width=1920, height=1080, num_patterns=50):
    """Generate 8-bit grayscale test patterns."""
    print(f"\nGenerating {num_patterns} 8-bit grayscale patterns...")
    
    # Try to load a font, fall back to default if not available
    try:
        font = ImageFont.truetype("Arial.ttf", 40)
    except IOError:
        font = ImageFont.load_default()
    
    for i in range(num_patterns):
        # Create a new grayscale image
        img = Image.new('L', (width, height), color=128)  # 128 = mid-gray
        draw = ImageDraw.Draw(img)
        
        # Calculate pattern parameters based on frame number
        phase = (2 * math.pi * i) / 25  # Complete cycle every 25 frames
        
        # Draw a gradient that moves across the screen
        for y in range(0, height, 5):
            # Vary the gradient based on the frame number and y position
            intensity = int(128 + 127 * math.sin(phase + y/100))
            draw.line([(0, y), (width, y)], fill=intensity, width=5)
        
        # Draw a rotating grayscale gradient circle
        circle_size = min(width, height) // 3
        for r in range(circle_size, 0, -5):
            intensity = int(255 * (1 - r/circle_size))
            center_x = int(width * (0.5 + 0.3 * math.sin(phase)))
            center_y = int(height * (0.5 + 0.3 * math.cos(phase)))
            bounds = [
                center_x - r, 
                center_y - r, 
                center_x + r, 
                center_y + r
            ]
            draw.ellipse(bounds, outline=intensity, width=2)
        
        # Add frame number and intensity indicator
        text = f"Frame {i+1}/{num_patterns}"
        text_width = draw.textlength(text, font=font)
        text_x = width - text_width - 20
        text_y = height - 50
        
        # Draw text with outline for better visibility
        for dx in [-1, 1]:
            for dy in [-1, 1]:
                draw.text((text_x + dx, text_y + dy), text, fill=0, font=font)
        draw.text((text_x, text_y), text, fill=255, font=font)
        
        # Save as 8-bit PNG
        filename = os.path.join(output_dir, f'grayscale_{i:04d}.png')
        img.save(filename, 'PNG')
        
        if (i + 1) % 10 == 0:
            print(f"  - Generated {i+1}/{num_patterns} patterns")
    
    print(f"8-bit grayscale patterns saved to: {output_dir}")

def main():
    # Create output directories
    dirs = create_directories()
    
    # Generate 1-bit sequence (400 patterns)
    generate_1bit_sequence(dirs['1bit'], num_patterns=400)
    
    # Generate 8-bit sequence (50 patterns)
    generate_8bit_sequence(dirs['8bit'], num_patterns=50)
    
    print("\nTest pattern generation complete!")
    print(f"1-bit patterns: {dirs['1bit']}")
    print(f"8-bit patterns: {dirs['8bit']}")

if __name__ == "__main__":
    main()
