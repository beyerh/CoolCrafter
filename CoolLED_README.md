# CoolLED pE-4000 GUI Controller

A modern GUI application for controlling the CoolLED pE-4000 four-channel LED illumination system.

## Features

- **4-Channel Control**: Independent control of all 4 channels (A-D)
- **Wavelength Selection**: Each channel can select from 4 specific wavelengths
  - Channel A: 365, 385, 395, 405 nm
  - Channel B: 425, 445, 460, 470 nm  
  - Channel C: 500, 525, 550, 575 nm
  - Channel D: 635, 660, 740, 770 nm
- **Intensity Control**: 0-100% intensity adjustment with real-time sliders
- **Color-Coded Display**: Dynamic color coding based on selected wavelength
- **Demo Mode**: Test all features without hardware
- **Quick Presets**: One-click activation of individual channels
- **Status Logging**: Real-time log of all operations

## Hardware Communication

The GUI uses the official CoolLED pE-4000 serial protocol:

- **Baud Rate**: 57600 (fallback to 38400)
- **Terminator**: `\r` (carriage return)
- **Commands**:
  - `LAMBDAS` - Query available wavelengths
  - `LOAD:<nm>` - Load wavelength into appropriate channel
  - `CSSxSNnnn` - Set channel x ON with intensity nnn (000-100)
  - `CSSxSF` - Turn channel x OFF
  - `CSN` - Turn all channels ON
  - `CSF` - Turn all channels OFF
  - `CSS?` - Query channel status

## Usage

### Connecting to Hardware

1. Connect the CoolLED pE-4000 via USB
2. Click the **Connect** button
3. The application will auto-detect the device and display connection info
4. If no device is found, you can enable **Demo Mode** to test the interface

### Controlling Channels

For each channel:

1. **Select Wavelength**: Choose from 4 available wavelengths in the dropdown
2. **Adjust Intensity**: Use the slider to set 0-100% intensity
3. **Turn ON**: Click the ON button to activate the channel
4. **Turn OFF**: Click the OFF button to deactivate

### Quick Presets

Use the preset buttons to quickly activate a single channel:
- **Channel A Only**: UV range (365-405nm)
- **Channel B Only**: Blue range (425-470nm)
- **Channel C Only**: Green/Yellow range (500-575nm)
- **Channel D Only**: Red/NIR range (635-770nm)

### Global Controls

- **All Channels ON**: Activate all channels with their current settings
- **All Channels OFF**: Deactivate all channels simultaneously

## Architecture

### Class Structure

#### `CoolLEDController`
Handles serial communication with the hardware:
- Connection management
- Command sending/receiving
- Wavelength loading
- Intensity and state control

#### `CoolLEDGUI`
Main GUI application:
- tkinter-based interface
- Channel control panels
- Status monitoring
- Event handling

### Wavelength Configuration

Wavelengths are organized by channel in `CHANNEL_WAVELENGTHS` dictionary:

```python
CHANNEL_WAVELENGTHS = {
    'A': {'365nm': {...}, '385nm': {...}, '395nm': {...}, '405nm': {...}},
    'B': {'425nm': {...}, '445nm': {...}, '460nm': {...}, '470nm': {...}},
    'C': {'500nm': {...}, '525nm': {...}, '550nm': {...}, '575nm': {...}},
    'D': {'635nm': {...}, '660nm': {...}, '740nm': {...}, '770nm': {...}}
}
```

Each wavelength entry includes:
- `wavelength`: Numeric value (nm)
- `color`: Hex color code for display
- `name`: Display name

## Integration with Pycrafter GUI

The CoolLED controller can be integrated into the Pycrafter6500 GUI for synchronized DMD and illumination control.

### Integration Approach

#### Option 1: Separate Window (Recommended for Testing)
Keep CoolLED as a separate window that can be launched from the main Pycrafter GUI:

```python
# In gui.py, add to menu or control panel:
def launch_coolled_controller(self):
    import subprocess
    subprocess.Popen(['python', 'CoolLED_gui.py'])
```

#### Option 2: Embedded Panel
Integrate CoolLED controls as an additional panel in the Pycrafter GUI:

```python
# Add to DMDControllerGUI.__init__():
from CoolLED_gui import CoolLEDController, CHANNEL_WAVELENGTHS

self.coolled_controller = None
self.create_coolled_panel(main_frame)  # Add panel

def create_coolled_panel(self, parent):
    coolled_frame = ttk.LabelFrame(parent, text="CoolLED Illumination", padding="10")
    # Add channel controls here
```

#### Option 3: Synchronized Sequences
For advanced use, synchronize DMD patterns with LED wavelength switching:

```python
# Sequence format:
sequence = [
    {'image': 'pattern1.png', 'wavelength': 365, 'channel': 'A', 'exposure': 100},
    {'image': 'pattern2.png', 'wavelength': 470, 'channel': 'B', 'exposure': 100},
    # ...
]
```

### Shared Resources

Both GUIs use similar design patterns:
- ttk/ttkthemes for styling
- 3-panel layout (controls, preview, status)
- Demo mode for testing
- Status logging

## Customization

### Adding New Wavelengths

If your pE-4000 has different wavelengths installed, update `CHANNEL_WAVELENGTHS`:

```python
CHANNEL_WAVELENGTHS = {
    'A': {
        '340nm': {'wavelength': 340, 'color': '#8000FF', 'name': '340nm UV'},
        # ... your wavelengths
    },
    # ...
}
```

### Adjusting Colors

Color codes can be adjusted for better visual representation:

```python
'365nm': {'wavelength': 365, 'color': '#YOUR_HEX_COLOR', 'name': '365nm UV'}
```

## Troubleshooting

### Connection Issues

**Problem**: "No CoolLED device found"
- **Solution**: Check USB connection, verify device is powered on
- **Alternative**: Use Demo Mode to test GUI functionality

**Problem**: "Communication errors"
- **Solution**: Try both baud rates (57600, 38400), check cable quality

### Wavelength Loading

**Problem**: "Channel won't light up"
- **Solution**: Ensure wavelength is loaded before turning ON
- **Tip**: The GUI automatically loads wavelengths when you click ON

### Performance

**Problem**: "Slow response"
- **Solution**: Reduce command frequency, add delays between operations
- **Note**: Hardware needs 10-50ms between commands

## Command Reference

### Loading Wavelengths
```python
controller.load_wavelength(470)  # Load 470nm
```

### Controlling Intensity
```python
controller.set_intensity('A', 75)  # Channel A at 75%
```

### Turning Channels On/Off
```python
controller.turn_on('A', intensity=50)
controller.turn_off('A')
```

### Global Commands
```python
controller.all_on()   # All channels ON
controller.all_off()  # All channels OFF
```

### Query Status
```python
status = controller.get_status()  # Returns: CSSASN075BSF000...
```

## Future Enhancements

Potential improvements for future versions:

1. **Sequence Programming**: Define time-based wavelength sequences
2. **TTL Trigger Support**: Hardware-synchronized switching
3. **Intensity Ramping**: Gradual intensity changes
4. **Save/Load Presets**: Store frequently used configurations
5. **Multi-device Support**: Control multiple pE-4000 units
6. **Python API**: Programmatic control for automation scripts

## License

This software is provided for research and educational purposes. Check CoolLED documentation for hardware warranty and usage terms.

## References

- CoolLED pE-4000 User Manual (DOC-008)
- CoolLED Command Reference Manual (DOC-038)
- Pycrafter6500 Documentation

---

**Version**: 1.0
**Last Updated**: 2025-10-08
**Author**: Generated for research microscopy automation
