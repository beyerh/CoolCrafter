# CoolCrafter - Synchronized DMD & LED Control for Optogenetics

**Designed for [uPatternScope](https://github.com/santkumar/uPatternScope)** - an optogenetic microscopy platform for spatiotemporal illumination control.

Integrated control system for the **TI DLP LightCrafter 6500** (DMD) and **CoolLED pE-4000** (LED illumination). Provides synchronized projection and LED control for optogenetic experiments with precise spatial and temporal control. Implemented with Claude Sonnet 4.5.

**Built on:**
- [Pycrafter6500](https://github.com/csi-dcsc/Pycrafter6500) - DMD control foundation
- [uPatternScope](https://github.com/santkumar/uPatternScope) - 8-bit grayscale support and optogenetic workflows
- [CoolLED_control](https://github.com/philglock/CoolLED_control) - LED integration

## Applications

Two main applications for different use cases:

### **CoolCrafter_gui.py** (Main Application)
**Synchronized DMD + LED control** for integrated optogenetic experiments.
- Controls both DMD projection and LED illumination simultaneously
- Per-image LED wavelength and intensity settings (4 independent channels)
- Four projection modes: Sequence, Constant, Pulsed, Nikon NIS Trigger
- Real-time projection timer with progress tracking
- Nikon NIS Trigger mode for synchronized time-lapse experiments with Nikon NIS software
- **Use this for synchronized optogenetic stimulation**

### **CoolLED_gui.py** (LED Standalone)
**CoolLED pE-4000 control** for LED illumination without DMD.
- Independent 4-channel control (A, B, C, D)
- Wavelength selection per channel:
  - Channel A: UV range (365-435nm)
  - Channel B: Blue range (460-500nm)
  - Channel C: Green/Yellow range (525-595nm)
  - Channel D: Red/NIR range (635-770nm)
- Real-time intensity adjustment (0-100%) per channel
- Built-in function generator for dynamic illumination patterns
- Live connection status and device info
- Auto-detection of serial port and baud rate
- **Use this for testing LED modules, calibrating intensities, or standalone illumination experiments**

## Screenshot

<img src="doc/screen.png" alt="CoolCrafter GUI" width="800"/>

*CoolCrafter main interface showing synchronized DMD and LED control with image preview, per-image LED settings, and real-time projection status.*

## Quick Start

### Installation

```bash
# Install dependencies
pip install pyusb pyserial numpy pillow ttkthemes
```

**Windows USB Drivers (DMD)**: Install using [Zadig](http://zadig.akeo.ie/)
- Options → List All Devices → Select DLPC900
- Choose `libusb-win32` or `libusbK` driver → Install

**CoolLED pE Driver**: Required for CoolLED pE-4000 control
- Download: [CoolLED pE Driver](https://www.coolled.com/support/imaging-software/#coolled-pe-driver)


### Launch Applications

**Launcher (Recommended):**
```bash
python launcher.py
```
A simple menu will appear allowing you to choose which application to start or access the GitHub repository.

**Direct Launch:**
```bash
# Main synchronized app (DMD + LED)
python CoolCrafter_gui.py

# LED only
python CoolLED_gui.py
```

**Windows Users**: Double-click `launch_gui.bat` or `launch_gui.vbs` to start the launcher. See [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for creating desktop shortcuts and taskbar pinning.

## Key Features

**DMD Control:**
- 1-bit (binary) and 8-bit (256-level grayscale) projection
- Pattern-on-the-fly mode: up to 400×1-bit or ~25×8-bit images (depending on file size,test and define in the settings)
- Flexible timing: per-image exposure, dark time, duration
- Four projection modes: Sequence, Constant, Pulsed, Nikon NIS Trigger
- Real-time upload progress feedback for large sequences
- File-based synchronization with Nikon NIS for time-lapse experiments

**CoolLED Integration:**
- 4 independent channels (A, B, C, D)
- Wavelength selection: UV (365-435nm), Blue (460-500nm), Green/Yellow (525-595nm), Red/NIR (635-770nm)
- Per-channel intensity control (0-100%)
- Synchronized with DMD projection timing
- Automatic LED switching in Nikon NIS Trigger mode


## Projection Modes

### **Sequence Mode**
Pre-upload all patterns to DMD memory for fast, hardware-controlled cycling.
- **Best for**: High-speed pattern switching, synchronized sequences
- **Upload**: Once at beginning
- **Switching**: Instant (hardware-controlled)
- **Limits**: 400×1-bit or 25×8-bit patterns

### **Constant Mode**
Project a single pattern continuously.
- **Best for**: Static illumination, single-pattern experiments
- **Upload**: Once at beginning
- **Duration**: Configurable time or infinite

### **Pulsed Mode**
Cycle through patterns with flexible per-image timing.
- **Best for**: Long exposures (>5s), flexible timing
- **Upload**: On-demand (each pattern uploaded when needed)
- **Switching**: 2-5 second delay per pattern
- **LED**: Fully synchronized with automatic channel switching

### **Nikon NIS Trigger Mode** 
File-based synchronization with Nikon NIS for automated time-lapse experiments.
- **Best for**: Integrated time-lapse imaging with Nikon NIS
- **Upload**: On-demand (triggered by Nikon macros)
- **Control**: Via text files written by Nikon NIS macros
  - `trigger_on_off.txt`: Start/stop projection (0=off, 1=on)
  - `trigger_next.txt`: Advance to next pattern (increment value)
- **LED**: Fully synchronized with automatic channel switching
- **Macros**: Nikon NIS macros in `NIS_AR_macro/` folder:
  - `trigger_on_next.mac` - Starts projection + advances to next pattern (for time-lapse)
  - `trigger_off.mac` - Stops projection
  - `trigger_on.mac` - Starts projection
  1. Load patterns in CoolCrafter
  2. Start Nikon NIS Trigger mode
  3. Run Nikon NIS time-lapse with macros
  4. Macros control CoolCrafter via trigger files
  5. Patterns switch automatically at each timepoint

#### **Setup for Nikon NIS Time-Lapse Experiments** 
**Recommended for time-lapse imaging with pattern switching:**

1. **Configure trigger file paths:**
   - In CoolCrafter: Go to Settings → Configuration
   - Set paths for `trigger_on_off.txt` and `trigger_next.txt`
   - Create these empty text files at the specified location or copy them from the `NIS_AR_macro/` folder

2. **Install Nikon NIS macros:**
   - Copy the macros (*.mac files) from `NIS_AR_macro/` folder into the Nikon NIS Elements macro folder (e.g., `C:\Program Files\Nikon\NIS Elements\Macro`)
   - Edit the file paths inside the macros to match your trigger file location, consider modifying the 'Wait time'

3. **Optional: Generate NIS Macro Panel:**
   - In NIS, go to **Macro → Load Macro Panel**
   - Select the macros and they will appear as buttons in a panel for convenient DMD control

4. **Time-lapse setup:**
   - Start Nikon NIS Trigger mode in CoolCrafter (enable "Start with black frame" option)
   - Configure your time-lapse experiment in NIS Elements
   - Assign `trigger_on_next.mac` to **Before Loop** or **Before Capture** event
   - Assign `trigger_off.mac` to **After Loop** or **After Capture** event
   - Each time point will automatically trigger the next DMD pattern with synchronized LED

## Example Scripts

Ready-to-use Python scripts for common projection tasks:

### **`examples/constant_projection.py`**
Continuously project a single 8-bit grayscale image.

### **`examples/pulsed_projection.py`**
Alternate between two images with configurable timing.

**For GUI users**: Use **CoolCrafter_gui.py** for interactive control with LED synchronization!

## Project Structure

```
CoolCrafter/
├── CoolCrafter_gui.py             # Main app (DMD + LED)
├── CoolLED_gui.py                 # LED standalone
├── pycrafter6500.py               # DMD controller library
├── erle.py                        # Image encoding (ERLE)
├── launcher.py                    # Application launcher with GitHub link
├── examples/
│   ├── constant_projection.py     # Single image projection
│   └── pulsed_projection.py       # Timed alternating projection
├── NIS_AR_macro/                  # Nikon NIS macros for trigger mode
│   ├── trigger_on.mac             # Start projection macro, copy to NIS Elements macro folder
│   ├── trigger_off.mac            # Stop projection macro, copy to NIS Elements macro folder
│   └── trigger_on_next.mac        # Advance pattern macro, copy to NIS Elements macro folder
│   ├── trigger_on_off.txt         # Start/stop projection (0=off, 1=on)
│   ├── trigger_next.txt           # Advance pattern (increment value)
└── images/                        # Test images
```

## Technical Notes

**8-bit Grayscale**: Uses Binary PWM - image decomposed into 8 bit planes, each displayed with weighted exposure (1×, 2×, 4×, ... 128×).

**Image Requirements**: 1920×1080 (auto-resized), PNG/JPEG/TIFF/BMP, numpy arrays with 0-1 (1-bit) or 0-255 (8-bit)

**Pattern Upload**: Images are uploaded in reverse order as required by DLPC900 hardware. The GUI provides real-time progress feedback, especially useful for large 8-bit sequences.

**Pattern Limits** (configurable in Settings menu):
- **1-bit mode**: Up to 400 patterns (default, processed in batches of 24)
- **8-bit mode**: Up to 25 patterns (default, each pattern ~370KB compressed, ~9MB total)
- Limits can be adjusted in Settings → Configuration based on your hardware stability

**Exposure Limits** (configurable in Settings menu):
- **Sequence/Constant modes**: Hardware exposure limited to ~3-5 seconds (hardware-dependent)
  - Max safe exposure and max recommended exposure can be customized via Edit → Settings
  - Default limits based on typical DLPC900 hardware capabilities
- **Pulsed mode**: No exposure limit - uses software-controlled duration for any length

**Upload Performance**:
- 1-bit sequences: Fast (~seconds for 400 patterns)
- 8-bit sequences: ~3-5 minutes for 25 patterns (with progress feedback)

**Tip**: For projections longer than a few seconds, use Pulsed mode with the duration parameter!

## Hardware Testing

Test your hardware's maximum exposure time (relevant for Sequence/Constant modes):

```bash
python determine_max_exposure.py
```

**See [HARDWARE_TESTING.md](HARDWARE_TESTING.md) for detailed testing instructions, troubleshooting, and configuration examples.**



## Version History

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

**Latest (v0.2):** Fixed critical upload bug, increased pattern limits (400×1-bit, 25×8-bit), added real-time progress feedback, Nikon NIS Trigger mode.

## Credits

Based on [Pycrafter6500](https://github.com/csi-dcsc/Pycrafter6500) with 8-bit support from [uPatternScope](https://github.com/santkumar/uPatternScope). CoolLED integration based on [CoolLED_control](https://github.com/philglock/CoolLED_control). Uses [ERLE encoding](https://github.com/e841018/ERLE) for image compression.

**References:**
- uPatternScope: [DOI: 10.1038/s41467-024-54351-6](https://doi.org/10.1038/s41467-024-54351-6)
- Original Pycrafter: [DOI: 10.1364/OE.25.000949](https://doi.org/10.1364/OE.25.000949)
- CoolLED Control: [philglock/CoolLED_control](https://github.com/philglock/CoolLED_control)
- TI DLPC900: [Programmer's Guide](http://www.ti.com/lit/ug/dlpu018b/dlpu018b.pdf)

---

**License**: See `license.txt` | **Version**: 0.2 (CoolCrafter) | November 2025
