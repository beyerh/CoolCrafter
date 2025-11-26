# Windows Desktop Integration Guide

This guide shows you how to create a desktop icon and pin the CoolCrafter GUI applications to your Windows taskbar.

**Available Applications:**
- `CoolCrafter_gui.py` - Main app (synchronized DMD + LED control)
- `CoolLED_gui.py` - LED standalone control
- `launcher.py` - Application launcher with GitHub link

## Quick Launch Options

### Option 1: Use the Launcher (Recommended)

A launcher application is provided to easily access all features:

- **`launcher.py`** - Main launcher with GUI interface
- **`launch_gui.bat`** - Console launcher (shows debug output)
- **`launch_gui.vbs`** - Silent launcher (no console window)

Simply double-click any of these files to start the launcher and choose your application.

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

