# Windows Desktop Integration Guide

This guide shows you how to create a desktop icon and pin the CoolCrafter GUI applications to your Windows taskbar.

**Available Applications:**
- `CoolCrafter_gui.py` - Main app (synchronized DMD + LED control)
- `Pycrafter6500_gui.py` - DMD standalone control
- `CoolLED_gui.py` - LED standalone control

## Quick Launch Options

### Option 1: Double-Click Launchers (Included)

Two launcher files are provided for convenience:

- **`launch_gui.bat`** - Shows a console window (useful for debugging)
- **`launch_gui.vbs`** - Runs silently without console window (recommended)

Simply double-click either file to launch the GUI!

---

## Creating a Desktop Shortcut (Recommended)

### Step 1: Create the Shortcut

1. Right-click on `launch_gui.vbs` (or `launch_gui.bat`)
2. Select **"Create shortcut"**
3. Drag the shortcut to your Desktop

### Step 2: Customize the Shortcut

1. Right-click the shortcut → **Properties**
2. Click **"Change Icon..."**
3. Browse and select an icon (or use default)
4. Optionally rename: `CoolCrafter` (or `DMD Controller`, `LED Controller` for standalone apps)
5. Click **OK**

### Step 3: Pin to Taskbar

1. Right-click the desktop shortcut
2. Select **"Pin to taskbar"**
3. Done! Now you can launch with one click from the taskbar