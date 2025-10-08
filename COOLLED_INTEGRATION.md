# CoolLED pE-4000 Integration Guide

## Overview
The Pycrafter6500 GUI now supports synchronized illumination control using the CoolLED pE-4000 LED system across all projection modes (Sequence, Constant, and Pulsed).

## Features Added

### 1. CoolLED Connection Panel
- **Location**: Left panel, below DMD Connection
- **Connection Options**:
  - Hardware connection (auto-detects CoolLED pE-4000)
  - Demo mode (for testing without hardware)
- **Status Indicator**: Shows connection state (Disconnected/Connected/Demo Mode)

### 2. Unified LED Settings (Per-Image)
- **Location**: Image Settings panel (center-right)
- **One panel for all modes** - no confusion!
- **Smart behavior based on projection mode**:
  - **Constant**: Uses selected image's LED settings
  - **Sequence**: Uses first image's LED settings for entire sequence
  - **Pulsed**: Each image uses its own settings (on/off per image)
- **Parameters**:
  - **Enable LED**: Checkbox to activate illumination
  - **Channel**: Select A, B, C, or D
  - **Wavelength (nm)**: Auto-updates based on selected channel
    - Channel A: 365, 385, 395, 405 nm (UV range)
    - Channel B: 425, 445, 460, 470 nm (Blue range)
    - Channel C: 500, 525, 550, 575 nm (Green/Yellow range)
    - Channel D: 635, 660, 740, 770 nm (Red/NIR range)
  - **Intensity (%)**: 0-100% power level
- **Context hint**: Label below settings explains behavior for current mode

### 3. LED Column in Image List
- Shows LED configuration for each image
- Format: `Ch{X} {wavelength}nm {intensity}%` or `-` if disabled
- Example: `ChA 365nm 75%`
- Visible in all modes

### 4. Enhanced Progress Logging
- LED status shown in progress log with clear format:
  - `LED: ChA 470nm @ 80% - ON`
  - `LED: ChA - OFF`
  - `LED: OFF (not enabled)`
  - `LED: All channels OFF`
- Helps track illumination state during experiments

### 5. Safety Features
- LEDs automatically turn OFF when:
  - Projection is stopped manually
  - Projection completes
  - An error occurs
  - Application closes
- Warning displayed if images have LED enabled but CoolLED not connected

## Usage Workflows

### Common Setup (All Modes)
1. Connect CoolLED pE-4000 via USB/Serial
2. Click "Connect" in CoolLED pE-4000 panel
3. If hardware not found, enable Demo Mode for testing
4. Add images to the sequence

### Workflow A: Constant Mode
**Goal**: Single image with constant LED illumination

1. Select projection mode: **"Constant (selected image only)"**
2. Add/select an image from the list
3. Configure LED in **Image Settings panel**:
   - Check "Enable LED"
   - Select Channel (A-D)
   - Choose Wavelength
   - Set Intensity (0-100%)
   - *Hint shows: "Used for constant projection"*
4. Set projection time (or enable infinite)
5. Click "Start Projection"
6. **Result**: Selected image's LED turns ON, stays ON throughout projection

**Progress Log Example**:
```
Starting constant projection...
LED: ChC 525nm @ 40% - ON
Projecting grey255.png (8bit) for 1800s...
```

**Use Case**: Continuous illumination (optogenetic activation, baseline fluorescence)

### Workflow B: Sequence Mode
**Goal**: Multiple patterns cycling with constant LED illumination

1. Select projection mode: **"Sequence (1-bit, up to 24 images)"**
2. Add 1-bit images to sequence
3. Select the **first image** in the list
4. Configure LED in **Image Settings panel**:
   - Check "Enable LED"
   - Select Channel (A-D)
   - Choose Wavelength
   - Set Intensity (0-100%)
   - *Hint shows in RED: "First image's settings used for entire sequence"*
5. Set number of cycles (0=infinite)
6. Click "Start Projection"
7. **Result**: First image's LED turns ON, stays ON while all patterns cycle

**Progress Log Example**:
```
Starting sequence projection...
LED: ChB 470nm @ 60% - ON
Projecting sequence of 3 1-bit image(s):
  1. pattern1.png (Exposure: 105μs, Dark: 0μs)
  2. pattern2.png (Exposure: 105μs, Dark: 0μs)
  3. pattern3.png (Exposure: 105μs, Dark: 0μs)
```

**Use Case**: Structured illumination, DMD masking with constant background light

### Workflow C: Pulsed Mode
**Goal**: Multiple images with per-image LED control

1. Select projection mode: **"Pulsed Projection"**
2. Add images to sequence
3. For **each image** you want illuminated:
   - Select image from list
   - In **Image Settings panel**:
     - Check "Enable LED"
     - Select Channel (A-D)
     - Choose Wavelength
     - Set Intensity (0-100%)
     - Set Duration (how long to project this image)
     - *Hint shows: "Per-image control (on/off each image)"*
4. Configure total runtime or number of cycles
5. Click "Start Projection"
6. **Result**: For each image: LED ON → Project for duration → LED OFF → Next

**Progress Log Example**:
```
Starting pulsed projection...
Cycle 1/10
  LED: ChA 365nm @ 50% - ON
  Projecting image1.png (8bit) for 5s...
  LED: ChA - OFF
  LED: ChC 525nm @ 75% - ON
  Projecting image2.png (8bit) for 5s...
  LED: ChC - OFF
```

**Use Case**: Multi-wavelength time-lapse, photobleaching protocols, optogenetics

## Example Use Cases

### Example 1: Constant Mode - Baseline Fluorescence Imaging
**Mode**: Constant  
**LED Settings (Global)**: ChC 525nm @ 40% (Green excitation)  
**Image**: grey255.png (full field illumination)  
**Duration**: 30 minutes  

**Description**: Continuous excitation for stable fluorescence measurement. Single LED setting for entire duration.

### Example 2: Sequence Mode - Structured Illumination
**Mode**: Sequence  
**LED Settings (Global)**: ChB 470nm @ 60% (Blue excitation)  
**Images**: 
- pattern1.png (stripe pattern 0°)
- pattern2.png (stripe pattern 45°)
- pattern3.png (stripe pattern 90°)

**Cycles**: 100  
**Description**: Cycling through 3 DMD patterns with constant blue illumination for structured illumination microscopy.

### Example 3: Pulsed Mode - Multi-Wavelength Time-Lapse
**Mode**: Pulsed

Image 1: grey255.png
- LED: ChA 365nm @ 50% (UV excitation for DAPI)
- Duration: 5 seconds

Image 2: grey255.png  
- LED: ChC 525nm @ 75% (Green excitation for GFP)
- Duration: 5 seconds

Image 3: grey255.png
- LED: ChD 635nm @ 100% (Red excitation for mCherry)
- Duration: 5 seconds

**Description**: Sequential multi-channel imaging with different illumination per timepoint.

### Example 4: Pulsed Mode - Photobleaching Protocol
**Mode**: Pulsed

Image 1: pattern1.png
- LED: ChB 470nm @ 30% (Low intensity baseline)
- Duration: 10 seconds

Image 2: pattern1.png
- LED: ChB 470nm @ 100% (High intensity bleach)
- Duration: 60 seconds

Image 3: pattern1.png
- LED: ChB 470nm @ 30% (Recovery monitoring)
- Duration: 10 seconds

**Description**: Automated photobleaching with precise intensity control per phase.

### Example 5: Pulsed Mode - Optogenetic Stimulation
**Mode**: Pulsed

Image 1: roi_neurons.png
- LED: ChB 470nm @ 80% (Blue light activation)
- Duration: 2 seconds

Image 2: roi_control.png
- LED: OFF (No stimulation)
- Duration: 8 seconds

**Description**: Alternating stimulation and rest periods with spatial control.

## Technical Details

### Communication Protocol
- **Serial Port**: Auto-detected (typical: /dev/ttyUSB* on Linux, COM* on Windows)
- **Baud Rate**: 57600 or 38400 (auto-negotiated)
- **Terminator**: `\r` (carriage return)

### Key Commands Used
- `XVER` - Query firmware version
- `LOAD:{wavelength}` - Load wavelength (e.g., `LOAD:470`)
- `CSS{ch}SN{intensity}` - Set intensity and turn ON (e.g., `CSSASN075` = Channel A, 75%)
- `CSS{ch}SF` - Turn channel OFF
- `CSF` - Turn all channels OFF

### CoolLEDController Class
Extracted from CoolLED_gui.py and integrated into gui.py:
- Handles serial communication
- Auto-detects devices
- Provides clean API for LED control
- Includes demo mode for testing

## Notes

### LED Control Modes Summary
- **Constant Mode**: Uses **selected image's** LED settings, stays ON throughout
- **Sequence Mode**: Uses **first image's** LED settings, stays ON while cycling
- **Pulsed Mode**: Uses **each image's** LED settings, turns ON/OFF per image

### Key Design Decisions
✅ **Unified Interface**: One LED panel (in Image Settings) for all modes - no confusion!  
✅ **Smart Behavior**: Same settings, different behavior based on projection mode  
✅ **Visual Hints**: Context label shows how LED will behave (RED for sequence mode!)  
✅ **Clear Logging**: LED status shown in progress log with consistent format  

### Important Details
- LED settings are per-image (stored with each image in GUI session)
- Settings NOT persisted to file - configure each session
- All LED settings configured in Image Settings panel (center-right)
- LED column in image list shows configuration for all images
- LEDs automatically turn OFF when projection stops (safety feature)
- Context hint updates when you change projection mode (RED for sequence!)

## Troubleshooting

### LED Not Responding
1. Check CoolLED connection status (should show "Connected" in green)
2. Verify correct serial port is detected
3. Try disconnecting and reconnecting
4. Check CoolLED hardware is powered on

### Warning: "Images have LED enabled but CoolLED not connected"
- Some images have LED checkbox enabled
- CoolLED is not connected
- Connect CoolLED or disable LED for those images

### LED Stays On After Stop
- This should not happen due to safety features
- Manually disconnect CoolLED to reset all channels
- Report as bug if persistent

## Demo Mode Testing
Both DMD and CoolLED support independent demo modes:
- Test LED configurations without hardware
- Log shows `[DEMO LED]` prefix for simulated LED control
- Useful for planning experiments and validating sequences
- Try all three modes (constant, sequence, pulsed) in demo mode

## Summary Table

| Mode | LED Source | When LED Turns ON | When LED Turns OFF | Context Hint | Use Case |
|------|-----------|-------------------|-------------------|--------------|----------|
| **Constant** | Selected image's settings | Start of projection | End of projection | Gray text | Single pattern + continuous light |
| **Sequence** | First image's settings | Start of projection | End of projection | **RED text** | Multiple patterns + continuous light |
| **Pulsed** | Each image's settings | Before each image | After each image | Gray text | Multiple patterns + varying light |

## Future Enhancements (Potential)
- Save/load LED configurations to file
- LED sequence templates
- Wavelength color preview in image list
- Real-time intensity adjustment during projection
- Support for multiple channels simultaneously in pulsed mode
