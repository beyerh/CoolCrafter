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
VERSION = "0.1"
APP_NAME = "CoolCrafter"
GITHUB_URL = "https://github.com/beyerh/CoolCrafter"

class DMDControllerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{VERSION} - DMD Controller")
        self.root.geometry("1400x850")  # Optimized height
        
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
        self.create_ui()
    
    def create_menu(self):
        """Create menu bar with File and Help menus"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Exit", command=self.on_closing)
        
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
        ttk.Radiobutton(mode_frame, text="Sequence (1-bit, up to 24 images)", variable=self.projection_mode, value='sequence', command=self.on_projection_mode_change).pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="Constant (selected image only)", variable=self.projection_mode, value='constant', command=self.on_projection_mode_change).pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="Pulsed Projection", variable=self.projection_mode, value='pulsed', command=self.on_projection_mode_change).pack(anchor=tk.W)
        
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
        
        settings_right = ttk.Frame(preview_frame)
        settings_right.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        settings_inner = ttk.LabelFrame(settings_right, text="Selected Image Settings", padding="10")
        settings_inner.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(settings_inner, text="Bit Mode:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.img_mode_var = tk.StringVar()
        mode_combo = ttk.Combobox(settings_inner, textvariable=self.img_mode_var, values=['1bit', '8bit'], state='readonly', width=15)
        mode_combo.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(5, 0))
        mode_combo.bind('<<ComboboxSelected>>', self.on_image_setting_change)
        
        ttk.Label(settings_inner, text="Exposure (μs):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.img_exposure_var = tk.StringVar()
        ttk.Entry(settings_inner, textvariable=self.img_exposure_var, width=18).grid(row=1, column=1, sticky=tk.W, pady=5, padx=(5, 0))
        self.img_exposure_var.trace('w', lambda *args: self.on_image_setting_change())
        
        ttk.Label(settings_inner, text="Dark Time (μs):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.img_dark_time_var = tk.StringVar()
        ttk.Entry(settings_inner, textvariable=self.img_dark_time_var, width=18).grid(row=2, column=1, sticky=tk.W, pady=5, padx=(5, 0))
        self.img_dark_time_var.trace('w', lambda *args: self.on_image_setting_change())
        
        ttk.Label(settings_inner, text="Duration:").grid(row=3, column=0, sticky=tk.W, pady=5)
        duration_frame = ttk.Frame(settings_inner)
        duration_frame.grid(row=3, column=1, sticky=tk.W, pady=5, padx=(5, 0))
        self.img_duration_var = tk.StringVar(value="60")
        self.img_duration_entry = ttk.Entry(duration_frame, textvariable=self.img_duration_var, width=10)
        self.img_duration_entry.pack(side=tk.LEFT, padx=(0, 2))
        self.img_duration_unit_var = tk.StringVar(value="sec")
        self.img_duration_unit_combo = ttk.Combobox(duration_frame, textvariable=self.img_duration_unit_var, values=['sec', 'min', 'hrs'], state='readonly', width=5)
        self.img_duration_unit_combo.pack(side=tk.LEFT)
        self.img_duration_var.trace('w', lambda *args: self.on_image_setting_change())
        self.img_duration_unit_var.trace('w', lambda *args: self.on_image_setting_change())
        ttk.Label(settings_inner, text="(For pulsed mode only)", font=('TkDefaultFont', 8), foreground='gray').grid(row=4, column=0, columnspan=2, sticky=tk.W)
        
        # CoolLED Illumination Settings
        ttk.Separator(settings_inner, orient=tk.HORIZONTAL).grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        ttk.Label(settings_inner, text="LED Illumination:", font=('TkDefaultFont', 9, 'bold')).grid(row=6, column=0, columnspan=2, sticky=tk.W)
        
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
        info_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.info_text = tk.Text(info_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
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
            self.status_label.config(text="● Connected (Hardware)", foreground="green")
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
            self.start_btn.config(state=tk.NORMAL)
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
        self.status_label.config(text="● Disconnected", foreground="red")
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.start_btn.config(state=tk.DISABLED)
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
        self.start_btn.config(state=tk.NORMAL)
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
        
        # Update duration field state based on mode
        self.update_duration_field_state()
        
        # Update LED hint label
        self.update_led_hint_label()
        
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
    
    def clear_all_images(self):
        if not self.images or not messagebox.askyesno("Confirm", "Clear all?"): return
        self.images.clear()
        for item in self.image_tree.get_children(): self.image_tree.delete(item)
        self.selected_image_index = None
        self.clear_preview()
        self.update_sequence_info()
    
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
    
    def on_image_setting_change(self, event=None):
        # Don't save changes if we're currently loading an image's values into the GUI
        if getattr(self, '_loading_image', False):
            return
        if self.selected_image_index is None: return
        img = self.images[self.selected_image_index]
        
        # Flag to track if we should recalculate
        should_recalculate = False
        
        try:
            # Check for empty fields first
            if not self.img_exposure_var.get() or not self.img_dark_time_var.get() or not self.img_duration_var.get():
                return  # Don't process if any field is empty
            
            img.mode = self.img_mode_var.get()
            img.exposure = int(self.img_exposure_var.get())
            img.dark_time = int(self.img_dark_time_var.get())
            # Convert duration to seconds based on selected unit
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
            
            # Fix numpy array boolean check
            if img.image_array is not None:
                img.load_image()
            self.refresh_image_list()
            should_recalculate = True
        except ValueError:
            return  # Don't recalculate if there was an error
        
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
        """Validate that exposure times are within hardware limits"""
        warnings = []
        errors = []
        
        for img in images_to_check:
            if img.exposure > MAX_SAFE_EXPOSURE_US:
                errors.append(f"{os.path.basename(img.filepath)}: {img.exposure}μs (>{MAX_SAFE_EXPOSURE_US/1000000}s limit)")
            elif img.exposure > MAX_RECOMMENDED_EXPOSURE_US:
                warnings.append(f"{os.path.basename(img.filepath)}: {img.exposure}μs (>{MAX_RECOMMENDED_EXPOSURE_US/1000000}s recommended)")
        
        if errors:
            msg = "❌ Exposure times EXCEED hardware limit!\n\n"
            msg += "Projections will terminate early (~3 seconds actual).\n\n"
            msg += "Images with invalid exposures:\n"
            for err in errors:
                msg += f"• {err}\n"
            msg += f"\n💡 Solution: Keep exposures ≤ {MAX_SAFE_EXPOSURE_US/1000000}s"
            msg += "\nFor longer projections, duplicate the image or use more cycles."
            messagebox.showerror("Exposure Time Error", msg)
            return False
        
        if warnings:
            msg = f"⚠️ Some exposures exceed {MAX_RECOMMENDED_EXPOSURE_US/1000000}s (confirmed safe limit):\n\n"
            for warn in warnings:
                msg += f"• {warn}\n"
            msg += f"\nThey may work up to {MAX_SAFE_EXPOSURE_US/1000000}s, but test your hardware.\n"
            msg += "For guaranteed reliability, keep exposures ≤ 3s.\n\n"
            msg += "Continue anyway?"
            if not messagebox.askyesno("Exposure Time Warning", msg):
                return False
        
        return True
    
    def start_projection(self):
        if not self.connected:
            messagebox.showerror("Error", "Not connected")
            return
        if not self.images:
            messagebox.showerror("Error", "No images")
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
        
        self.stop_projection_flag = False
        self.projecting = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
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
            self.projection_thread = threading.Thread(target=self.run_sequence, daemon=True)
        elif mode == 'constant':
            self.projection_thread = threading.Thread(target=self.run_constant, daemon=True)
        elif mode == 'pulsed':
            self.projection_thread = threading.Thread(target=self.run_pulsed, daemon=True)
        
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
        
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.proj_status_label.config(text="Stopped")
        self.log_progress("Stopped" if not self.demo_mode else "[DEMO] Stopped simulation")
    
    def run_sequence(self):
        """Sequence mode: Projects all 1-bit images in sequence"""
        try:
            self.log_progress("Starting sequence projection..." if not self.demo_mode else "[DEMO] Starting sequence projection simulation...")
            bit1 = [i for i in self.images if i.mode=='1bit']
            # DLPC900 repeat count = TOTAL pattern displays, not sequence loops
            # User enters "cycles", we need to multiply by number of images
            rep_input = int(self.seq_repeat_count_var.get()) if self.seq_repeat_count_var.get().isdigit() else 0
            if rep_input == 0:
                rep = 0xFFFFFFFF  # Infinite
            else:
                # For K cycles of N images: repeat = K * N total displays
                rep = rep_input * len([i for i in self.images if i.mode=='1bit'])
            
            if not bit1:
                self.log_progress("Error: No 1-bit images found for sequence mode. Set Mode to 1-bit.")
                self.root.after(0, self.stop_projection)
                return
            
            # Ensure all images are loaded
            for img in bit1:
                if img.image_array is None:
                    img.load_image()
            
            # Validate exposure times before starting
            if not self.demo_mode and not self.validate_exposure_times(bit1):
                self.root.after(0, self.stop_projection)
                return
            
            # Check and activate LED using first image's settings
            first_img = bit1[0]
            if first_img.led_enabled and self.coolled_connected:
                try:
                    enabled_channels = [ch for ch in ['A', 'B', 'C', 'D'] if first_img.led_channels[ch]['enabled']]
                    if enabled_channels:
                        for channel in enabled_channels:
                            wavelength = first_img.led_channels[channel]['wavelength']
                            intensity = first_img.led_channels[channel]['intensity']
                            
                            if not self.coolled_demo_mode:
                                self.coolled.load_wavelength(wavelength)
                                self.coolled.set_intensity(channel, intensity)
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
                self.log_progress(f"[DEMO] Would project {len(bit1)} 1-bit image(s) in sequence:")
                for idx, img in enumerate(bit1, 1):
                    self.log_progress(f"[DEMO]   {idx}. {os.path.basename(img.filepath)} (Exposure: {img.exposure}μs, Dark: {img.dark_time}μs)")
                self.log_progress(f"[DEMO] Cycles: {'infinite' if rep == 0xFFFFFFFF else f'{rep_input} ({rep} total displays)'}")
                if rep == 0xFFFFFFFF:
                    self.log_progress("[DEMO] Sequence would cycle continuously until stopped...")
                else:
                    self.log_progress(f"[DEMO] Sequence would run for {rep} displays then stop automatically")
            else:
                # Real hardware mode
                self.log_progress(f"Projecting sequence of {len(bit1)} 1-bit image(s):")
                for idx, img in enumerate(bit1, 1):
                    self.log_progress(f"  {idx}. {os.path.basename(img.filepath)} (Exposure: {img.exposure}μs, Dark: {img.dark_time}μs)")
                self.log_progress(f"Cycles: {'infinite' if rep == 0xFFFFFFFF else f'{rep_input} ({rep} total displays)'}")
                self.dlp.defsequence([i.image_array for i in bit1], [i.exposure for i in bit1], [False]*len(bit1), [i.dark_time for i in bit1], [1]*len(bit1), rep)
                self.dlp.startsequence()
                self.log_progress("Sequence projection started")
            
            # Cycle through images in preview to visualize sequence
            idx = 0
            total_displays = rep if rep != 0xFFFFFFFF else None  # None means infinite
            
            while self.projecting and not self.stop_projection_flag:
                # Check if we've reached the target number of displays (for finite sequences)
                if total_displays is not None and idx >= total_displays:
                    self.log_progress("Sequence completed!")
                    self.root.after(0, self.stop_projection)
                    break
                
                img = bit1[idx % len(bit1)]
                if total_displays is not None:
                    # Show progress for finite sequences
                    self.update_preview_during_projection(img, f"Frame {idx % len(bit1) + 1}/{len(bit1)} | Display {idx+1}/{total_displays}")
                else:
                    # Show frame info for infinite sequences
                    self.update_preview_during_projection(img, f"Frame {idx % len(bit1) + 1}/{len(bit1)}")
                
                # Calculate time to display based on exposure + dark time (in seconds)
                display_time = (img.exposure + img.dark_time) / 1000000.0  # Convert μs to seconds
                time.sleep(display_time)
                idx += 1
                
        except Exception as e:
            self.log_progress(f"Error: {e}")
            self.root.after(0, self.stop_projection)
    
    def run_constant(self):
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
                                self.coolled.set_intensity(channel, intensity)
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
                self.log_progress(f"Projecting selected image: {filename}")
                self.log_progress(f"Mode: {img.mode}, Exposure: {img.exposure}μs, Dark Time: {img.dark_time}μs")
                self.log_progress(f"Duration: {total_time:.1f}s" if total_time else "Duration: Infinite (until stopped)")
                
                # Use 0xFFFFFFFF for infinite projection (DLPC900 standard)
                rep = 0xFFFFFFFF
                
                if img.mode == '1bit':
                    # Project single 1-bit image
                    self.dlp.defsequence([img.image_array], [img.exposure], [False], [img.dark_time], [1], rep)
                    self.dlp.startsequence()
                    self.log_progress("Constant projection started (1-bit)")
                else:
                    # Project single 8-bit image
                    self.dlp.defsequence_8bit([img.image_array], [img.exposure], [False], [img.dark_time], [1], rep)
                    self.dlp.startsequence()
                    self.log_progress("Constant projection started (8-bit)")
                
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
            self.log_progress(f"Total cycles: {cycles}, Cycle duration: {cycle_dur}s")
            
            # Check if any images have LED enabled
            led_images = [img for img in self.images if img.led_enabled]
            if led_images:
                if self.coolled_connected:
                    self.log_progress(f"CoolLED control enabled for {len(led_images)} image(s)" + (" [DEMO]" if self.coolled_demo_mode else ""))
                else:
                    self.log_progress("⚠ Warning: Some images have LED enabled but CoolLED not connected")
            
            start_time = time.time()
            
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
                    
                    # Turn off ALL CoolLED channels first (before switching to new image)
                    if self.coolled_connected and not self.coolled_demo_mode:
                        self.coolled.all_off()
                    
                    # Control CoolLED if enabled for this image
                    if img.led_enabled and self.coolled_connected:
                        enabled_channels = [ch for ch in ['A', 'B', 'C', 'D'] if img.led_channels[ch]['enabled']]
                        if enabled_channels:
                            for channel in enabled_channels:
                                wavelength = img.led_channels[channel]['wavelength']
                                intensity = img.led_channels[channel]['intensity']
                                if not self.coolled_demo_mode:
                                    # Real CoolLED hardware
                                    self.coolled.load_wavelength(wavelength)
                                    self.coolled.set_intensity(channel, intensity)
                                    self.log_progress(f"  LED: Ch{channel} {wavelength}nm @ {intensity}% - ON")
                                else:
                                    # CoolLED demo mode
                                    self.log_progress(f"  [DEMO] LED: Ch{channel} {wavelength}nm @ {intensity}% - ON")
                    elif img.led_enabled and not self.coolled_connected:
                        self.log_progress(f"  ⚠ LED enabled but not connected")
                    
                    if self.demo_mode:
                        # Demo mode: simulate projection with full duration
                        self.log_progress(f"[DEMO] Projecting {filename} ({img.mode}) for {img.duration}s...")
                        time.sleep(img.duration)  # Use full duration in demo mode
                    else:
                        # Real hardware mode
                        self.log_progress(f"Projecting {filename} ({img.mode}) for {img.duration}s...")
                        
                        # Setup DMD sequence
                        if img.mode == '1bit':
                            self.dlp.defsequence([img.image_array], [img.exposure], [False], [img.dark_time], [1], 0)
                        else:
                            self.dlp.defsequence_8bit([img.image_array], [img.exposure], [False], [img.dark_time], [1], 0)
                        self.dlp.startsequence()
                        
                        # Sleep for the projection duration
                        time.sleep(img.duration)
                        self.dlp.stopsequence()
                    
                    # Note: LEDs will be turned off at the start of the next image loop
                    # or at the end of all cycles (see below)
                
                # Progress update
                if c % 5 == 0 or c == cycles:  # Update every 5 cycles or at end
                    elapsed = time.time() - start_time
                    remaining = (cycles - c) * cycle_dur
                    self.log_progress(f"Progress: {c}/{cycles} cycles ({c/cycles*100:.1f}%) | Elapsed: {elapsed/60:.1f}min | Remaining: ~{remaining/60:.1f}min")
            
            # Ensure all LEDs are off at the end
            if self.coolled_connected:
                if not self.coolled_demo_mode:
                    self.coolled.all_off()
                    self.log_progress("LED: All channels OFF")
                else:
                    self.log_progress("[DEMO] LED: All channels OFF")
            
            self.log_progress("Pulsed projection completed!" if not self.demo_mode else "[DEMO] Pulsed projection simulation completed!")
            self.root.after(0, self.stop_projection)
            
        except Exception as e:
            self.log_progress(f"Error: {e}")
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

def main():
    # Use ThemedTk with arc theme for modern appearance
    root = ThemedTk(theme="arc")
    app = DMDControllerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
