"""
GUI Application for Pycrafter6500-8bit DMD Controller
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from ttkthemes import ThemedTk
from PIL import Image, ImageTk
import numpy as np
import os, threading, time
import serial
import serial.tools.list_ports
import glob
import sys
import pycrafter6500
from pycrafter6500 import MAX_SAFE_EXPOSURE_US, MAX_RECOMMENDED_EXPOSURE_US

# CoolLED Wavelength Configuration (Channel -> Available Wavelengths)
CHANNEL_WAVELENGTHS = {
    'A': [365, 385, 405, 435],  # UV range
    'B': [460, 470, 490, 500],  # Blue range
    'C': [525, 550, 580, 595],  # Green/Yellow range
    'D': [635, 660, 740, 770]   # Red/NIR range
}

class CoolLEDController:
    """Serial communication handler for CoolLED pE-4000"""
    
    def __init__(self, port):
        self.port = port
        self.serial = None
        self.connected = False
        
    def connect(self):
        """Establish serial connection"""
        try:
            for baud in [57600, 38400]:
                try:
                    self.serial = serial.Serial(self.port, baud, timeout=1.0)
                    time.sleep(0.2)
                    
                    # Clear any buffered data
                    self.serial.reset_input_buffer()
                    self.serial.reset_output_buffer()
                    
                    version = self.get_version()
                    if version and len(version) > 0:
                        self.connected = True
                        # Extract just the firmware version number
                        fw_version = "Unknown"
                        if 'XFW_VER=' in version:
                            fw_version = version.split('XFW_VER=')[1].split('\r')[0].split('\n')[0]
                        return True, f"FW v{fw_version} @ {baud} baud"
                    self.serial.close()
                except Exception as ex:
                    print(f"Connection attempt failed on {self.port} @ {baud}: {ex}")
                    if self.serial and self.serial.is_open:
                        self.serial.close()
                    continue
            return False, "No response from device"
        except Exception as e:
            return False, str(e)
    
    def disconnect(self):
        """Close serial connection"""
        if self.serial:
            self.all_off()
            self.serial.close()
            self.serial = None
        self.connected = False
    
    def send_command(self, command):
        """Send command and return response"""
        if not self.serial:
            return None
        try:
            self.serial.write(f"{command}\r".encode('utf-8'))
            time.sleep(0.05)
            response = self.serial.readline().decode('utf-8').strip()
            return response
        except Exception as e:
            print(f"CoolLED command error: {e}")
            return None
    
    def get_version(self):
        """Query firmware version"""
        try:
            # Send XVER command
            self.serial.write(b"XVER\r")
            time.sleep(0.2)
            # Read multiple lines since response has multiple lines
            response = self.serial.read(200).decode('utf-8', errors='ignore').strip()
            return response
        except Exception as e:
            print(f"get_version error: {e}")
            return None
    
    def load_wavelength(self, wavelength_nm):
        """Load a wavelength (automatically selects correct channel)"""
        response = self.send_command(f"LOAD:{wavelength_nm}")
        return response
    
    def set_intensity(self, channel, intensity):
        """Set channel intensity and turn ON (0-100%)"""
        intensity_str = f"{int(intensity):03d}"
        response = self.send_command(f"CSS{channel}SN{intensity_str}")
        return True
    
    def turn_off(self, channel):
        """Turn channel OFF"""
        response = self.send_command(f"CSS{channel}SF")
        return True
    
    def all_off(self):
        """Turn all channels OFF"""
        response = self.send_command("CSF")
        return True
    
    @staticmethod
    def find_devices():
        """Find connected CoolLED devices"""
        devices = []
        
        # First, try using serial.tools.list_ports to find CoolLED devices
        try:
            ports_info = list(serial.tools.list_ports.comports())
            for port_info in ports_info:
                # Check if description contains "CoolLED"
                if "CoolLED" in port_info.description or "CoolLED" in str(port_info.manufacturer):
                    print(f"Found CoolLED device: {port_info.device} - {port_info.description}")
                    devices.append(port_info.device)
            
            if devices:
                return devices
        except Exception as e:
            print(f"Error using list_ports: {e}")
        
        # Fallback: scan all ports
        if sys.platform.startswith('win'):
            ports = [f'COM{i+1}' for i in range(20)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            ports = glob.glob('/dev/tty[A-Za-z]*')
        elif sys.platform.startswith('darwin'):
            ports = glob.glob('/dev/tty.*')
        else:
            return devices
        
        for port in ports:
            # Try both common baud rates
            for baud in [57600, 38400]:
                try:
                    ser = serial.Serial(port, baud, timeout=0.5)
                    time.sleep(0.1)
                    
                    # Try reading initial response
                    initial = ser.readline()
                    if b'CoolLED' in initial:
                        devices.append(port)
                        ser.close()
                        break
                    
                    # Try XVER command with correct terminator
                    ser.write(b'XVER\r')
                    time.sleep(0.2)
                    response = ser.read(200)
                    
                    if b'XFW_VER' in response or b'XUNIT' in response:
                        devices.append(port)
                        ser.close()
                        break
                    
                    ser.close()
                except (OSError, serial.SerialException):
                    if 'ser' in locals() and ser and ser.is_open:
                        ser.close()
                    continue
        
        return devices

class ImageItem:
    def __init__(self, filepath, mode='1bit'):
        self.filepath = filepath
        self.mode = mode
        self.exposure = 4046 if mode == '8bit' else 105
        self.dark_time = 0
        self.trigger_in = False
        self.trigger_out = 1
        self.duration = 60
        self.image_array = None
        self.thumbnail = None
        self.thumbnail_mirrored = None
        self._pil_image = None  # Cache PIL image for faster reloading
        # CoolLED illumination settings - support 4 channels
        self.led_enabled = False
        self.led_channels = {
            'A': {'enabled': False, 'wavelength': 365, 'intensity': 50},
            'B': {'enabled': False, 'wavelength': 460, 'intensity': 50},
            'C': {'enabled': False, 'wavelength': 525, 'intensity': 50},
            'D': {'enabled': False, 'wavelength': 635, 'intensity': 50}
        }
    
    def load_image(self, force_reload=False):
        """Load full image array. Only loads once unless force_reload=True"""
        if self.image_array is not None and not force_reload:
            return self.image_array  # Already loaded
        
        img = Image.open(self.filepath)
        if img.mode != 'L': img = img.convert('L')
        if img.size != (1920, 1080): img = img.resize((1920, 1080), Image.LANCZOS)
        self._pil_image = img  # Cache for thumbnail generation
        img_array = np.array(img)
        self.image_array = img_array // 129 if self.mode == '1bit' else img_array.astype(np.uint8)
        return self.image_array
    
    def load_thumbnail(self):
        """Load thumbnail for preview. Fast, lightweight operation"""
        if self.thumbnail is not None:
            return  # Already loaded
        
        # Use cached PIL image if available, otherwise load just for thumbnail
        if self._pil_image is not None:
            img = self._pil_image
        else:
            img = Image.open(self.filepath)
            if img.mode != 'L': img = img.convert('L')
        
        # Create thumbnail maintaining exact 16:9 aspect ratio (1920:1080)
        thumb = img.copy()
        thumb.thumbnail((480, 270), Image.LANCZOS)
        self.thumbnail = ImageTk.PhotoImage(thumb)
        # Also create mirrored version
        thumb_mirrored = thumb.transpose(Image.FLIP_LEFT_RIGHT)
        self.thumbnail_mirrored = ImageTk.PhotoImage(thumb_mirrored)

# Version info
VERSION = "0.2"
APP_NAME = "CoolCrafter"
GITHUB_URL = "https://github.com/beyerh/CoolCrafter"

class DMDControllerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{VERSION} - DMD Controller")
        self.root.geometry("1400x880")  # Optimized height
        
        # Apply professional theme
        self.apply_theme()
        
        # Create menu bar
        self.create_menu()
        
        self.dlp = None
        self.connected = False
        self.demo_mode = False
        self.projecting = False
        self.projection_thread = None
        self.stop_projection_flag = False
        self.images = []
        # CoolLED controller
        self.coolled = None
        self.coolled_connected = False
        self.coolled_demo_mode = False
        self.selected_image_index = None
        self.projection_mode = tk.StringVar(value='constant')
        self.projection_start_time = None
        self.projection_total_time = None
        self.timer_update_id = None
        # Upload state tracking
        self.images_uploaded = False
        self.uploaded_image_index = None  # Track which image was uploaded (for constant mode)
        self.upload_thread = None
        
        # Settings with defaults
        self.settings = {
            'max_patterns_1bit': 400,
            'max_patterns_8bit': 20,
            'max_safe_exposure_us': MAX_SAFE_EXPOSURE_US,
            'max_recommended_exposure_us': MAX_RECOMMENDED_EXPOSURE_US,
            'trigger_on_off_path': r'C:\Users\Nikon\nikon_trigger\trigger_on_off.txt',
            'trigger_next_path': r'C:\Users\Nikon\nikon_trigger\trigger_next.txt',
            'nikon_start_black_frame': True  # Start with black frame in Nikon trigger mode
        }
        self.load_settings()
        
        self.create_ui()
    
    def create_menu(self):
        """Create menu bar with File, Settings and Help menus"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # Settings menu
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Configuration...", command=self.show_settings)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
    
    def show_about(self):
        """Show About dialog with credits and version info"""
        about_window = tk.Toplevel(self.root)
        about_window.title(f"About {APP_NAME}")
        about_window.geometry("500x400")
        about_window.resizable(False, False)
        about_window.transient(self.root)
        about_window.grab_set()
        
        # Center the window
        about_window.update_idletasks()
        x = (about_window.winfo_screenwidth() // 2) - (500 // 2)
        y = (about_window.winfo_screenheight() // 2) - (400 // 2)
        about_window.geometry(f"500x400+{x}+{y}")
        
        # Content frame
        content = ttk.Frame(about_window, padding="20")
        content.pack(fill=tk.BOTH, expand=True)
        
        # App name and version
        ttk.Label(content, text=APP_NAME, font=('TkDefaultFont', 18, 'bold')).pack(pady=(0, 5))
        ttk.Label(content, text=f"Version {VERSION}", font=('TkDefaultFont', 12)).pack(pady=(0, 20))
        
        # Description
        desc_text = "Integrated DMD and CoolLED controller for\nprecise spatial light modulation and illumination"
        ttk.Label(content, text=desc_text, font=('TkDefaultFont', 10), justify=tk.CENTER).pack(pady=(0, 20))
        
        # Credits
        ttk.Label(content, text="Credits", font=('TkDefaultFont', 12, 'bold')).pack(pady=(10, 5))
        credits_text = (
            "Based on Pycrafter6500 with 8-bit support from uPatternScope\n"
            "CoolLED integration from CoolLED_control\n"
            "ERLE encoding for image compression\n\n"
            "See GitHub for detailed references and citations"
        )
        ttk.Label(content, text=credits_text, font=('TkDefaultFont', 8), justify=tk.CENTER).pack(pady=(0, 20))
        
        # GitHub link
        ttk.Label(content, text="GitHub Repository:", font=('TkDefaultFont', 10, 'bold')).pack(pady=(10, 5))
        github_label = ttk.Label(content, text=GITHUB_URL, font=('TkDefaultFont', 9), foreground='blue', cursor='hand2')
        github_label.pack()
        github_label.bind("<Button-1>", lambda e: self.open_url(GITHUB_URL))
        
        # Close button
        ttk.Button(content, text="Close", command=about_window.destroy).pack(pady=(20, 0))
    
    def open_url(self, url):
        """Open URL in default browser"""
        import webbrowser
        webbrowser.open(url)
    
    def show_settings(self):
        """Show Settings configuration dialog"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("600x500")
        settings_window.resizable(False, False)
        settings_window.transient(self.root)
        settings_window.grab_set()
        
        # Center the window
        settings_window.update_idletasks()
        x = (settings_window.winfo_screenwidth() // 2) - (600 // 2)
        y = (settings_window.winfo_screenheight() // 2) - (500 // 2)
        settings_window.geometry(f"600x500+{x}+{y}")
        
        # Content frame
        content = ttk.Frame(settings_window, padding="20")
        content.pack(fill=tk.BOTH, expand=True)
        
        # Title
        ttk.Label(content, text="Configuration Settings", font=('TkDefaultFont', 14, 'bold')).pack(pady=(0, 20))
        
        # Pattern Limits Section
        pattern_frame = ttk.LabelFrame(content, text="Pattern Limits", padding="10")
        pattern_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(pattern_frame, text="Max 1-bit patterns:").grid(row=0, column=0, sticky=tk.W, pady=5)
        max_1bit_var = tk.IntVar(value=self.settings['max_patterns_1bit'])
        ttk.Entry(pattern_frame, textvariable=max_1bit_var, width=15).grid(row=0, column=1, sticky=tk.W, padx=10)
        ttk.Label(pattern_frame, text="(1-400)", foreground='gray').grid(row=0, column=2, sticky=tk.W)
        
        ttk.Label(pattern_frame, text="Max 8-bit patterns:").grid(row=1, column=0, sticky=tk.W, pady=5)
        max_8bit_var = tk.IntVar(value=self.settings['max_patterns_8bit'])
        ttk.Entry(pattern_frame, textvariable=max_8bit_var, width=15).grid(row=1, column=1, sticky=tk.W, padx=10)
        ttk.Label(pattern_frame, text="(1-25)", foreground='gray').grid(row=1, column=2, sticky=tk.W)
        
        # Exposure Limits Section
        exposure_frame = ttk.LabelFrame(content, text="Exposure Limits (microseconds)", padding="10")
        exposure_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(exposure_frame, text="Max safe exposure:").grid(row=0, column=0, sticky=tk.W, pady=5)
        max_safe_var = tk.IntVar(value=self.settings['max_safe_exposure_us'])
        ttk.Entry(exposure_frame, textvariable=max_safe_var, width=15).grid(row=0, column=1, sticky=tk.W, padx=10)
        ttk.Label(exposure_frame, text=f"({MAX_SAFE_EXPOSURE_US} default)", foreground='gray').grid(row=0, column=2, sticky=tk.W)
        
        ttk.Label(exposure_frame, text="Max recommended:").grid(row=1, column=0, sticky=tk.W, pady=5)
        max_rec_var = tk.IntVar(value=self.settings['max_recommended_exposure_us'])
        ttk.Entry(exposure_frame, textvariable=max_rec_var, width=15).grid(row=1, column=1, sticky=tk.W, padx=10)
        ttk.Label(exposure_frame, text=f"({MAX_RECOMMENDED_EXPOSURE_US} default)", foreground='gray').grid(row=1, column=2, sticky=tk.W)
        
        # Nikon Sync Paths Section
        nikon_frame = ttk.LabelFrame(content, text="Nikon NIS Synchronization", padding="10")
        nikon_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(nikon_frame, text="Trigger ON/OFF file:").grid(row=0, column=0, sticky=tk.W, pady=5)
        trigger_on_off_var = tk.StringVar(value=self.settings['trigger_on_off_path'])
        ttk.Entry(nikon_frame, textvariable=trigger_on_off_var, width=40).grid(row=0, column=1, sticky=tk.W, padx=10)
        ttk.Button(nikon_frame, text="Browse", command=lambda: self.browse_file(trigger_on_off_var)).grid(row=0, column=2, padx=5)
        
        ttk.Label(nikon_frame, text="Trigger NEXT file:").grid(row=1, column=0, sticky=tk.W, pady=5)
        trigger_next_var = tk.StringVar(value=self.settings['trigger_next_path'])
        ttk.Entry(nikon_frame, textvariable=trigger_next_var, width=40).grid(row=1, column=1, sticky=tk.W, padx=10)
        ttk.Button(nikon_frame, text="Browse", command=lambda: self.browse_file(trigger_next_var)).grid(row=1, column=2, padx=5)
        
        # Buttons
        button_frame = ttk.Frame(content)
        button_frame.pack(fill=tk.X, pady=(20, 0))
        
        def save_settings():
            # Validate and save
            try:
                self.settings['max_patterns_1bit'] = max(1, min(400, max_1bit_var.get()))
                self.settings['max_patterns_8bit'] = max(1, min(25, max_8bit_var.get()))
                self.settings['max_safe_exposure_us'] = max(100, max_safe_var.get())
                self.settings['max_recommended_exposure_us'] = max(100, max_rec_var.get())
                self.settings['trigger_on_off_path'] = trigger_on_off_var.get()
                self.settings['trigger_next_path'] = trigger_next_var.get()
                self.save_settings()
                self.log_progress("Settings saved successfully")
                settings_window.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save settings: {e}")
        
        ttk.Button(button_frame, text="Save", command=save_settings).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=settings_window.destroy).pack(side=tk.RIGHT)
    
    def browse_file(self, var):
        """Browse for a file path"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            var.set(filename)
    
    def load_settings(self):
        """Load settings from config file"""
        import json
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    saved_settings = json.load(f)
                    self.settings.update(saved_settings)
        except Exception as e:
            print(f"Could not load settings: {e}")
    
    def save_settings(self):
        """Save settings to config file"""
        import json
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        try:
            with open(config_path, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Could not save settings: {e}")
    
    def _save_black_frame_setting(self):
        """Save black frame setting when checkbox is toggled"""
        self.settings['nikon_start_black_frame'] = self.nikon_black_frame_var.get()
        self.save_settings()
    
    def apply_theme(self):
        """Apply additional styling tweaks for the arc theme"""
        style = ttk.Style()
        
        # The arc theme from ttkthemes handles most styling automatically
        # Just add a few custom tweaks for better appearance
        
        # Increase Treeview row height for better readability
        style.configure('Treeview', rowheight=25)
        
        # Make LabelFrame labels bold for better hierarchy
        style.configure('TLabelframe.Label', font=('TkDefaultFont', 9, 'bold'))
        
        # Add padding to buttons for better touch targets
        style.configure('TButton', padding=6)
    
    def create_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Configure column weights: left and right fixed, center expands
        main_frame.columnconfigure(0, weight=0)  # Left panel - no expansion
        main_frame.columnconfigure(1, weight=1)  # Center panel - expands
        main_frame.columnconfigure(2, weight=0)  # Right panel - no expansion
        main_frame.rowconfigure(0, weight=1)  # Top section
        main_frame.rowconfigure(1, weight=0)  # Bottom progress section
        
        # Left Panel (fixed width, no horizontal expansion)
        left_frame = ttk.LabelFrame(main_frame, text="System & Configuration", padding="10", width=280)
        left_frame.grid(row=0, column=0, sticky=(tk.N, tk.S), padx=(0, 5))
        left_frame.pack_propagate(False)  # Prevent frame from shrinking (use pack_propagate since children use pack)
        
        # DMD Connection
        conn_frame = ttk.LabelFrame(left_frame, text="DMD Connection", padding="5")
        conn_frame.pack(fill=tk.X, pady=(0, 10))
        self.status_label = ttk.Label(conn_frame, text="● Disconnected", foreground="red")
        self.status_label.pack(anchor=tk.W)
        btn_frame = ttk.Frame(conn_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        self.connect_btn = ttk.Button(btn_frame, text="Connect", command=self.connect_dmd)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.disconnect_btn = ttk.Button(btn_frame, text="Disconnect", command=self.disconnect_dmd, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT)
        
        # CoolLED Connection
        led_frame = ttk.LabelFrame(left_frame, text="CoolLED pE-4000", padding="5")
        led_frame.pack(fill=tk.X, pady=(0, 10))
        self.led_status_label = ttk.Label(led_frame, text="● Disconnected", foreground="red")
        self.led_status_label.pack(anchor=tk.W)
        self.led_port_label = ttk.Label(led_frame, text="", foreground="gray", font=('TkDefaultFont', 8))
        self.led_port_label.pack(anchor=tk.W)
        led_btn_frame = ttk.Frame(led_frame)
        led_btn_frame.pack(fill=tk.X, pady=(5, 0))
        self.led_connect_btn = ttk.Button(led_btn_frame, text="Connect", command=self.connect_coolled)
        self.led_connect_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.led_disconnect_btn = ttk.Button(led_btn_frame, text="Disconnect", command=self.disconnect_coolled, state=tk.DISABLED)
        self.led_disconnect_btn.pack(side=tk.LEFT)
        ttk.Label(led_frame, text="For pulsed mode illumination", font=('TkDefaultFont', 8), foreground='gray').pack(anchor=tk.W, pady=(5, 0))
          
        mode_frame = ttk.LabelFrame(left_frame, text="Projection Mode", padding="5")
        mode_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Radiobutton(mode_frame, text="Image sequence", variable=self.projection_mode, value='sequence', command=self.on_projection_mode_change).pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="Constant (selected image only)", variable=self.projection_mode, value='constant', command=self.on_projection_mode_change).pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="Pulsed Projection", variable=self.projection_mode, value='pulsed', command=self.on_projection_mode_change).pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="Nikon NIS Trigger", variable=self.projection_mode, value='nikon_trigger', command=self.on_projection_mode_change).pack(anchor=tk.W)
        
        # Sequence mode settings (1-bit images)
        self.sequence_frame = ttk.LabelFrame(left_frame, text="Sequence Mode Settings", padding="5")
        ttk.Label(self.sequence_frame, text="Number of Cycles (0=infinite):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.seq_repeat_count_var = tk.StringVar(value="0")
        ttk.Entry(self.sequence_frame, textvariable=self.seq_repeat_count_var, width=15).grid(row=0, column=1, pady=2)
        ttk.Label(self.sequence_frame, text="1 cycle = all images shown once", font=('TkDefaultFont', 8), foreground='gray').grid(row=1, column=0, columnspan=2, sticky=tk.W)
        
        # Constant mode settings (single image)
        self.constant_frame = ttk.LabelFrame(left_frame, text="Constant Mode Settings", padding="5")
        
        # Infinite projection checkbox
        self.constant_infinite_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.constant_frame, text="Infinite (project until stopped)", variable=self.constant_infinite_var, command=self.on_constant_infinite_change).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Projection time (enabled when not infinite)
        ttk.Label(self.constant_frame, text="Projection Time:").grid(row=1, column=0, sticky=tk.W, pady=2)
        time_frame = ttk.Frame(self.constant_frame)
        time_frame.grid(row=1, column=1, sticky=tk.W, pady=2)
        self.constant_time_var = tk.StringVar(value="60")
        self.constant_time_entry = ttk.Entry(time_frame, textvariable=self.constant_time_var, width=10)
        self.constant_time_entry.pack(side=tk.LEFT, padx=(0, 2))
        self.constant_time_unit_var = tk.StringVar(value="sec")
        self.constant_time_unit = ttk.Combobox(time_frame, textvariable=self.constant_time_unit_var, values=['sec', 'min', 'hrs'], state='readonly', width=5)
        self.constant_time_unit.pack(side=tk.LEFT)
        
        ttk.Label(self.constant_frame, text="Projects selected image only", font=('TkDefaultFont', 8), foreground='gray').grid(row=2, column=0, columnspan=2, sticky=tk.W)
        
        # Pulsed mode settings with bidirectional calculation
        self.pulsed_frame = ttk.LabelFrame(left_frame, text="Pulsed Mode Settings", padding="5")
        
        ttk.Label(self.pulsed_frame, text="Total Runtime:").grid(row=0, column=0, sticky=tk.W, pady=2)
        runtime_frame = ttk.Frame(self.pulsed_frame)
        runtime_frame.grid(row=0, column=1, columnspan=2, sticky=tk.W, pady=2)
        self.total_runtime_var = tk.StringVar(value="60")
        runtime_entry = ttk.Entry(runtime_frame, textvariable=self.total_runtime_var, width=10)
        runtime_entry.pack(side=tk.LEFT, padx=(0, 2))
        self.runtime_unit_var = tk.StringVar(value="min")
        runtime_unit_combo = ttk.Combobox(runtime_frame, textvariable=self.runtime_unit_var, values=['sec', 'min', 'hrs'], state='readonly', width=5)
        runtime_unit_combo.pack(side=tk.LEFT)
        self.total_runtime_var.trace('w', lambda *args: self.calculate_cycles_from_runtime())
        self.runtime_unit_var.trace('w', lambda *args: self.calculate_cycles_from_runtime())
        
        ttk.Label(self.pulsed_frame, text="OR", font=('TkDefaultFont', 9, 'bold')).grid(row=1, column=0, columnspan=2, pady=5)
        
        ttk.Label(self.pulsed_frame, text="Number of Cycles:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.cycles_var = tk.StringVar(value="")
        cycles_entry = ttk.Entry(self.pulsed_frame, textvariable=self.cycles_var, width=15)
        cycles_entry.grid(row=2, column=1, pady=2)
        self.cycles_var.trace('w', lambda *args: self.calculate_runtime_from_cycles())
        
        # Display calculated value
        self.pulsed_calc_label = ttk.Label(self.pulsed_frame, text="", foreground="blue", font=('TkDefaultFont', 8))
        self.pulsed_calc_label.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        
        # Timing compensation mode
        ttk.Separator(self.pulsed_frame, orient='horizontal').grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        ttk.Label(self.pulsed_frame, text="Timing Mode:", font=('TkDefaultFont', 9, 'bold')).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(0, 2))
        
        self.timing_mode_var = tk.StringVar(value="precise_total")
        timing_frame = ttk.Frame(self.pulsed_frame)
        timing_frame.grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=2)
        
        ttk.Radiobutton(timing_frame, text="Precise Total Time", variable=self.timing_mode_var, 
                       value="precise_total").pack(anchor=tk.W)
        ttk.Label(timing_frame, text="  Compensates upload delays", 
                 foreground="gray", font=('TkDefaultFont', 8)).pack(anchor=tk.W, padx=(20, 0))
        
        ttk.Radiobutton(timing_frame, text="Precise Pulse Time", variable=self.timing_mode_var, 
                       value="precise_pulse").pack(anchor=tk.W, pady=(5, 0))
        ttk.Label(timing_frame, text="  Exact pulse duration", 
                 foreground="gray", font=('TkDefaultFont', 8)).pack(anchor=tk.W, padx=(20, 0))
        
        # Nikon NIS Trigger mode settings (compact)
        self.nikon_trigger_frame = ttk.LabelFrame(left_frame, text="Nikon NIS Trigger", padding="5")
        
        # Status display
        status_info_frame = ttk.Frame(self.nikon_trigger_frame)
        status_info_frame.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        ttk.Label(status_info_frame, text="Status:", foreground="gray", font=('TkDefaultFont', 8)).pack(side=tk.LEFT)
        self.nikon_on_off_status = ttk.Label(status_info_frame, text="--", font=('TkDefaultFont', 8, 'bold'))
        self.nikon_on_off_status.pack(side=tk.LEFT, padx=(5, 15))
        
        ttk.Label(status_info_frame, text="Next:", foreground="gray", font=('TkDefaultFont', 8)).pack(side=tk.LEFT)
        self.nikon_next_status = ttk.Label(status_info_frame, text="--", font=('TkDefaultFont', 8, 'bold'))
        self.nikon_next_status.pack(side=tk.LEFT, padx=5)
        
        # Current pattern
        pattern_frame = ttk.Frame(self.nikon_trigger_frame)
        pattern_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)
        ttk.Label(pattern_frame, text="Pattern:", foreground="gray", font=('TkDefaultFont', 8)).pack(side=tk.LEFT)
        self.nikon_current_pattern = ttk.Label(pattern_frame, text="--", font=('TkDefaultFont', 8, 'bold'))
        self.nikon_current_pattern.pack(side=tk.LEFT, padx=5)
        
        # Black frame option (compact)
        ttk.Separator(self.nikon_trigger_frame, orient='horizontal').grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=8)
        
        self.nikon_black_frame_var = tk.BooleanVar(value=self.settings.get('nikon_start_black_frame', True))
        black_frame_cb = ttk.Checkbutton(self.nikon_trigger_frame, 
                                        text="Start with black frame", 
                                        variable=self.nikon_black_frame_var,
                                        command=self._save_black_frame_setting)
        black_frame_cb.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
        ttk.Label(self.nikon_trigger_frame, 
                 text="Recommended for NIS macro 'trigger_on_next.mac'",
                 foreground="gray", font=('TkDefaultFont', 7)).grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=(20, 0))
        
        # Image Management and Global Settings moved to right panel
        
        # Center Panel
        center_frame = ttk.Frame(main_frame)
        center_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        center_frame.columnconfigure(0, weight=1)
        center_frame.rowconfigure(0, weight=1)
        center_frame.rowconfigure(1, weight=2)
        
        list_frame = ttk.LabelFrame(center_frame, text="Image Sequence", padding="5")
        list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        columns = ('filename', 'mode', 'exposure', 'dark_time', 'duration', 'led')
        self.image_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=5)
        self.image_tree.heading('filename', text='Filename')
        self.image_tree.heading('mode', text='Mode')
        self.image_tree.heading('exposure', text='Exposure (μs)')
        self.image_tree.heading('dark_time', text='Dark Time (μs)')
        self.image_tree.heading('duration', text='Duration (s)')
        self.image_tree.heading('led', text='LED')
        self.image_tree.column('filename', width=200)
        self.image_tree.column('mode', width=50)
        self.image_tree.column('exposure', width=90)
        self.image_tree.column('dark_time', width=90)
        self.image_tree.column('duration', width=80)
        self.image_tree.column('led', width=120)
        self.image_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.image_tree.bind('<<TreeviewSelect>>', self.on_image_select)
        # Keyboard shortcuts for reordering
        self.image_tree.bind('<Control-Up>', lambda e: self.move_image_up())
        self.image_tree.bind('<Control-Down>', lambda e: self.move_image_down())
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.image_tree.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.image_tree.configure(yscrollcommand=scrollbar.set)
        
        preview_frame = ttk.LabelFrame(center_frame, text="Image Preview & Settings", padding="5")
        preview_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.columnconfigure(1, weight=1)
        
        preview_left = ttk.Frame(preview_frame)
        preview_left.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        # Preview header with mirror checkbox
        preview_header = ttk.Frame(preview_left)
        preview_header.pack(fill=tk.X, anchor=tk.W)
        ttk.Label(preview_header, text="Preview (1920×1080):").pack(side=tk.LEFT)
        self.mirror_preview_var = tk.BooleanVar(value=True)  # Default: mirrored
        ttk.Checkbutton(preview_header, text="Mirror", variable=self.mirror_preview_var, command=self.refresh_preview).pack(side=tk.LEFT, padx=(10, 0))
        
        # Maintain 16:9 aspect ratio (1920:1080 = 16:9)
        # Using width=480, height=270 for exact 16:9 ratio
        self.preview_canvas = tk.Canvas(preview_left, width=480, height=270, bg='black', highlightthickness=1, highlightbackground='gray')
        self.preview_canvas.pack(pady=5)
        self.preview_label = ttk.Label(preview_left, text="No image selected", foreground="gray")
        self.preview_label.pack(pady=5)
        
        # Nikon NIS Trigger help (shown only when mode is active)
        self.nikon_help_frame = ttk.LabelFrame(preview_left, text="ℹ Nikon NIS Trigger Mode", padding="8")
        self.nikon_help_frame.pack_forget()  # Hidden by default
        
        help_text = """How it works:
• NIS writes 1 to trigger_on_off.txt → starts projection
• NIS increments trigger_next.txt → shows next pattern  
• NIS writes 0 to trigger_on_off.txt → stops projection"""

        ttk.Label(self.nikon_help_frame, text=help_text, justify=tk.LEFT,
                 foreground="#555", font=('TkDefaultFont', 8)).pack(anchor=tk.W)
        
        settings_right = ttk.Frame(preview_frame)
        settings_right.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        settings_inner = ttk.LabelFrame(settings_right, text="Selected Image Settings", padding="10")
        settings_inner.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(settings_inner, text="Bit Mode:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.img_mode_var = tk.StringVar()
        mode_combo = ttk.Combobox(settings_inner, textvariable=self.img_mode_var, values=['1bit', '8bit'], state='readonly', width=15)
        mode_combo.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(5, 0))
        mode_combo.bind('<<ComboboxSelected>>', self.on_image_setting_change)
        
        # Exposure label and input field - matching Duration field layout
        ttk.Label(settings_inner, text="Exposure (μs):").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        # Create a container for the input field
        exposure_frame = ttk.Frame(settings_inner)
        exposure_frame.grid(row=1, column=1, sticky=tk.W, pady=5, padx=(5, 0))
        
        # Add the input field
        self.img_exposure_var = tk.StringVar()
        ttk.Entry(exposure_frame, textvariable=self.img_exposure_var, width=18).pack(anchor=tk.W)
        self.img_exposure_var.trace('w', lambda *args: self.on_image_setting_change())
        
        # Add minimum exposure time label in the next row, spanning both columns
        self.min_exposure_label = ttk.Label(
            settings_inner,
            text="Min: 105 μs (1-bit)",
            font=('TkDefaultFont', 8),
            foreground='gray'
        )
        # Place the label in a new row below the exposure input
        self.min_exposure_label.grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=(5, 0), pady=(0, 5))
        
        # Update label when bit depth changes
        self.img_mode_var.trace('w', self.update_min_exposure_label)
        
        # Move Dark Time to row 3 (after the min exposure label)
        ttk.Label(settings_inner, text="Dark Time (μs):").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.img_dark_time_var = tk.StringVar()
        ttk.Entry(settings_inner, textvariable=self.img_dark_time_var, width=18).grid(row=3, column=1, sticky=tk.W, pady=5, padx=(5, 0))
        self.img_dark_time_var.trace('w', lambda *args: self.on_image_setting_change())
        
        # Move Duration to row 4
        ttk.Label(settings_inner, text="Duration:").grid(row=4, column=0, sticky=tk.W, pady=5)
        duration_frame = ttk.Frame(settings_inner)
        duration_frame.grid(row=4, column=1, sticky=tk.W, pady=5, padx=(5, 0))
        self.img_duration_var = tk.StringVar(value="60")
        self.img_duration_entry = ttk.Entry(duration_frame, textvariable=self.img_duration_var, width=10)
        self.img_duration_entry.pack(side=tk.LEFT, padx=(0, 2))
        self.img_duration_unit_var = tk.StringVar(value="sec")
        self.img_duration_unit_combo = ttk.Combobox(duration_frame, textvariable=self.img_duration_unit_var, values=['sec', 'min', 'hrs'], state='readonly', width=5)
        self.img_duration_unit_combo.pack(side=tk.LEFT)
        self.img_duration_var.trace('w', lambda *args: self.on_image_setting_change())
        self.img_duration_unit_var.trace('w', lambda *args: self.on_image_setting_change())
        # Move pulsed mode note to row 5
        ttk.Label(settings_inner, text="(For pulsed mode only)", font=('TkDefaultFont', 8), foreground='gray').grid(row=5, column=0, columnspan=2, sticky=tk.W)
        
        # CoolLED Illumination Settings (moved down by 1 row)
        ttk.Separator(settings_inner, orient=tk.HORIZONTAL).grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        ttk.Label(settings_inner, text="LED Illumination:", font=('TkDefaultFont', 9, 'bold')).grid(row=7, column=0, columnspan=2, sticky=tk.W)
        
        # LED enabled automatically when any channel is selected (no checkbox needed)
        self.img_led_enabled_var = tk.BooleanVar(value=False)
        
        # Create 4 channel controls
        self.led_channel_vars = {}
        row_start = 7
        for i, channel in enumerate(['A', 'B', 'C', 'D']):
            channel_frame = ttk.Frame(settings_inner)
            channel_frame.grid(row=row_start+i, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=2)
            
            # Channel enable checkbox
            ch_enabled_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(channel_frame, text=f"Ch {channel}", variable=ch_enabled_var, command=self.on_image_setting_change, width=5).pack(side=tk.LEFT)
            
            # Wavelength selector
            ch_wavelength_var = tk.StringVar(value=str(CHANNEL_WAVELENGTHS[channel][0]))
            wavelength_combo = ttk.Combobox(channel_frame, textvariable=ch_wavelength_var, 
                                           values=[str(w) for w in CHANNEL_WAVELENGTHS[channel]], 
                                           state='readonly', width=6)
            wavelength_combo.pack(side=tk.LEFT, padx=5)
            wavelength_combo.bind('<<ComboboxSelected>>', lambda e: self.on_image_setting_change())
            
            ttk.Label(channel_frame, text="nm").pack(side=tk.LEFT)
            
            # Intensity entry
            ch_intensity_var = tk.StringVar(value='50')
            intensity_entry = ttk.Entry(channel_frame, textvariable=ch_intensity_var, width=5)
            intensity_entry.pack(side=tk.LEFT, padx=5)
            ch_intensity_var.trace('w', lambda *args: self.on_image_setting_change())
            
            ttk.Label(channel_frame, text="%").pack(side=tk.LEFT)
            
            self.led_channel_vars[channel] = {
                'enabled': ch_enabled_var,
                'wavelength': ch_wavelength_var,
                'intensity': ch_intensity_var
            }
        
        self.led_mode_hint_label = ttk.Label(settings_inner, text="", font=('TkDefaultFont', 8), foreground='gray', wraplength=200)
        self.led_mode_hint_label.grid(row=row_start+4, column=0, columnspan=2, sticky=tk.W)
        self.update_led_hint_label()
        
        # Right Panel (fixed width, spans both rows - match left panel width)
        right_frame = ttk.LabelFrame(main_frame, text="Projection Control", padding="10", width=280)
        right_frame.grid(row=0, column=2, rowspan=2, sticky=(tk.N, tk.S), padx=(5, 0))
        right_frame.pack_propagate(False)  # Maintain fixed width (use pack_propagate since children use pack)
        
        status_frame = ttk.LabelFrame(right_frame, text="Status", padding="5")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        self.proj_status_label = ttk.Label(status_frame, text="Ready", font=('TkDefaultFont', 10, 'bold'))
        self.proj_status_label.pack()
        self.proj_info_label = ttk.Label(status_frame, text="", font=('TkDefaultFont', 9))
        self.proj_info_label.pack()
        self.timer_label = ttk.Label(status_frame, text="", font=('TkDefaultFont', 9), foreground='#555555')
        self.timer_label.pack(pady=(5, 0))
        
        control_frame = ttk.Frame(right_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        self.upload_btn = ttk.Button(control_frame, text="⬆ Upload to DMD", command=self.upload_to_dmd, state=tk.DISABLED)
        self.upload_btn.pack(fill=tk.X, pady=2)
        self.start_btn = ttk.Button(control_frame, text="▶ Start Projection", command=self.start_projection, state=tk.DISABLED)
        self.start_btn.pack(fill=tk.X, pady=2)
        self.stop_btn = ttk.Button(control_frame, text="⏹ Stop", command=self.stop_projection, state=tk.DISABLED)
        self.stop_btn.pack(fill=tk.X, pady=2)
        
        # Image Management (moved from left panel)
        img_mgmt_frame = ttk.LabelFrame(right_frame, text="Image Management", padding="5")
        img_mgmt_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(img_mgmt_frame, text="Add Image(s)", command=self.add_images).pack(fill=tk.X, pady=2)
        ttk.Button(img_mgmt_frame, text="Remove Selected", command=self.remove_selected_image).pack(fill=tk.X, pady=2)
        
        # Reorder buttons in a horizontal frame
        reorder_frame = ttk.Frame(img_mgmt_frame)
        reorder_frame.pack(fill=tk.X, pady=2)
        ttk.Button(reorder_frame, text="▲ Move Up", command=self.move_image_up).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(reorder_frame, text="▼ Move Down", command=self.move_image_down).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        
        ttk.Button(img_mgmt_frame, text="Clear All", command=self.clear_all_images).pack(fill=tk.X, pady=2)
        
        # Sequence Info
        info_frame = ttk.LabelFrame(right_frame, text="Sequence Info", padding="5")
        info_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 10))
        self.info_text = tk.Text(info_frame, height=4, wrap=tk.WORD, state=tk.DISABLED)
        self.info_text.pack(fill=tk.BOTH, expand=True)
        self.update_sequence_info()
        
        # Global Settings (compact layout for slim panel)
        global_frame = ttk.LabelFrame(right_frame, text="Global Settings", padding="5")
        global_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(global_frame, text="Default Mode:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.default_mode_var = tk.StringVar(value='8bit')
        ttk.Combobox(global_frame, textvariable=self.default_mode_var, values=['1bit', '8bit'], state='readonly', width=8).grid(row=0, column=1, sticky=tk.W, pady=2)
        ttk.Label(global_frame, text="Default Exposure (μs):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.default_exposure_var = tk.StringVar(value='4046')
        ttk.Entry(global_frame, textvariable=self.default_exposure_var, width=10).grid(row=1, column=1, sticky=tk.W, pady=2)
        ttk.Label(global_frame, text="Max: 16,777,215 μs (≈16.8s)", font=('TkDefaultFont', 8), foreground='gray').grid(row=2, column=0, columnspan=2, sticky=tk.W)
        ttk.Button(global_frame, text="Apply to All", command=self.apply_default_mode).grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5, 0))
        
        # Bottom Panel: Progress Log (spans entire width - all 3 columns)
        progress_frame = ttk.LabelFrame(main_frame, text="Progress Log", padding="5")
        progress_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(5, 0))
        
        # Create frame with scrollbar
        progress_inner = ttk.Frame(progress_frame)
        progress_inner.pack(fill=tk.BOTH, expand=True)
        
        self.progress_text = tk.Text(progress_inner, height=8, wrap=tk.NONE, state=tk.DISABLED)
        self.progress_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Add scrollbars
        progress_vscroll = ttk.Scrollbar(progress_inner, orient=tk.VERTICAL, command=self.progress_text.yview)
        progress_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.progress_text.configure(yscrollcommand=progress_vscroll.set)
        
        progress_hscroll = ttk.Scrollbar(progress_frame, orient=tk.HORIZONTAL, command=self.progress_text.xview)
        progress_hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.progress_text.configure(xscrollcommand=progress_hscroll.set)
        
        # Sequence Info now inside right panel (see above)
        
        # Show constant mode frame by default (since constant is the default mode)
        self.constant_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Set initial state for duration field (should be disabled in constant mode)
        self.update_duration_field_state()
        
        # Set up proper window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def on_closing(self):
        """Handle window close event gracefully"""
        # Warn if projection is running
        if self.projecting:
            if not messagebox.askyesno("Projection Running", 
                                       "A projection is currently running.\n\n"
                                       "Do you want to stop it and close the application?"):
                return  # User cancelled, don't close
            self.stop_projection()
        
        # Disconnect from hardware if connected
        if self.connected and not self.demo_mode:
            try:
                self.disconnect_dmd()
            except:
                pass
        # Disconnect CoolLED if connected
        if self.coolled_connected and not self.coolled_demo_mode:
            try:
                self.disconnect_coolled()
            except:
                pass
        # Close the window
        self.root.destroy()
    
    def connect_dmd(self):
        try:
            self.log_progress("Connecting to DMD...")
            self.dlp = pycrafter6500.dmd()
            
            # Check if device was found
            if self.dlp.dev is None:
                raise ConnectionError("DMD device not found. Please check USB connection.")
            
            self.dlp.stopsequence()
            self.dlp.changemode(3)
            self.connected = True
            self.demo_mode = False
            self.status_label.config(text="● Connected", foreground="green")
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
            self.update_button_states()
            self.log_progress("Connected successfully!")
            #messagebox.showinfo("Success", "Connected to DMD hardware!")
            
        except Exception as e:
            self.log_progress(f"Hardware connection failed: {e}")
            
            # Offer demo mode
            result = messagebox.askyesno(
                "Hardware Not Found",
                f"Could not connect to DMD hardware:\n{e}\n\n"
                "Would you like to enable Demo Mode?\n\n"
                "Demo Mode lets you test all GUI features without hardware."
            )
            
            if result:
                self.enable_demo_mode()
            else:
                self.log_progress("Connection cancelled")
    
    def disconnect_dmd(self):
        if self.projecting: self.stop_projection()
        self.dlp = None
        self.connected = False
        self.demo_mode = False
        self.images_uploaded = False
        self.uploaded_image_index = None
        self.status_label.config(text="● Disconnected", foreground="red")
        self.proj_status_label.config(text="Ready")
        self.proj_info_label.config(text="")
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.update_button_states()
        self.log_progress("Disconnected")
    
    def connect_coolled(self):
        """Connect to CoolLED pE-4000"""
        def search_and_connect():
            devices = CoolLEDController.find_devices()
            self.root.after(0, lambda: self.complete_coolled_connection(devices))
        threading.Thread(target=search_and_connect, daemon=True).start()
    
    def complete_coolled_connection(self, devices):
        """Complete CoolLED connection after device search"""
        if not devices:
            result = messagebox.askyesno(
                "CoolLED Not Found",
                "Could not find CoolLED pE-4000 device.\n\n"
                "Would you like to enable Demo Mode for CoolLED?\n\n"
                "Demo Mode lets you configure LED settings without hardware."
            )
            if result:
                self.enable_coolled_demo_mode()
            return
        
        port = devices[0]
        self.coolled = CoolLEDController(port)
        success, message = self.coolled.connect()
        
        if success:
            self.coolled_connected = True
            self.led_status_label.config(text="● Connected", foreground="green")
            self.led_port_label.config(text=f"{port} | {message}")
            self.led_connect_btn.config(state=tk.DISABLED)
            self.led_disconnect_btn.config(state=tk.NORMAL)
            self.log_progress(f"CoolLED connected on {port}: {message}")
            self.update_led_hint_label()
        else:
            messagebox.showerror("Connection Error", f"Could not connect to CoolLED:\n{message}")
    
    def disconnect_coolled(self):
        """Disconnect from CoolLED"""
        if self.coolled and self.coolled_connected:
            self.coolled.disconnect()
        self.coolled = None
        self.coolled_connected = False
        self.coolled_demo_mode = False
        self.led_status_label.config(text="● Disconnected", foreground="red")
        self.led_port_label.config(text="")
        self.led_connect_btn.config(state=tk.NORMAL)
        self.led_disconnect_btn.config(state=tk.DISABLED)
        self.log_progress("CoolLED disconnected")
        self.update_led_hint_label()
    
    def enable_coolled_demo_mode(self):
        """Enable demo mode for CoolLED"""
        self.coolled_demo_mode = True
        self.coolled_connected = True
        self.led_status_label.config(text="● Demo Mode", foreground="orange")
        self.led_port_label.config(text="No hardware - Testing mode")
        self.led_connect_btn.config(state=tk.DISABLED)
        self.led_disconnect_btn.config(state=tk.NORMAL)
        self.log_progress("CoolLED Demo Mode enabled")
        messagebox.showinfo(
            "CoolLED Demo Mode",
            "CoolLED Demo Mode is now active!\n\n"
            "You can configure LED settings for images.\n"
            "Note: No actual LED control will occur."
        )
    
    def enable_demo_mode(self):
        """Enable demo mode for testing without hardware"""
        self.demo_mode = True
        self.connected = True
        self.dlp = None  # No actual hardware
        self.status_label.config(text="● Demo Mode", foreground="orange")
        self.connect_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.NORMAL)
        self.update_button_states()
        self.log_progress("Demo Mode enabled - All GUI features available for testing")
        messagebox.showinfo(
            "Demo Mode Enabled",
            "Demo Mode is now active!\n\n"
            "You can test all GUI features:\n"
            "• Add and configure images\n"
            "• Set up projection sequences\n"
            "• Test timing calculations\n\n"
            "Note: No actual projection will occur (no hardware connected)."
        )
    
    def on_constant_infinite_change(self):
        """Enable/disable projection time fields based on infinite checkbox"""
        infinite = self.constant_infinite_var.get()
        state = tk.DISABLED if infinite else tk.NORMAL
        self.constant_time_entry.config(state=state)
        self.constant_time_unit.config(state='disabled' if infinite else 'readonly')
    
    def update_duration_field_state(self):
        """Enable/disable duration field based on projection mode"""
        mode = self.projection_mode.get()
        # Duration is only relevant in pulsed mode
        if mode == 'pulsed':
            self.img_duration_entry.config(state=tk.NORMAL)
            self.img_duration_unit_combo.config(state='readonly')
        else:
            self.img_duration_entry.config(state=tk.DISABLED)
            self.img_duration_unit_combo.config(state='disabled')
    
    def on_projection_mode_change(self):
        # Hide all mode-specific frames
        self.sequence_frame.pack_forget()
        self.constant_frame.pack_forget()
        self.pulsed_frame.pack_forget()
        self.nikon_trigger_frame.pack_forget()
        self.nikon_help_frame.pack_forget()
        
        # Show the appropriate frame for the selected mode
        mode = self.projection_mode.get()
        if mode == 'sequence':
            self.sequence_frame.pack(fill=tk.X, pady=(0, 10))
        elif mode == 'constant':
            self.constant_frame.pack(fill=tk.X, pady=(0, 10))
            self.on_constant_infinite_change()  # Update time field states
        elif mode == 'pulsed':
            self.pulsed_frame.pack(fill=tk.X, pady=(0, 10))
            self.calculate_cycles_from_runtime()  # Update display
        elif mode == 'nikon_trigger':
            self.nikon_trigger_frame.pack(fill=tk.X, pady=(0, 10))
            self.nikon_help_frame.pack(fill=tk.X, pady=(5, 0))  # Show help below preview
        
        # Update duration field state based on mode
        self.update_duration_field_state()
        
        # Update LED hint label
        self.update_led_hint_label()
        
        # Mark images as not uploaded when mode changes
        self.mark_images_not_uploaded()
        
        self.update_sequence_info()
    
    def add_images(self):
        filepaths = filedialog.askopenfilenames(title="Select Images", filetypes=[("Images", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp"), ("All", "*.*")])
        if not filepaths: return
        try:
            default_exposure = int(self.default_exposure_var.get())
        except ValueError:
            default_exposure = 4046  # Fallback
        for filepath in filepaths:
            img_item = ImageItem(filepath, self.default_mode_var.get())
            img_item.exposure = default_exposure  # Apply global default exposure
            self.images.append(img_item)
            self.image_tree.insert('', tk.END, values=(os.path.basename(filepath), img_item.mode, img_item.exposure, img_item.dark_time, img_item.duration))
        self.update_sequence_info()
        self.log_progress(f"Added {len(filepaths)} image(s)")
        # Mark images as not uploaded since sequence changed
        self.mark_images_not_uploaded()
        # Update pulsed mode calculations if in pulsed mode
        if self.projection_mode.get() == 'pulsed':
            self.calculate_cycles_from_runtime()
    
    def remove_selected_image(self):
        sel = self.image_tree.selection()
        if not sel: return
        idx = self.image_tree.index(sel[0])
        del self.images[idx]
        self.image_tree.delete(sel[0])
        self.selected_image_index = None
        self.clear_preview()
        self.update_sequence_info()
        self.mark_images_not_uploaded()
    
    def clear_all_images(self):
        if not self.images or not messagebox.askyesno("Confirm", "Clear all?"): return
        self.images.clear()
        for item in self.image_tree.get_children(): self.image_tree.delete(item)
        self.selected_image_index = None
        self.clear_preview()
        self.update_sequence_info()
        self.mark_images_not_uploaded()
    
    def move_image_up(self):
        """Move selected image up in the list"""
        sel = self.image_tree.selection()
        if not sel: return
        idx = self.image_tree.index(sel[0])
        if idx == 0: return  # Already at top
        
        # Swap images in list
        self.images[idx], self.images[idx-1] = self.images[idx-1], self.images[idx]
        
        # Refresh display
        self.refresh_image_list()
        
        # Reselect the moved item at its new position
        items = self.image_tree.get_children()
        self.image_tree.selection_set(items[idx-1])
        self.image_tree.focus(items[idx-1])
        self.selected_image_index = idx - 1
        
        # Mark images as not uploaded since order changed
        self.mark_images_not_uploaded()
        
        # Update pulsed mode calculations if in pulsed mode
        if self.projection_mode.get() == 'pulsed':
            self.calculate_cycles_from_runtime()
    
    def move_image_down(self):
        """Move selected image down in the list"""
        sel = self.image_tree.selection()
        if not sel: return
        idx = self.image_tree.index(sel[0])
        if idx >= len(self.images) - 1: return  # Already at bottom
        
        # Swap images in list
        self.images[idx], self.images[idx+1] = self.images[idx+1], self.images[idx]
        
        # Refresh display
        self.refresh_image_list()
        
        # Reselect the moved item at its new position
        items = self.image_tree.get_children()
        self.image_tree.selection_set(items[idx+1])
        self.image_tree.focus(items[idx+1])
        self.selected_image_index = idx + 1
        
        # Mark images as not uploaded since order changed
        self.mark_images_not_uploaded()
        
        # Update pulsed mode calculations if in pulsed mode
        if self.projection_mode.get() == 'pulsed':
            self.calculate_cycles_from_runtime()
    
    def apply_default_mode(self):
        if not self.images: return
        mode = self.default_mode_var.get()
        try:
            exposure = int(self.default_exposure_var.get())
        except ValueError:
            exposure = 4046  # Fallback to default
        for img in self.images:
            img.mode = mode
            img.exposure = exposure
        self.refresh_image_list()
        self.mark_images_not_uploaded()
    
    def update_led_hint_label(self):
        """Update the LED hint label based on projection mode"""
        mode = self.projection_mode.get()
        if mode == 'constant':
            hint = "Used for constant projection"
            color = 'gray'
        elif mode == 'sequence':
            hint = "First image's settings used\nfor entire sequence"
            color = 'red'
        elif mode == 'pulsed':
            hint = "Per-image control\n(on/off each image)"
            color = 'gray'
        else:
            hint = ""
            color = 'gray'
        self.led_mode_hint_label.config(text=hint, foreground=color)
    
    def on_image_select(self, event):
        sel = self.image_tree.selection()
        if not sel: return
        idx = self.image_tree.index(sel[0])
        
        # In constant mode, selecting a different image means we need to re-upload
        if self.projection_mode.get() == 'constant' and self.images_uploaded:
            # Check if we're selecting a different image than what was uploaded
            if self.uploaded_image_index is not None and idx != self.uploaded_image_index:
                self.mark_images_not_uploaded()
        
        self.selected_image_index = idx
        img = self.images[idx]
        
        # Temporarily disable trace callbacks to prevent triggering on_image_setting_change
        # when loading values into the GUI fields
        self._loading_image = True
        
        self.img_mode_var.set(img.mode)
        self.img_exposure_var.set(str(img.exposure))
        self.img_dark_time_var.set(str(img.dark_time))
        
        # Display duration in the stored unit preference (or default to seconds)
        unit = getattr(img, 'duration_unit', 'sec')
        self.img_duration_unit_var.set(unit)
        if unit == 'min':
            duration_display = img.duration / 60
        elif unit == 'hrs':
            duration_display = img.duration / 3600
        else:  # sec
            duration_display = img.duration
        self.img_duration_var.set(f"{duration_display:.1f}" if duration_display != int(duration_display) else str(int(duration_display)))
        
        # Load LED settings
        self.img_led_enabled_var.set(img.led_enabled)
        for channel in ['A', 'B', 'C', 'D']:
            self.led_channel_vars[channel]['enabled'].set(img.led_channels[channel]['enabled'])
            self.led_channel_vars[channel]['wavelength'].set(str(img.led_channels[channel]['wavelength']))
            self.led_channel_vars[channel]['intensity'].set(str(img.led_channels[channel]['intensity']))
        
        # Re-enable trace callbacks
        self._loading_image = False
        
        try:
            # Load thumbnail only for preview (fast)
            img.load_thumbnail()
            self.display_preview(img)
        except Exception as e:
            self.log_progress(f"Load error: {e}")
    
    def update_min_exposure_label(self, *args):
        """Update the minimum exposure time label based on selected bit depth"""
        try:
            mode = self.img_mode_var.get()
            if mode == '8bit':
                self.min_exposure_label.config(text="Min: 4046 μs (8-bit)")
            else:  # Default to 1-bit
                self.min_exposure_label.config(text="Min: 105 μs (1-bit)")
        except Exception as e:
            print(f"Error updating min exposure label: {e}")
    
    def on_image_setting_change(self, event=None):
        """Handle changes to image settings"""
        # Don't save changes if we're currently loading an image's values into the GUI
        if getattr(self, '_loading_image', False):
            return
            
        if self.selected_image_index is None:
            return
            
        img = self.images[self.selected_image_index]
        should_recalculate = False
        
        try:
            # Check for empty fields first
            if not self.img_exposure_var.get() or not self.img_dark_time_var.get() or not self.img_duration_var.get():
                return  # Don't process if any field is empty
            
            # Update mode if changed
            new_mode = self.img_mode_var.get()
            if new_mode in ['1bit', '8bit'] and new_mode != img.mode:
                img.mode = new_mode
                # Update the min exposure label when mode changes
                self.update_min_exposure_label()
                # Set default exposure based on mode
                if new_mode == '8bit' and int(self.img_exposure_var.get()) < 4046:
                    self.img_exposure_var.set("4046")  # Set to minimum for 8-bit
                elif new_mode == '1bit' and int(self.img_exposure_var.get()) < 105:
                    self.img_exposure_var.set("105")  # Set to minimum for 1-bit
            
            # Update exposure time if changed and valid
            try:
                exposure = int(self.img_exposure_var.get())
                if exposure > 0:  # Only update if valid positive number
                    img.exposure = exposure
            except (ValueError, tk.TclError):
                pass  # Ignore invalid entries (non-numeric)
            
            # Update duration if changed and valid
            try:
                duration_value = float(self.img_duration_var.get())
                unit = self.img_duration_unit_var.get()
                if unit == 'min':
                    img.duration = int(duration_value * 60)
                elif unit == 'hrs':
                    img.duration = int(duration_value * 3600)
                else:  # sec
                    img.duration = int(duration_value)
                # Store the unit preference with the image
                img.duration_unit = unit
            except (ValueError, tk.TclError):
                pass  # Ignore invalid entries (non-numeric)
            
            # Update dark time if changed and valid
            try:
                dark_time = int(self.img_dark_time_var.get())
                if dark_time >= 0:  # Only update if valid non-negative number
                    img.dark_time = dark_time
            except (ValueError, tk.TclError):
                pass  # Ignore invalid entries (non-numeric)
            
            # Update LED settings
            # Auto-enable LED if any channel is enabled
            any_channel_enabled = False
            for channel in ['A', 'B', 'C', 'D']:
                img.led_channels[channel]['enabled'] = self.led_channel_vars[channel]['enabled'].get()
                if self.led_channel_vars[channel]['enabled'].get():
                    any_channel_enabled = True
                if self.led_channel_vars[channel]['wavelength'].get():
                    img.led_channels[channel]['wavelength'] = int(self.led_channel_vars[channel]['wavelength'].get())
                if self.led_channel_vars[channel]['intensity'].get():
                    img.led_channels[channel]['intensity'] = int(self.led_channel_vars[channel]['intensity'].get())
            
            # Automatically enable LED if any channel is selected
            img.led_enabled = any_channel_enabled
            self.img_led_enabled_var.set(any_channel_enabled)
            
            # Reload image if needed
            if img.image_array is not None:
                img.load_image()
            
            should_recalculate = True
                
        except Exception as e:
            print(f"Error updating image settings: {e}")
            return  # Don't recalculate if there was an error
        
        # Update the image list to reflect changes
        self.refresh_image_list()
        
        # Mark images as not uploaded since settings changed
        if should_recalculate:
            self.mark_images_not_uploaded()
        
        # Update pulsed mode calculations when duration changes
        if self.projection_mode.get() == 'pulsed' and should_recalculate:
            # Force recalculation to update display
            self.calculate_cycles_from_runtime()
    
    def calculate_cycles_from_runtime(self):
        """Calculate number of cycles from total runtime"""
        if not self.images or self.projection_mode.get() != 'pulsed':
            return
        try:
            # Get total runtime and convert to seconds
            runtime_value = float(self.total_runtime_var.get())
            unit = self.runtime_unit_var.get()
            if unit == 'hrs':
                runtime_sec = runtime_value * 3600
            elif unit == 'min':
                runtime_sec = runtime_value * 60
            else:  # sec
                runtime_sec = runtime_value
            
            # Calculate cycle duration in seconds
            cycle_duration = sum(img.duration for img in self.images)
            if cycle_duration == 0:
                self.pulsed_calc_label.config(text="⚠ Set image durations first")
                return
            
            # Calculate number of cycles
            cycles = int(runtime_sec / cycle_duration)
            
            # Update display without triggering the other calculation
            if self.cycles_var.trace_vinfo():
                self.cycles_var.trace_vdelete('w', self.cycles_var.trace_vinfo()[0][1])
            self.cycles_var.set(str(cycles))
            self.cycles_var.trace('w', lambda *args: self.calculate_runtime_from_cycles())
            
            # Display info with appropriate units
            cycle_min = cycle_duration / 60
            self.pulsed_calc_label.config(
                text=f"→ {cycles} cycles × {cycle_duration}s ({cycle_min:.1f} min/cycle)"
            )
        except (ValueError, ZeroDivisionError):
            self.pulsed_calc_label.config(text="")
    
    def calculate_runtime_from_cycles(self):
        """Calculate total runtime from number of cycles"""
        if not self.images or self.projection_mode.get() != 'pulsed':
            return
        try:
            # Get number of cycles
            cycles = int(self.cycles_var.get())
            if cycles == 0:
                return
            
            # Calculate cycle duration in seconds
            cycle_duration = sum(img.duration for img in self.images)
            if cycle_duration == 0:
                self.pulsed_calc_label.config(text="⚠ Set image durations first")
                return
            
            # Calculate total runtime in seconds
            runtime_sec = cycles * cycle_duration
            
            # Convert to the selected unit
            unit = self.runtime_unit_var.get()
            if unit == 'hrs':
                runtime_value = runtime_sec / 3600
            elif unit == 'min':
                runtime_value = runtime_sec / 60
            else:  # sec
                runtime_value = runtime_sec
            
            # Update display without triggering the other calculation
            if self.total_runtime_var.trace_vinfo():
                self.total_runtime_var.trace_vdelete('w', self.total_runtime_var.trace_vinfo()[0][1])
            self.total_runtime_var.set(f"{runtime_value:.1f}")
            self.total_runtime_var.trace('w', lambda *args: self.calculate_cycles_from_runtime())
            
            # Display info
            cycle_min = cycle_duration / 60
            self.pulsed_calc_label.config(
                text=f"→ {runtime_value:.1f} {unit} ({cycles} cycles × {cycle_min:.1f} min/cycle)"
            )
        except (ValueError, ZeroDivisionError):
            self.pulsed_calc_label.config(text="")
    
    def display_preview(self, img):
        if img.thumbnail:
            self.preview_canvas.delete("all")
            # Canvas is fixed at 480x270 to maintain exact 16:9 aspect ratio
            canvas_w, canvas_h = 480, 270
            # Use mirrored thumbnail if mirror option is enabled
            thumb = img.thumbnail_mirrored if (self.mirror_preview_var.get() and hasattr(img, 'thumbnail_mirrored')) else img.thumbnail
            x, y = (canvas_w - thumb.width()) // 2, (canvas_h - thumb.height()) // 2
            self.preview_canvas.create_image(x, y, anchor=tk.NW, image=thumb)
            # Show range only if image is loaded (avoid triggering load for preview)
            if img.image_array is not None:
                self.preview_label.config(text=f"{os.path.basename(img.filepath)} | {img.mode} | Range: {img.image_array.min()}-{img.image_array.max()}", foreground="black")
            else:
                self.preview_label.config(text=f"{os.path.basename(img.filepath)} | {img.mode}", foreground="black")
    
    def update_preview_during_projection(self, img, status_text=""):
        """Thread-safe method to update preview during projection"""
        def _update():
            # Load thumbnail if not already loaded
            if img.thumbnail is None:
                try:
                    img.load_thumbnail()
                except:
                    pass  # If thumbnail load fails, skip preview update
            
            if img.thumbnail:
                self.preview_canvas.delete("all")
                canvas_w, canvas_h = 480, 270
                # Use mirrored thumbnail if mirror option is enabled
                thumb = img.thumbnail_mirrored if (self.mirror_preview_var.get() and hasattr(img, 'thumbnail_mirrored')) else img.thumbnail
                x, y = (canvas_w - thumb.width()) // 2, (canvas_h - thumb.height()) // 2
                self.preview_canvas.create_image(x, y, anchor=tk.NW, image=thumb)
                label_text = f"▶ {os.path.basename(img.filepath)} | {img.mode}"
                if status_text:
                    label_text += f" | {status_text}"
                self.preview_label.config(text=label_text, foreground="green")
        self.root.after(0, _update)
    
    def clear_preview(self):
        self.preview_canvas.delete("all")
        self.preview_label.config(text="No image selected", foreground="gray")
    
    def refresh_preview(self):
        """Refresh preview when mirror setting changes"""
        if self.selected_image_index is not None and self.selected_image_index < len(self.images):
            img = self.images[self.selected_image_index]
            if img.image_array is not None:
                self.display_preview(img)
    
    def refresh_image_list(self):
        for item in self.image_tree.get_children(): self.image_tree.delete(item)
        for img in self.images:
            # Format LED info column - show all enabled channels
            if img.led_enabled:
                enabled_channels = [ch for ch in ['A', 'B', 'C', 'D'] if img.led_channels[ch]['enabled']]
                if enabled_channels:
                    led_parts = [f"{ch}{img.led_channels[ch]['wavelength']}" for ch in enabled_channels]
                    led_info = ", ".join(led_parts)
                else:
                    led_info = "(none)"
            else:
                led_info = "-"
            self.image_tree.insert('', tk.END, values=(os.path.basename(img.filepath), img.mode, img.exposure, img.dark_time, img.duration, led_info))
        self.update_sequence_info()
    
    def update_sequence_info(self):
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        info = f"Total: {len(self.images)}\nMode: {self.projection_mode.get().title()}\n\n"
        if self.images:
            info += f"1-bit: {sum(1 for i in self.images if i.mode=='1bit')}\n8-bit: {sum(1 for i in self.images if i.mode=='8bit')}\n"
        self.info_text.insert(1.0, info)
        self.info_text.config(state=tk.DISABLED)
    
    def log_progress(self, msg):
        self.progress_text.config(state=tk.NORMAL)
        # If message is empty, insert blank line without timestamp for visual separation
        if msg == "":
            self.progress_text.insert(tk.END, "\n")
        else:
            self.progress_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.progress_text.config(state=tk.DISABLED)
        # Ensure the latest message is always visible
        self.progress_text.see(tk.END)
    
    def update_timer(self):
        """Update the projection timer display"""
        if not self.projecting or self.projection_start_time is None:
            return
        
        elapsed = time.time() - self.projection_start_time
        elapsed_str = self.format_time(elapsed)
        
        if self.projection_total_time is not None and self.projection_total_time > 0:
            # For pulsed mode with known duration
            remaining = max(0, self.projection_total_time - elapsed)
            remaining_str = self.format_time(remaining)
            progress_pct = min(100, (elapsed / self.projection_total_time) * 100)
            self.timer_label.config(text=f"⏱ {elapsed_str} elapsed | {remaining_str} remaining ({progress_pct:.1f}%)")
        else:
            # For constant/sequence mode (no end time)
            self.timer_label.config(text=f"⏱ {elapsed_str} elapsed")
        
        # Schedule next update in 1 second
        self.timer_update_id = self.root.after(1000, self.update_timer)
    
    def format_time(self, seconds):
        """Format seconds into readable time string"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    
    def validate_exposure_times(self, images_to_check):
        """Validate that exposure times are within hardware limits
        
        Validates both minimum and maximum exposure times:
        - 1-bit images: min 105μs, max as defined by hardware
        - 8-bit images: min 4046μs, max as defined by hardware
        """
        warnings = []
        errors = []
        
        # Define minimum exposure times in microseconds
        MIN_EXPOSURE_1BIT = 105    # 105 μs for 1-bit images
        MIN_EXPOSURE_8BIT = 4046   # 4046 μs for 8-bit images
        
        for img in images_to_check:
            # Check minimum exposure time
            if img.mode == '1bit' and img.exposure < MIN_EXPOSURE_1BIT:
                errors.append(f"{os.path.basename(img.filepath)}: {img.exposure}μs (<{MIN_EXPOSURE_1BIT}μs minimum for 1-bit)")
            elif img.mode == '8bit' and img.exposure < MIN_EXPOSURE_8BIT:
                errors.append(f"{os.path.basename(img.filepath)}: {img.exposure}μs (<{MIN_EXPOSURE_8BIT}μs minimum for 8-bit)")
            # Check maximum exposure time (existing check)
            elif img.exposure > MAX_SAFE_EXPOSURE_US:
                errors.append(f"{os.path.basename(img.filepath)}: {img.exposure}μs (>{MAX_SAFE_EXPOSURE_US/1000000:.3f}s maximum)")
            elif img.exposure > MAX_RECOMMENDED_EXPOSURE_US:
                warnings.append(f"{os.path.basename(img.filepath)}: {img.exposure}μs (>{MAX_RECOMMENDED_EXPOSURE_US/1000000:.3f}s recommended)")
        
        if errors:
            msg = "❌ Exposure time validation failed!\n\n"
            
            # Check if we have minimum exposure time violations
            min_errors = [e for e in errors if "minimum" in e]
            max_errors = [e for e in errors if "maximum" in e]
            
            if min_errors:
                msg += "• Some exposures are below the minimum required time:\n"
                for err in min_errors:
                    msg += f"  - {err}\n"
                msg += "\n  Minimum exposure times:\n"
                msg += f"  - 1-bit images: {MIN_EXPOSURE_1BIT} μs\n"
                msg += f"  - 8-bit images: {MIN_EXPOSURE_8BIT} μs\n\n"
                
            if max_errors:
                msg += "• Some exposures exceed the hardware limit:\n"
                for err in max_errors:
                    msg += f"  - {err}\n"
                msg += "\n  Projections will terminate early if these limits are exceeded.\n"
                msg += f"  For reliable operation, keep exposures ≤ {MAX_RECOMMENDED_EXPOSURE_US/1000000:.3f}s\n\n"
            
            msg += "💡 Solutions:\n"
            if min_errors:
                msg += "  - Increase exposure times to meet minimum requirements\n"
            if max_errors:
                msg += "  - Decrease exposure times or use multiple cycles\n"
                
            messagebox.showerror("Exposure Time Error", msg)
            return False
        
        if warnings:
            msg = f"⚠️ Some exposures exceed {MAX_RECOMMENDED_EXPOSURE_US/1000000:.3f}s (recommended safe limit):\n\n"
            for warn in warnings:
                msg += f"• {warn}\n"
            msg += f"\nThey may work up to {MAX_SAFE_EXPOSURE_US/1000000:.3f}s, but test your hardware.\n"
            msg += "For guaranteed reliability, keep exposures within recommended limits.\n\n"
            msg += "Continue anyway?"
            if not messagebox.askyesno("Exposure Time Warning", msg):
                return False
        
        return True
    
    def mark_images_not_uploaded(self):
        """Mark that images need to be re-uploaded to DMD"""
        self.images_uploaded = False
        self.uploaded_image_index = None
        self.update_button_states()
    
    def update_button_states(self):
        """Update the enabled/disabled state of control buttons based on current state"""
        if not self.connected:
            self.upload_btn.config(state=tk.DISABLED)
            self.start_btn.config(state=tk.DISABLED)
            return
        
        if self.projecting:
            # During projection
            self.upload_btn.config(state=tk.DISABLED)
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            return
        
        # Not projecting - check if we have images and if upload is needed
        has_images = len(self.images) > 0
        mode = self.projection_mode.get()
        
        # Pulsed and Nikon trigger modes don't benefit from pre-upload (upload on-demand)
        if mode in ['pulsed', 'nikon_trigger']:
            self.upload_btn.config(state=tk.DISABLED)
            self.start_btn.config(state=tk.NORMAL if has_images else tk.DISABLED)
        else:
            # Sequence and constant modes require pre-upload
            # Upload button enabled if images present and not already uploaded
            self.upload_btn.config(state=tk.NORMAL if (has_images and not self.images_uploaded) else tk.DISABLED)
            # Start button only enabled if images are uploaded
            self.start_btn.config(state=tk.NORMAL if (has_images and self.images_uploaded) else tk.DISABLED)
    
    def upload_to_dmd(self):
        """Pre-upload images to DMD without starting projection"""
        if not self.connected:
            messagebox.showerror("Error", "Not connected to DMD")
            return
        if not self.images:
            messagebox.showerror("Error", "No images to upload")
            return
        
        # Disable buttons during upload
        self.upload_btn.config(state=tk.DISABLED)
        self.start_btn.config(state=tk.DISABLED)
        self.proj_status_label.config(text="Uploading...")
        self.proj_info_label.config(text="")
        
        # Run upload in background thread
        self.upload_thread = threading.Thread(target=self._do_upload, daemon=True)
        self.upload_thread.start()
    
    def _do_upload(self):
        """Background thread for uploading images to DMD"""
        try:
            mode = self.projection_mode.get()
            
            # Load all images into memory first
            self.root.after(0, lambda: self.proj_info_label.config(text="Loading images..."))
            for img in self.images:
                if img.image_array is None:
                    img.load_image()
            
            # Validate exposure times
            self.root.after(0, lambda: self.proj_info_label.config(text="Validating settings..."))
            if not self.validate_exposure_times(self.images if mode == 'sequence' else [self.images[self.selected_image_index]] if self.selected_image_index is not None else self.images):
                self.root.after(0, self._upload_failed)
                return
            
            # Upload to DMD based on mode
            if mode == 'sequence':
                self._upload_sequence()
            elif mode == 'constant':
                self._upload_constant()
            
            # Success - pass mode and relevant info to _upload_complete
            self.root.after(0, lambda: self._upload_complete(mode))
            
        except Exception as e:
            self.root.after(0, lambda err=str(e): self._upload_error(err))
    
    def _upload_sequence(self):
        """Upload sequence mode images"""
        self.root.after(0, lambda: self.proj_info_label.config(text=f"Uploading {len(self.images)} images..."))
        
        # Check for mixed bit depths
        has_1bit = any(img.mode == '1bit' for img in self.images)
        has_8bit = any(img.mode == '8bit' for img in self.images)
        
        if has_1bit and has_8bit:
            raise ValueError("Cannot mix 1-bit and 8-bit images in sequence mode")
        
        sequence_mode = self.images[0].mode
        
        # Validate sequence length
        num_images = len(self.images)
        max_1bit = self.settings['max_patterns_1bit']
        max_8bit = self.settings['max_patterns_8bit']
        if sequence_mode == '1bit' and num_images > max_1bit:
            raise ValueError(f"Maximum {max_1bit} 1-bit images in sequence. Current: {num_images}")
        elif sequence_mode == '8bit' and num_images > max_8bit:
            raise ValueError(f"Maximum {max_8bit} 8-bit images in sequence. Current: {num_images}")
        
        # Get repeat count
        rep_input = int(self.seq_repeat_count_var.get()) if self.seq_repeat_count_var.get().isdigit() else 0
        if rep_input == 0:
            rep = 0xFFFFFFFF
        else:
            rep = rep_input * len(self.images)
        
        # Prepare sequence data
        image_arrays = [img.image_array for img in self.images]
        exposures = [img.exposure for img in self.images]
        dark_times = [img.dark_time for img in self.images]
        
        # Upload to DMD with GUI progress callback
        if sequence_mode == '1bit':
            self.dlp.defsequence(image_arrays, exposures, [False]*len(self.images), dark_times, [1]*len(self.images), rep, 
                               progress_callback=self.log_progress)
        else:
            self.dlp.defsequence_8bit(image_arrays, exposures, [False]*len(self.images), dark_times, [1]*len(self.images), rep,
                                     progress_callback=self.log_progress)
    
    def _upload_constant(self):
        """Upload constant mode image"""
        if self.selected_image_index is None:
            raise ValueError("No image selected for constant mode")
        
        img = self.images[self.selected_image_index]
        self.root.after(0, lambda: self.proj_info_label.config(text="Uploading image..."))
        
        # Use infinite repeat for constant mode
        rep = 0xFFFFFFFF
        
        if img.mode == '1bit':
            self.dlp.defsequence([img.image_array], [img.exposure], [False], [img.dark_time], [1], rep,
                               progress_callback=self.log_progress)
        else:
            self.dlp.defsequence_8bit([img.image_array], [img.exposure], [False], [img.dark_time], [1], rep,
                                     progress_callback=self.log_progress)
    
    def _upload_complete(self, mode):
        """Called when upload completes successfully"""
        self.images_uploaded = True
        
        # Track what was uploaded
        if mode == 'constant':
            self.uploaded_image_index = self.selected_image_index
            img = self.images[self.uploaded_image_index]
            filename = os.path.basename(img.filepath)
            status_text = f"Ready: {filename} ({img.mode})"
            info_text = f"✓ Uploaded: {filename}"
            self.log_progress(f"Upload complete! Uploaded: {filename} ({img.mode})")
        else:  # sequence
            self.uploaded_image_index = None  # Not applicable for sequence
            num_images = len(self.images)
            mode_type = self.images[0].mode
            status_text = f"Ready: {num_images} images ({mode_type})"
            info_text = f"✓ Uploaded: {num_images} images"
            self.log_progress(f"Upload complete! Uploaded {num_images} {mode_type} images")
        
        self.proj_status_label.config(text=status_text)
        self.proj_info_label.config(text=info_text)
        self.log_progress("Press Start to begin projection.")
        self.update_button_states()
    
    def _upload_failed(self):
        """Called when upload validation fails"""
        self.images_uploaded = False
        self.uploaded_image_index = None
        self.proj_status_label.config(text="Ready")
        self.proj_info_label.config(text="")
        self.log_progress("Upload cancelled")
        self.update_button_states()
    
    def _upload_error(self, error_msg):
        """Called when upload encounters an error"""
        self.images_uploaded = False
        self.uploaded_image_index = None
        self.proj_status_label.config(text="Upload Failed")
        self.proj_info_label.config(text="")
        self.log_progress(f"Upload error: {error_msg}")
        messagebox.showerror("Upload Error", f"Failed to upload images:\n\n{error_msg}")
        self.update_button_states()
    
    def start_projection(self):
        if not self.connected:
            messagebox.showerror("Error", "Not connected")
            return
        if not self.images:
            messagebox.showerror("Error", "No images")
            return
        
        # Check if images need to be uploaded first (for sequence/constant modes)
        mode = self.projection_mode.get()
        if mode in ['sequence', 'constant'] and not self.images_uploaded and not self.demo_mode:
            messagebox.showerror("Upload Required", "Please upload images to DMD first using the 'Upload to DMD' button.")
            return
        
        for img in self.images:
            if img.image_array is None:
                try: img.load_image()
                except Exception as e:
                    messagebox.showerror("Error", f"Load failed: {e}")
                    return
        
        # Add separator line for visual clarity
        self.log_progress("")
        
        # Warn if in demo mode
        if self.demo_mode:
            self.log_progress("[DEMO MODE] Simulating projection (no hardware output)")
        
        # Check if we can use pre-uploaded sequence
        skip_upload = self.images_uploaded and mode in ['sequence', 'constant']
        
        if skip_upload and not self.demo_mode:
            self.log_progress("Using pre-uploaded sequence (instant start!)")
        
        self.stop_projection_flag = False
        self.projecting = True
        self.update_button_states()
        self.proj_status_label.config(text="Projecting" if not self.demo_mode else "Simulating")
        
        # Initialize timer
        self.projection_start_time = time.time()
        
        # Calculate total time based on mode
        mode = self.projection_mode.get()
        if mode == 'pulsed':
            # Get total runtime in seconds
            runtime_value = float(self.total_runtime_var.get())
            unit = self.runtime_unit_var.get()
            if unit == 'hrs':
                self.projection_total_time = runtime_value * 3600
            elif unit == 'min':
                self.projection_total_time = runtime_value * 60
            else:
                self.projection_total_time = runtime_value
        elif mode == 'constant':
            # Check if constant mode has a time limit
            if not self.constant_infinite_var.get():
                time_value = float(self.constant_time_var.get())
                unit = self.constant_time_unit_var.get()
                if unit == 'hrs':
                    self.projection_total_time = time_value * 3600
                elif unit == 'min':
                    self.projection_total_time = time_value * 60
                else:
                    self.projection_total_time = time_value
            else:
                self.projection_total_time = None
        else:
            # Sequence mode runs indefinitely
            self.projection_total_time = None
        
        # Start timer updates
        self.update_timer()
        
        # Route to appropriate projection method based on mode
        if mode == 'sequence':
            self.projection_thread = threading.Thread(target=lambda: self.run_sequence(skip_upload), daemon=True)
        elif mode == 'constant':
            self.projection_thread = threading.Thread(target=lambda: self.run_constant(skip_upload), daemon=True)
        elif mode == 'pulsed':
            self.projection_thread = threading.Thread(target=self.run_pulsed, daemon=True)
        elif mode == 'nikon_trigger':
            self.projection_thread = threading.Thread(target=self.run_nikon_trigger, daemon=True)
        
        if self.projection_thread:
            self.projection_thread.start()
    
    def stop_projection(self):
        self.stop_projection_flag = True
        if self.dlp and not self.demo_mode:
            self.dlp.stopsequence()
        
        # Turn off all CoolLED channels if connected (both real and demo mode)
        if self.coolled_connected:
            try:
                if not self.coolled_demo_mode:
                    self.coolled.all_off()
                    self.log_progress("LED: All channels OFF")
                else:
                    self.log_progress("[DEMO] LED: All channels OFF")
            except Exception as e:
                self.log_progress(f"Warning: Could not turn off LED: {e}")
        
        self.projecting = False
        
        # Stop timer updates
        if self.timer_update_id:
            self.root.after_cancel(self.timer_update_id)
            self.timer_update_id = None
        self.timer_label.config(text="")
        
        # Restore upload status if images are still uploaded
        if self.images_uploaded:
            mode = self.projection_mode.get()
            if mode == 'constant' and self.uploaded_image_index is not None:
                img = self.images[self.uploaded_image_index]
                filename = os.path.basename(img.filepath)
                self.proj_status_label.config(text=f"Ready: {filename} ({img.mode})")
                self.proj_info_label.config(text=f"✓ Uploaded: {filename}")
            elif mode == 'sequence':
                num_images = len(self.images)
                mode_type = self.images[0].mode if self.images else '1bit'
                self.proj_status_label.config(text=f"Ready: {num_images} images ({mode_type})")
                self.proj_info_label.config(text=f"✓ Uploaded: {num_images} images")
            else:
                self.proj_status_label.config(text="Ready")
                self.proj_info_label.config(text="")
        else:
            self.proj_status_label.config(text="Ready")
            self.proj_info_label.config(text="")
        
        self.update_button_states()
        self.log_progress("Stopped" if not self.demo_mode else "[DEMO] Stopped simulation")
    
    def run_sequence(self, skip_upload=False):
        """Sequence mode: Projects all images in sequence (1-bit or 8-bit)"""
        try:
            if skip_upload:
                self.log_progress("Starting pre-uploaded sequence..." if not self.demo_mode else "[DEMO] Starting sequence projection simulation...")
            else:
                self.log_progress("Starting sequence projection..." if not self.demo_mode else "[DEMO] Starting sequence projection simulation...")
            
            # Check for empty sequence
            if not self.images:
                self.log_progress("Error: No images in the sequence.")
                self.root.after(0, self.stop_projection)
                return
                
            # Check if we have mixed bit depths (not supported in a single sequence)
            has_1bit = any(img.mode == '1bit' for img in self.images)
            has_8bit = any(img.mode == '8bit' for img in self.images)
            
            if has_1bit and has_8bit:
                self.log_progress("Error: Cannot mix 1-bit and 8-bit images in the same sequence. Please use all 1-bit or all 8-bit images.")
                self.root.after(0, self.stop_projection)
                return
                
            # Determine sequence mode based on first image
            sequence_mode = self.images[0].mode
            
            # Validate sequence length against hardware limits
            num_images = len(self.images)
            max_1bit = self.settings['max_patterns_1bit']
            max_8bit = self.settings['max_patterns_8bit']
            if sequence_mode == '1bit' and num_images > max_1bit:
                self.log_progress(f"Error: Maximum of {max_1bit} 1-bit images allowed in sequence mode. Current: {num_images} images.")
                self.root.after(0, self.stop_projection)
                return
            elif sequence_mode == '8bit' and num_images > max_8bit:
                self.log_progress(f"Error: Maximum of {max_8bit} 8-bit images allowed in sequence mode. Current: {num_images} images.")
                self.root.after(0, self.stop_projection)
                return
            
            # DLPC900 repeat count = TOTAL pattern displays, not sequence loops
            # User enters "cycles", we need to multiply by number of images
            rep_input = int(self.seq_repeat_count_var.get()) if self.seq_repeat_count_var.get().isdigit() else 0
            if rep_input == 0:
                rep = 0xFFFFFFFF  # Infinite
            else:
                # For K cycles of N images: repeat = K * N total displays
                rep = rep_input * len(self.images)
            
            # Ensure all images are loaded
            for img in self.images:
                if img.image_array is None:
                    img.load_image()
            
            # Validate exposure times before starting (both demo and non-demo modes)
            if not self.validate_exposure_times(self.images):
                self.root.after(0, self.stop_projection)
                return
            
            # Check and activate LED using first image's settings
            first_img = self.images[0]
            if first_img.led_enabled and self.coolled_connected:
                try:
                    enabled_channels = [ch for ch in ['A', 'B', 'C', 'D'] if first_img.led_channels[ch]['enabled']]
                    if enabled_channels:
                        for channel in enabled_channels:
                            wavelength = first_img.led_channels[channel]['wavelength']
                            intensity = first_img.led_channels[channel]['intensity']
                            
                            if not self.coolled_demo_mode:
                                self.coolled.load_wavelength(wavelength)
                                time.sleep(0.6)  # Wait for mechanical filter wheel rotation (0.6 sec for troubleshooting)
                                self.coolled.set_intensity(channel, intensity)
                                time.sleep(0.05)  # Wait for channel to activate
                                self.log_progress(f"LED: Ch{channel} {wavelength}nm @ {intensity}% - ON")
                            else:
                                self.log_progress(f"[DEMO] LED: Ch{channel} {wavelength}nm @ {intensity}% - ON")
                    else:
                        self.log_progress("LED: Enabled but no channels selected")
                except Exception as e:
                    self.log_progress(f"Warning: LED control failed: {e}")
            elif first_img.led_enabled and not self.coolled_connected:
                self.log_progress("⚠ Warning: LED enabled but CoolLED not connected")
            else:
                self.log_progress("LED: OFF (not enabled)")
            
            if self.demo_mode:
                # Demo mode
                self.log_progress(f"[DEMO] Would project {len(self.images)} {sequence_mode} image(s) in sequence:")
                for idx, img in enumerate(self.images, 1):
                    self.log_progress(f"[DEMO]   {idx}. {os.path.basename(img.filepath)} ({img.mode}, Exposure: {img.exposure}μs, Dark: {img.dark_time}μs)")
                self.log_progress(f"[DEMO] Cycles: {'infinite' if rep == 0xFFFFFFFF else f'{rep_input} ({rep} total displays)'}")
                if rep == 0xFFFFFFFF:
                    self.log_progress("[DEMO] Sequence would cycle continuously until stopped...")
                else:
                    self.log_progress(f"[DEMO] Sequence would run for {rep} displays then stop automatically")
            else:
                # Real hardware mode
                if not skip_upload:
                    self.log_progress(f"Projecting sequence of {len(self.images)} {sequence_mode} image(s):")
                    for idx, img in enumerate(self.images, 1):
                        self.log_progress(f"  {idx}. {os.path.basename(img.filepath)} ({img.mode}, Exposure: {img.exposure}μs, Dark: {img.dark_time}μs)")
                    
                    # Prepare sequence based on image mode
                    image_arrays = [img.image_array for img in self.images]
                    exposures = [img.exposure for img in self.images]
                    dark_times = [img.dark_time for img in self.images]
                    
                    max_1bit = self.settings['max_patterns_1bit']
                    max_8bit = self.settings['max_patterns_8bit']
                    if sequence_mode == '1bit':
                        self.log_progress(f"Using 1-bit sequence mode (max {max_1bit} patterns)")
                        self.dlp.defsequence(image_arrays, exposures, [False]*len(self.images), dark_times, [1]*len(self.images), rep,
                                           progress_callback=self.log_progress)
                    else:  # 8-bit mode
                        self.log_progress(f"Using 8-bit sequence mode (max {max_8bit} patterns)")
                        self.dlp.defsequence_8bit(image_arrays, exposures, [False]*len(self.images), dark_times, [1]*len(self.images), rep,
                                                 progress_callback=self.log_progress)
                
                # Start sequence (either new or pre-uploaded)
                self.dlp.startsequence()
                self.log_progress("Sequence projection started")
            
            # Cycle through images in preview to visualize sequence
            idx = 0
            total_displays = rep if rep != 0xFFFFFFFF else None  # None means infinite
            sequence_start_time = time.time()
            
            while self.projecting and not self.stop_projection_flag:
                # Check if we've reached the target number of displays (for finite sequences)
                if total_displays is not None and idx >= total_displays:
                    self.log_progress("Sequence completed!")
                    self.root.after(0, self.stop_projection)
                    break
                
                img = self.images[idx % len(self.images)]
                if total_displays is not None:
                    # Show progress for finite sequences
                    self.update_preview_during_projection(img, f"Frame {idx % len(self.images) + 1}/{len(self.images)} | Display {idx+1}/{total_displays}")
                else:
                    # Show frame info for infinite sequences
                    self.update_preview_during_projection(img, f"Frame {idx % len(self.images) + 1}/{len(self.images)}")
                
                # Calculate time to display based on exposure + dark time (in seconds)
                display_time = (img.exposure + img.dark_time) / 1000000.0  # Convert μs to seconds
                time.sleep(display_time)
                idx += 1
                
        except Exception as e:
            self.log_progress(f"Error: {e}")
            self.root.after(0, self.stop_projection)
    
    def run_constant(self, skip_upload=False):
        """Constant mode: Projects only the selected image"""
        try:
            if self.selected_image_index is None:
                self.log_progress("Error: No image selected. Please select an image from the list.")
                self.root.after(0, self.stop_projection)
                return
            
            img = self.images[self.selected_image_index]
            infinite = self.constant_infinite_var.get()
            
            # Calculate total projection time (if not infinite)
            total_time = None
            if not infinite:
                time_value = float(self.constant_time_var.get())
                unit = self.constant_time_unit_var.get()
                if unit == 'hrs':
                    total_time = time_value * 3600
                elif unit == 'min':
                    total_time = time_value * 60
                else:
                    total_time = time_value
            
            if skip_upload:
                self.log_progress("Starting pre-uploaded constant projection..." if not self.demo_mode else "[DEMO] Starting constant projection simulation...")
            else:
                self.log_progress("Starting constant projection..." if not self.demo_mode else "[DEMO] Starting constant projection simulation...")
            
            # Validate exposure time before starting
            if not self.demo_mode and not self.validate_exposure_times([img]):
                self.root.after(0, self.stop_projection)
                return
            
            # Check and activate LED using selected image's settings
            if img.led_enabled and self.coolled_connected:
                try:
                    enabled_channels = [ch for ch in ['A', 'B', 'C', 'D'] if img.led_channels[ch]['enabled']]
                    if enabled_channels:
                        for channel in enabled_channels:
                            wavelength = img.led_channels[channel]['wavelength']
                            intensity = img.led_channels[channel]['intensity']
                            
                            if not self.coolled_demo_mode:
                                self.coolled.load_wavelength(wavelength)
                                time.sleep(0.6)  # Wait for mechanical filter wheel rotation (0.6 sec for troubleshooting)
                                self.coolled.set_intensity(channel, intensity)
                                time.sleep(0.05)  # Wait for channel to activate
                                self.log_progress(f"LED: Ch{channel} {wavelength}nm @ {intensity}% - ON")
                            else:
                                self.log_progress(f"[DEMO] LED: Ch{channel} {wavelength}nm @ {intensity}% - ON")
                    else:
                        self.log_progress("LED: Enabled but no channels selected")
                except Exception as e:
                    self.log_progress(f"Warning: LED control failed: {e}")
            elif img.led_enabled and not self.coolled_connected:
                self.log_progress("⚠ Warning: LED enabled but CoolLED not connected")
            else:
                self.log_progress("LED: OFF (not enabled)")
            
            # Update preview to show the projected image
            self.update_preview_during_projection(img, "Projecting...")
            
            filename = os.path.basename(img.filepath)
            
            if self.demo_mode:
                # Demo mode
                self.log_progress(f"[DEMO] Would project selected image: {filename}")
                self.log_progress(f"[DEMO] Mode: {img.mode}, Exposure: {img.exposure}μs, Dark Time: {img.dark_time}μs")
                self.log_progress(f"[DEMO] Duration: {total_time:.1f}s" if total_time else "[DEMO] Duration: Infinite")
                
                if total_time:
                    # Wait for the full projection time in demo mode
                    self.log_progress(f"[DEMO] Projecting for {total_time:.1f}s...")
                    start_time = time.time()
                    while time.time() - start_time < total_time:
                        if self.stop_projection_flag:
                            break
                        time.sleep(0.1)  # Check every 100ms
                    
                    if not self.stop_projection_flag:
                        self.log_progress(f"[DEMO] Constant projection completed")
                        self.root.after(0, self.stop_projection)
                else:
                    self.log_progress("[DEMO] Projection would continue until stopped...")
            else:
                # Real hardware mode
                if not skip_upload:
                    self.log_progress(f"Projecting selected image: {filename}")
                    self.log_progress(f"Mode: {img.mode}, Exposure: {img.exposure}μs, Dark Time: {img.dark_time}μs")
                    self.log_progress(f"Duration: {total_time:.1f}s" if total_time else "Duration: Infinite (until stopped)")
                    
                    # Use 0xFFFFFFFF for infinite projection (DLPC900 standard)
                    rep = 0xFFFFFFFF
                    
                    if img.mode == '1bit':
                        # Project single 1-bit image
                        self.dlp.defsequence([img.image_array], [img.exposure], [False], [img.dark_time], [1], rep,
                                           progress_callback=self.log_progress)
                    else:
                        # Project single 8-bit image
                        self.dlp.defsequence_8bit([img.image_array], [img.exposure], [False], [img.dark_time], [1], rep,
                                                 progress_callback=self.log_progress)
                
                # Start sequence (either new or pre-uploaded)
                self.dlp.startsequence()
                self.log_progress("Constant projection started ({})" .format(img.mode))
                
                # If projection time is specified, wait then auto-stop
                if total_time:
                    self.log_progress(f"Will auto-stop after {total_time:.1f}s")
                    
                    # Wait for completion, checking stop flag periodically
                    start_time = time.time()
                    while time.time() - start_time < total_time:
                        if self.stop_projection_flag:
                            break
                        time.sleep(0.1)  # Check every 100ms
                    
                    if not self.stop_projection_flag:
                        self.log_progress("Constant projection time completed")
                        self.root.after(0, self.stop_projection)
        except Exception as e:
            self.log_progress(f"Error: {e}")
            self.root.after(0, self.stop_projection)
    
    def run_pulsed(self):
        try:
            # Get runtime and convert to seconds based on unit
            runtime_value = float(self.total_runtime_var.get())
            unit = self.runtime_unit_var.get()
            if unit == 'hrs':
                runtime_sec = runtime_value * 3600
            elif unit == 'min':
                runtime_sec = runtime_value * 60
            else:
                runtime_sec = runtime_value
            
            cycle_dur = sum(i.duration for i in self.images)
            cycles = int(runtime_sec / cycle_dur) if cycle_dur > 0 else 1
            
            self.log_progress("Starting pulsed projection..." if not self.demo_mode else "[DEMO] Starting pulsed projection simulation...")
            
            # Pre-load all images to minimize delays during transitions
            if not self.demo_mode:
                self.log_progress("Pre-loading all images...")
                for img in self.images:
                    if img.image_array is None:
                        img.load_image()
                
                # Validate exposure times before starting
                if not self.validate_exposure_times(self.images):
                    self.root.after(0, self.stop_projection)
                    return
            
            self.log_progress(f"Total cycles: {cycles}, Cycle duration: {cycle_dur}s")
            
            # Get timing mode preference
            timing_mode = self.timing_mode_var.get()
            if timing_mode == "precise_total":
                self.log_progress("Timing Mode: Precise Total Time (compensating for upload delays)")
            else:
                self.log_progress("Timing Mode: Precise Pulse Time (exact image durations)")
            
            # Check if any images have LED enabled
            led_images = [img for img in self.images if img.led_enabled]
            if led_images:
                if self.coolled_connected:
                    self.log_progress(f"CoolLED control enabled for {len(led_images)} image(s)" + (" [DEMO]" if self.coolled_demo_mode else ""))
                else:
                    self.log_progress("⚠ Warning: Some images have LED enabled but CoolLED not connected")
            
            start_time = time.time()
            target_end_time = start_time + runtime_sec  # Target time for precise_total mode
            
            for c in range(1, cycles + 1):
                if self.stop_projection_flag: break
                
                self.log_progress(f"{'[DEMO] ' if self.demo_mode else ''}Cycle {c}/{cycles}")
                
                for idx, img in enumerate(self.images):
                    if self.stop_projection_flag: break
                    
                    # Update preview to show current image
                    if img.led_enabled:
                        enabled_channels = [ch for ch in ['A', 'B', 'C', 'D'] if img.led_channels[ch]['enabled']]
                        if enabled_channels:
                            led_parts = [f"{ch}{img.led_channels[ch]['wavelength']}" for ch in enabled_channels]
                            led_status = f"LED: {', '.join(led_parts)}"
                        else:
                            led_status = ""
                    else:
                        led_status = ""
                    preview_text = f"{img.duration}s | {led_status}" if led_status else f"{img.duration}s"
                    self.update_preview_during_projection(img, preview_text)
                    
                    filename = os.path.basename(img.filepath)
                    
                    if self.demo_mode:
                        # Demo mode: simulate projection with full duration
                        # Turn off ALL CoolLED channels first
                        if self.coolled_connected and not self.coolled_demo_mode:
                            self.coolled.all_off()
                        
                        # Control CoolLED if enabled for this image
                        if img.led_enabled and self.coolled_connected:
                            enabled_channels = [ch for ch in ['A', 'B', 'C', 'D'] if img.led_channels[ch]['enabled']]
                            if enabled_channels:
                                for channel in enabled_channels:
                                    wavelength = img.led_channels[channel]['wavelength']
                                    intensity = img.led_channels[channel]['intensity']
                                    self.log_progress(f"  [DEMO] LED: Ch{channel} {wavelength}nm @ {intensity}% - ON")
                        elif img.led_enabled and not self.coolled_connected:
                            self.log_progress(f"  ⚠ LED enabled but not connected")
                        
                        self.log_progress(f"[DEMO] Projecting {filename} ({img.mode}) for {img.duration}s...")
                        time.sleep(img.duration)  # Use full duration in demo mode
                    else:
                        # Real hardware mode
                        self.log_progress(f"Projecting {filename} ({img.mode}) for {img.duration}s...")
                        
                        # Track time for upload compensation
                        image_start_time = time.time()
                        
                        # CRITICAL SYNCHRONIZATION ORDER:
                        # Stop DMD first to create dark period, then switch LEDs (invisible transition)
                        
                        # Determine which channels should be active for the new image
                        target_channels = {}
                        if self.coolled_connected and img.led_enabled:
                            for ch in ['A', 'B', 'C', 'D']:
                                if img.led_channels[ch]['enabled']:
                                    target_channels[ch] = {
                                        'wavelength': img.led_channels[ch]['wavelength'],
                                        'intensity': img.led_channels[ch]['intensity']
                                    }
                        
                        # Step 1: Stop current DMD sequence (screen goes dark instantly)
                        # This hides any sequential LED switching
                        self.dlp.stopsequence()
                        time.sleep(0.02)
                        
                        # Step 2: Turn off all LED channels (now invisible because DMD is dark)
                        if self.coolled_connected:
                            for ch in ['A', 'B', 'C', 'D']:
                                self.coolled.send_command(f"CSS{ch}SN000")
                            time.sleep(0.1)  # Wait for all turn-off commands to complete
                        
                        # Step 3: Upload new DMD pattern (this takes time, especially for 8-bit)
                        upload_start = time.time()
                        if img.mode == '1bit':
                            self.dlp.defsequence([img.image_array], [img.exposure], [False], [img.dark_time], [1], 0xFFFFFFFF,
                                               progress_callback=self.log_progress)
                        else:
                            self.dlp.defsequence_8bit([img.image_array], [img.exposure], [False], [img.dark_time], [1], 0xFFFFFFFF,
                                                     progress_callback=self.log_progress)
                        upload_time = time.time() - upload_start
                        
                        # Step 4: Configure and turn on the target LED channels (still in dark period)
                        if self.coolled_connected and target_channels:
                            for channel, settings in target_channels.items():
                                wavelength = settings['wavelength']
                                intensity = settings['intensity']
                                
                                # Load wavelength for this specific channel
                                # This triggers mechanical filter wheel rotation - needs significant time!
                                self.coolled.send_command(f"LOAD:{wavelength}")
                                time.sleep(0.6)  # 0.6 sec for mechanical wheel rotation
                                
                                # Set intensity to turn on the channel
                                cmd = f"CSS{channel}SN{int(intensity):03d}"
                                self.coolled.send_command(cmd)
                                time.sleep(0.05)  # Wait for activation
                                
                                self.log_progress(f"  LED: Ch{channel} {wavelength}nm @ {intensity}% - ON")
                        elif img.led_enabled and not self.coolled_connected:
                            self.log_progress(f"  ⚠ LED enabled but not connected")
                        
                        # Step 5: Start DMD sequence - now LED and pattern are synchronized
                        self.dlp.startsequence()
                        
                        # Calculate sleep duration based on timing mode
                        if timing_mode == "precise_total":
                            # Compensate for upload time to maintain precise total runtime
                            # Calculate how long this image should take in ideal conditions
                            elapsed = time.time() - image_start_time
                            sleep_duration = max(0, img.duration - elapsed)
                            
                            # Additional check: don't exceed target end time
                            time_until_target = target_end_time - time.time()
                            if time_until_target < sleep_duration:
                                sleep_duration = max(0, time_until_target)
                            
                            if upload_time > 0.01:  # Only log significant upload times (>10ms)
                                self.log_progress(f"  Upload: {upload_time*1000:.1f}ms, Adjusted sleep: {sleep_duration:.3f}s")
                        else:
                            # Precise pulse time: maintain exact image duration regardless of upload time
                            sleep_duration = img.duration
                        
                        # Sleep for the calculated projection duration
                        time.sleep(sleep_duration)
                        # Don't stop sequence here - let it continue until next image or end of all cycles
                    
                    # Note: LEDs will be turned off at the start of the next image loop
                    # or at the end of all cycles (see below)
                
                # Progress update
                if c % 5 == 0 or c == cycles:  # Update every 5 cycles or at end
                    elapsed = time.time() - start_time
                    remaining = (cycles - c) * cycle_dur
                    self.log_progress(f"Progress: {c}/{cycles} cycles ({c/cycles*100:.1f}%) | Elapsed: {elapsed/60:.1f}min | Remaining: ~{remaining/60:.1f}min")
            
            # Stop DMD sequence after all cycles complete
            if not self.demo_mode:
                self.dlp.stopsequence()
            
            # Ensure all LEDs are off at the end
            if self.coolled_connected:
                if not self.coolled_demo_mode:
                    self.coolled.all_off()
                    self.log_progress("LED: All channels OFF")
                else:
                    self.log_progress("[DEMO] LED: All channels OFF")
            
            # Report timing accuracy
            actual_runtime = time.time() - start_time
            expected_runtime = runtime_sec
            timing_error = actual_runtime - expected_runtime
            timing_error_pct = (timing_error / expected_runtime) * 100 if expected_runtime > 0 else 0
            
            self.log_progress(f"Timing Report:")
            self.log_progress(f"  Expected: {expected_runtime/60:.2f}min ({expected_runtime:.1f}s)")
            self.log_progress(f"  Actual: {actual_runtime/60:.2f}min ({actual_runtime:.1f}s)")
            self.log_progress(f"  Error: {timing_error:+.2f}s ({timing_error_pct:+.2f}%)")
            if timing_mode == "precise_total" and abs(timing_error_pct) < 1.0:
                self.log_progress(f"  ✓ Timing accuracy: Excellent (<1% error)")
            elif timing_mode == "precise_pulse":
                self.log_progress(f"  Note: Expected drift in precise pulse mode")
            
            self.log_progress("Pulsed projection completed!" if not self.demo_mode else "[DEMO] Pulsed projection simulation completed!")
            self.root.after(0, self.stop_projection)
            
        except Exception as e:
            self.log_progress(f"Error: {e}")
            # Stop DMD sequence on error
            if not self.demo_mode and self.dlp:
                try:
                    self.dlp.stopsequence()
                except:
                    pass
            # Ensure LEDs are off on error
            if self.coolled_connected:
                try:
                    if not self.coolled_demo_mode:
                        self.coolled.all_off()
                        self.log_progress("LED: All channels OFF (error cleanup)")
                    else:
                        self.log_progress("[DEMO] LED: All channels OFF (error cleanup)")
                except:
                    pass
            self.root.after(0, self.stop_projection)
    
    def run_nikon_trigger(self):
        """Nikon NIS Trigger mode: File-based synchronization"""
        try:
            self.log_progress("Nikon NIS Trigger mode started")
            self.log_progress(f"Monitoring: {self.settings['trigger_on_off_path']}")
            self.log_progress(f"           {self.settings['trigger_next_path']}")
            self.log_progress("Waiting for trigger files...")
            
            # Initialize tracking variables
            last_on_off_value = 0
            last_next_value = 0
            current_pattern_index = 0
            is_projecting = False
            
            # File paths from settings
            on_off_path = self.settings['trigger_on_off_path']
            next_path = self.settings['trigger_next_path']
            
            # Monitoring loop
            while not self.stop_projection_flag:
                try:
                    # Read trigger_on_off.txt
                    try:
                        with open(on_off_path, 'r') as f:
                            on_off_value = int(f.read().strip())
                    except:
                        on_off_value = 0
                    
                    # Read trigger_next.txt
                    try:
                        with open(next_path, 'r') as f:
                            next_value = int(f.read().strip())
                    except:
                        next_value = 0
                    
                    # Update status display
                    self.root.after(0, lambda: self.nikon_on_off_status.config(
                        text=str(on_off_value), 
                        foreground='green' if on_off_value == 1 else 'red'
                    ))
                    self.root.after(0, lambda nv=next_value: self.nikon_next_status.config(text=str(nv)))
                    
                    # Check for ON/OFF state change
                    if on_off_value != last_on_off_value:
                        if on_off_value == 1 and not is_projecting:
                            # Start projection
                            self.log_progress(f"✓ Trigger ON detected (value={on_off_value})")
                            is_projecting = True
                            last_next_value = next_value
                            
                            # Check if we should start with black frame
                            if self.nikon_black_frame_var.get():
                                # Project black frame initially
                                self.log_progress("  Starting with black frame (prevents double-trigger)")
                                current_pattern_index = -1  # Special value for black frame
                                self._project_black_frame_nikon_trigger()
                            else:
                                # Project first pattern immediately
                                current_pattern_index = 0
                                self._project_single_pattern_nikon_trigger(current_pattern_index)
                            
                        elif on_off_value == 0 and is_projecting:
                            # Stop projection
                            self.log_progress(f"✓ Trigger OFF detected (value={on_off_value})")
                            is_projecting = False
                            if not self.demo_mode:
                                self.dlp.stopsequence()
                            self.log_progress("Projection stopped, waiting for next trigger...")
                        
                        last_on_off_value = on_off_value
                    
                    # Check for NEXT increment (only when projecting)
                    if is_projecting and next_value != last_next_value:
                        self.log_progress(f"✓ NEXT increment detected ({last_next_value} → {next_value})")
                        last_next_value = next_value
                        
                        # Advance to next pattern
                        current_pattern_index += 1
                        if current_pattern_index >= len(self.images):
                            current_pattern_index = 0  # Wrap around
                            self.log_progress("  Wrapped to first pattern")
                        
                        # Project next pattern
                        self._project_single_pattern_nikon_trigger(current_pattern_index)
                    
                    # Small delay to avoid excessive file reading
                    time.sleep(0.1)  # Check every 100ms
                    
                except Exception as e:
                    self.log_progress(f"Warning: Error reading trigger files: {e}")
                    time.sleep(0.5)  # Longer delay on error
            
            # Cleanup when stopped
            if not self.demo_mode:
                self.dlp.stopsequence()
            self.log_progress("Nikon NIS Trigger mode stopped")
            self.root.after(0, self.stop_projection)
            
        except Exception as e:
            self.log_progress(f"Error in Nikon trigger mode: {e}")
            self.root.after(0, self.stop_projection)
    
    def _project_single_pattern_nikon_trigger(self, pattern_index):
        """Project a single pattern in Nikon trigger mode"""
        try:
            img = self.images[pattern_index]
            filename = os.path.basename(img.filepath)
            
            # Update status display
            self.root.after(0, lambda: self.nikon_current_pattern.config(
                text=f"{pattern_index + 1}/{len(self.images)}: {filename}"
            ))
            
            # Update preview
            self.update_preview_during_projection(img, f"Pattern {pattern_index + 1}/{len(self.images)}")
            
            self.log_progress(f"  Projecting pattern {pattern_index + 1}/{len(self.images)}: {filename} ({img.mode})")
            
            if self.demo_mode:
                # Demo mode
                self.log_progress(f"  [DEMO] Would project {filename}")
                
                # Demo CoolLED control
                if img.led_enabled and self.coolled_connected:
                    enabled_channels = [ch for ch in ['A', 'B', 'C', 'D'] if img.led_channels[ch]['enabled']]
                    if enabled_channels:
                        for channel in enabled_channels:
                            wavelength = img.led_channels[channel]['wavelength']
                            intensity = img.led_channels[channel]['intensity']
                            self.log_progress(f"  [DEMO] LED: Ch{channel} {wavelength}nm @ {intensity}%")
                elif img.led_enabled:
                    self.log_progress(f"  ⚠ LED enabled but not connected")
            else:
                # Real hardware mode - stop current, switch LED, upload new pattern, start
                
                # CRITICAL: Stop DMD first to create dark period
                self.dlp.stopsequence()
                
                # Turn off ALL CoolLED channels first (clean slate)
                if self.coolled_connected:
                    try:
                        if not self.coolled_demo_mode:
                            self.coolled.all_off()
                        # Don't log "all off" to reduce clutter
                    except Exception as e:
                        self.log_progress(f"  Warning: Could not turn off LED: {e}")
                
                # Control CoolLED for this pattern
                if img.led_enabled and self.coolled_connected:
                    try:
                        enabled_channels = [ch for ch in ['A', 'B', 'C', 'D'] if img.led_channels[ch]['enabled']]
                        if enabled_channels:
                            for channel in enabled_channels:
                                wavelength = img.led_channels[channel]['wavelength']
                                intensity = img.led_channels[channel]['intensity']
                                
                                if not self.coolled_demo_mode:
                                    self.coolled.load_wavelength(wavelength)
                                    time.sleep(0.6)  # Wait for filter wheel rotation
                                    self.coolled.set_intensity(channel, intensity)
                                    time.sleep(0.05)  # Wait for channel activation
                                    self.log_progress(f"  LED: Ch{channel} {wavelength}nm @ {intensity}%")
                                else:
                                    self.log_progress(f"  [DEMO] LED: Ch{channel} {wavelength}nm @ {intensity}%")
                        else:
                            self.log_progress(f"  LED: Enabled but no channels selected")
                    except Exception as e:
                        self.log_progress(f"  Warning: LED control failed: {e}")
                elif img.led_enabled and not self.coolled_connected:
                    self.log_progress(f"  ⚠ Warning: LED enabled but not connected")
                
                # Load image if needed
                if img.image_array is None:
                    img.load_image()
                
                # Upload single pattern with infinite repeat (like constant mode)
                image_arrays = [img.image_array]
                exposures = [img.exposure]
                dark_times = [img.dark_time]
                rep = 0xFFFFFFFF  # Infinite repeat - pattern stays on screen
                
                if img.mode == '1bit':
                    self.dlp.defsequence(image_arrays, exposures, [False], dark_times, [1], rep,
                                       progress_callback=None)  # No progress for single image
                else:  # 8-bit mode
                    self.dlp.defsequence_8bit(image_arrays, exposures, [False], dark_times, [1], rep,
                                            progress_callback=None)
                
                # Start projection (LED already set, so transition is invisible)
                self.dlp.startsequence()
                self.log_progress(f"  ✓ Pattern started ({img.mode}, {img.exposure}μs)")
                
        except Exception as e:
            self.log_progress(f"  Error projecting pattern: {e}")
    
    def _project_black_frame_nikon_trigger(self):
        """Project a black frame in Nikon trigger mode"""
        try:
            # Update status display
            self.root.after(0, lambda: self.nikon_current_pattern.config(
                text="BLACK FRAME (initial)"
            ))
            
            self.log_progress("  Projecting BLACK FRAME (1920x1080 all zeros)")
            
            if self.demo_mode:
                # Demo mode
                self.log_progress(f"  [DEMO] Would project black frame")
            else:
                # Real hardware mode - project all-black pattern
                
                # Stop current sequence
                self.dlp.stopsequence()
                
                # Turn off ALL CoolLED channels
                if self.coolled_connected:
                    try:
                        if not self.coolled_demo_mode:
                            self.coolled.all_off()
                    except Exception as e:
                        self.log_progress(f"  Warning: Could not turn off LED: {e}")
                
                # Create black frame (1920x1080 all zeros)
                import numpy as np
                black_frame = np.zeros((1080, 1920), dtype=np.uint8)
                
                # Upload as 1-bit pattern (most efficient)
                image_arrays = [black_frame]
                exposures = [100000]  # 100ms exposure (doesn't matter, it's black)
                dark_times = [0]
                rep = 0xFFFFFFFF  # Infinite repeat
                
                self.dlp.defsequence(image_arrays, exposures, [False], dark_times, [1], rep,
                                   progress_callback=None)
                
                # Start projection
                self.dlp.startsequence()
                self.log_progress(f"  ✓ Black frame started")
                
        except Exception as e:
            self.log_progress(f"  Error projecting black frame: {e}")

def main():
    # Use ThemedTk with arc theme for modern appearance
    root = ThemedTk(theme="arc")
    app = DMDControllerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
