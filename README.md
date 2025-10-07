# Pycrafter6500 - Python Controller for TI DLP LightCrafter 6500

A Python controller for Texas Instruments' DLPLCR6500EVM evaluation module for DLP technology. The controller can fully control the "pattern on-the-fly" mode with user-defined sequences of binary and grayscale images. Requires `pyusb` and `numpy`, with `PIL`/`pillow` recommended for image handling and testing. The library is compatible with the [uPatternScope](https://doi.org/10.1038/s41467-024-54351-6) for intensity modulated light pattern projection in optogenetic microscope experiments.


 using a microscope and intensity modulatied pattern projection.

## About This Fork

This is a fork of [Pycrafter6500](https://github.com/csi-dcsc/Pycrafter6500) with 8-bit grayscaling support implemented. The implementation was developed using reference code from [uPatternScope](https://github.com/santkumar/uPatternScope) and assistance from Claude Sonnet 4.5.

## Features

- **1-bit and 8-bit Image Projection**: Binary patterns and 256-level grayscale
- **Pattern On-The-Fly Mode**: Upload and display image sequences via USB
- **Flexible Timing Control**: Independent exposure times, dark times, and triggers
- **Fast Image Encoding**: Enhanced Run-Length Encoding (ERLE) for efficient data transfer
- **Multiple Example Scripts**: Ready-to-use examples for various use cases
- **Cross-Platform**: Compatible with Windows, macOS, and Linux

## Requirements

- **Python**: 2.x or 3.x (tested up to 3.8)
- **Dependencies**:
  - `pyusb` - USB communication
  - `numpy` - Array operations
  - `PIL/pillow` - Image loading and processing
  - `cv2` (optional) - Additional image processing
  - `ttkthemes` - For the gui

### Driver Installation

**Windows Users**: Install USB drivers using [Zadig](http://zadig.akeo.ie/)
- Select the DLP LightCrafter 6500 device
- Choose `WinUSB` driver (recommended for modern systems)
- If you encounter issues, try `libusbK` or `libusb-win32` as fallbacks
- Click "Install Driver"

**Linux/macOS**: libusb should work out of the box

## Installation

```bash
# Install dependencies
pip install pyusb numpy pillow opencv-python ttkthemes

## Quick Start

### Basic Connection

```python
import pycrafter6500

# Connect to DMD
dlp = pycrafter6500.dmd()

# Set to pattern on-the-fly mode
dlp.changemode(3)
```

### Project a 1-bit Binary Image

```python
import numpy as np
from PIL import Image

# Load and convert image to binary
img = Image.open("image.png").convert('L').resize((1920, 1080))
img_array = np.array(img) // 129  # Convert to 0 or 1

# Define sequence
images = [img_array]
exposure = [4046]  # microseconds
trigger_in = [False]
dark_time = [0]
trigger_out = [1]

dlp.defsequence(images, exposure, trigger_in, dark_time, trigger_out, 0)
dlp.startsequence()
```

### Project an 8-bit Grayscale Image

```python
import numpy as np
from PIL import Image

# Load 8-bit grayscale image
img = Image.open("photo.tif").convert('L').resize((1920, 1080))
img_array = np.array(img, dtype=np.uint8)  # Keep 0-255 values

# Define 8-bit sequence
images = [img_array]
exposure = [4046]  # microseconds
trigger_in = [False]
dark_time = [0]
trigger_out = [1]

dlp.defsequence_8bit(images, exposure, trigger_in, dark_time, trigger_out, 0)
dlp.startsequence()
```

## Graphical User Interface (GUI)

A modern GUI application is included for easy control of the DMD without writing code.

### Launching the GUI

```bash
python3 gui.py
```

### GUI Features

- **Three Projection Modes**:
  - **Sequence Mode**: Cycle through up to 24 x 1-bit images continuously
  - **Constant Mode**: Project a single selected image (1-bit or 8-bit)
  - **Pulsed Projection**: Alternate through images with individual timing control

- **Image Management**:
  - Add multiple images with preview
  - Per-image settings (mode, exposure, dark time, duration)
  - Drag-and-drop image reordering (select and manage)

- **Flexible Timing**:
  - Time units: seconds, minutes, or hours
  - Bidirectional runtime/cycles calculation in pulsed mode
  - Individual duration settings per image

- **Demo Mode**: Test all features without hardware
- **Modern Theme**: Professional arc theme using ttkthemes
- **Progress Logging**: Full-width log with execution block separation

### GUI Requirements

The GUI requires one additional dependency:
```bash
pip install ttkthemes
```

## API Reference

### Core Methods

#### `dmd()`
Initialize connection to the DMD.

#### `changemode(mode)`
Set DMD operating mode:
- `0` - Normal video mode
- `1` - Pre-stored pattern mode
- `2` - Video pattern mode
- `3` - Pattern on-the-fly mode (recommended)

#### `defsequence(images, exposure, trigger_in, dark_time, trigger_out, repetitions)`
Define a sequence for **1-bit binary** images.

**Parameters:**
- `images`: List of numpy arrays (1080×1920, dtype=uint8, values 0-1)
- `exposure`: List of exposure times in microseconds
- `trigger_in`: List of booleans for external trigger input
- `dark_time`: List of dark times in microseconds
- `trigger_out`: List of integers for trigger output
- `repetitions`: Number of repetitions (0 = infinite)

#### `defsequence_8bit(images, exposure, trigger_in, dark_time, trigger_out, repetitions)`
Define a sequence for **8-bit grayscale** images.

**Parameters:**
- `images`: List of numpy arrays (1080×1920, dtype=uint8, values 0-255)
- Other parameters same as `defsequence()`

**Note:** Currently supports 1 image at a time for 8-bit mode.

#### Sequence Control

```python
dlp.startsequence()   # Start projection
dlp.pausesequence()   # Pause projection
dlp.stopsequence()    # Stop projection
```

#### Power Management

```python
dlp.idle_on()    # Enter idle mode
dlp.idle_off()   # Exit idle mode
dlp.standby()    # Enter standby
dlp.wakeup()     # Wake from standby
dlp.reset()      # Reset DMD
```

## Folder Structure

```
Pycrafter6500_pulsed/
├── README.md                    # This file
├── pycrafter6500.py            # Main library
├── erle.py                     # Image encoding module
├── license.txt                 # License information
├── examples/                   # Example scripts
│   ├── constant_projection.py
│   └── pulsed_projection.py
└── images/                     # Sample images
    ├── image1.png
    ├── image2.png
    ├── hhu.tif
    └── ...
```

## Example Scripts

All example scripts are located in the `examples/` folder and can be run from anywhere in the repository.

### 1. `constant_projection.py`
Continuously project a single 8-bit grayscale image (uses `images/hhu.tif`).

**Features:**
- 8-bit grayscale projection
- Infinite loop (press Ctrl+C to stop)
- Automatic image resizing to DMD resolution

**Usage:**
```bash
python examples/constant_projection.py
```

### 2. `pulsed_projection.py`
Alternate between two images with configurable durations and modes. Perfect for timed experiments.

**Features:**
- Supports both 1-bit and 8-bit modes
- Configurable duration for each image
- Automatic cycle calculation based on total runtime
- Progress tracking with elapsed and remaining time
- Mixed mode support (e.g., 8-bit image1, 1-bit image2)

**Configuration:**
```python
IMAGE1_PATH = os.path.join(script_dir, "..", "images", "image1.png")
IMAGE2_PATH = os.path.join(script_dir, "..", "images", "image2.png")
IMAGE1_DURATION_SEC = 29 * 60  # 29 minutes
IMAGE2_DURATION_SEC = 1 * 60   # 1 minute
TOTAL_RUNTIME_MIN = 24 * 60    # 24 hours

IMAGE1_MODE = '8bit'  # or '1bit'
IMAGE2_MODE = '1bit'  # or '8bit'
```

**Usage:**
```bash
python examples/pulsed_projection.py
```

**Example Output:**
```
============================================================
Timed Alternating Image Projection (8-bit Support)
============================================================
Image 1: image1.png (8bit) - Duration: 1740 sec (29.0 min)
Image 2: image2.png (1bit) - Duration: 60 sec (1.0 min)
Cycle duration: 1800 sec (30.0 min)
Total runtime: 1440 min (24.0 hours)
Total cycles: 48
============================================================
```

## 8-bit Grayscale: How It Works

The DMD achieves 8-bit grayscale through **Binary Pulse Width Modulation (PWM)**:

1. **Bit Plane Decomposition**: The 8-bit image is decomposed into 8 binary bit planes
2. **Weighted Display**: Each bit plane is displayed with exposure time weighted by powers of 2:
   - Bit 0 (LSB): 1× exposure
   - Bit 1: 2× exposure
   - Bit 2: 4× exposure
   - ...
   - Bit 7 (MSB): 128× exposure
3. **Visual Integration**: The human eye integrates these rapid flashes to perceive grayscale

### 1-bit vs 8-bit Comparison

| Feature | 1-bit | 8-bit |
|---------|-------|-------|
| **Grayscale Levels** | 2 (black/white) | 256 |
| **Pixel Values** | 0-1 | 0-255 |
| **Display Method** | Single binary pattern | 8 bit planes with PWM |
| **Typical Exposure** | ~4ms | ~100ms |
| **Use Case** | Fast patterns, masks | Photos, gradients |
| **Batch Support** | Up to 24 images | 1 image (current) |

## Image Requirements

### Resolution
- **Native DMD Resolution**: 1920 × 1080 pixels
- Images are automatically resized if needed

### Data Format
- **1-bit**: `numpy.uint8` with values 0 or 1
- **8-bit**: `numpy.uint8` with values 0-255
- **Color**: Automatically converted to grayscale

### Supported Formats
- PNG, JPEG, TIFF, BMP, and other PIL-supported formats

## Troubleshooting

### DMD Not Detected
- Ensure USB cable is connected
- Check that libusb drivers are installed (Windows)
- Verify device appears in Device Manager / lsusb

### Image Too Bright/Dark
- **1-bit**: Adjust threshold when converting (default: `//129`)
- **8-bit**: Adjust `exposure` parameter in microseconds

### "8-bit mode currently supports only 1 image at a time"
- Pass a list with exactly one image: `images = [img_array]`
- For multiple images, call `defsequence_8bit()` separately for each

### Image Has Artifacts
- Ensure image is properly resized to 1920×1080
- Check that dtype is `uint8`
- Verify pixel values are in correct range (0-1 for 1-bit, 0-255 for 8-bit)

### Slow Performance
- The ERLE encoder provides significant speedup
- Reduce image count or use lower resolution for testing
- Ensure USB connection is stable

## Technical Details

### Modified Files

**`pycrafter6500.py`**
- Core DMD controller class
- `defsequence()` for 1-bit images
- `defsequence_8bit()` for 8-bit images

**`erle.py`**
- Enhanced Run-Length Encoding for image compression, modified in this fork with the merge_8bit() and encode_8bit() functions
- `encode()` for 1-bit binary images
- `encode_8bit()` for 8-bit grayscale images
- `merge()` and `merge_8bit()` for image merging

### USB Communication
- Uses HID protocol over USB
- Vendor ID: `0x0451`
- Product ID: `0xc900`
- Buffer size: 64 bytes

### Image Encoding
Images are encoded using Enhanced Run-Length Encoding (ERLE) as specified in the DLPC900 Programmer's Guide:
- Header: 52 bytes (signature, dimensions, compression type)
- Compression: Type 0x02 (Enhanced RLE)
- Format: 24-bit BGR (0x00BBGGRR)

## Credits and Citations

**Original Library**: Pycrafter6500  
**8-bit Support**: Extended implementation based on MATLAB DMD driver

**Contributors:**
- Guangyuan Zhao - Python 3.x compatibility
- Ashu (@e841018) - Fast ERLE encoder

**References:**
- [DLPC900 Programmer's Guide](http://www.ti.com/lit/ug/dlpu018b/dlpu018b.pdf)
- [Enhanced Run-Length Encoding (ERLE)](https://github.com/e841018/ERLE)

### Scientific Usage

If you use this library for scientific publications, please cite:
- Original work: https://doi.org/10.1364/OE.25.000949
- uPatternScope: https://doi.org/10.1038/s41467-024-54351-6

## License

See `license.txt` for details.

## Support

For issues, questions, or contributions, please open an issue on the repository.

---

**Version**: 1.1 (with 8-bit grayscale support)  
**Last Updated**: October 2025
