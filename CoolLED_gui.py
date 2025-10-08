"""
GUI Application for CoolLED pE-4000 LED Illumination Controller
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import serial.tools.list_ports
import time
import threading
import glob
import sys
import json
from datetime import datetime
import math

# Try to import ttkthemes, fall back to standard tkinter if not available
try:
    from ttkthemes import ThemedTk
    THEMED_AVAILABLE = True
except ImportError:
    THEMED_AVAILABLE = False
    print("ttkthemes not available, using standard tkinter theme")

# LED Wavelength Configuration
# Each channel (A-D) can use one of 4 specific wavelengths
# Total = 16 wavelengths across all channels
CHANNEL_WAVELENGTHS = {
    'A': {
        '365nm': {'wavelength': 365, 'color': '#8B00FF', 'name': '365nm UV'},
        '385nm': {'wavelength': 385, 'color': '#9370DB', 'name': '385nm UV'},
        '395nm': {'wavelength': 395, 'color': '#A070E0', 'name': '395nm UV'},
        '405nm': {'wavelength': 405, 'color': '#7B00E0', 'name': '405nm Violet'}
    },
    'B': {
        '425nm': {'wavelength': 425, 'color': '#5F00D0', 'name': '425nm Violet'},
        '445nm': {'wavelength': 445, 'color': '#4600FF', 'name': '445nm Blue'},
        '460nm': {'wavelength': 460, 'color': '#0050FF', 'name': '460nm Blue'},
        '470nm': {'wavelength': 470, 'color': '#0060FF', 'name': '470nm Blue'}
    },
    'C': {
        '500nm': {'wavelength': 500, 'color': '#00B0B0', 'name': '500nm Cyan'},
        '525nm': {'wavelength': 525, 'color': '#00FF00', 'name': '525nm Green'},
        '550nm': {'wavelength': 550, 'color': '#80FF00', 'name': '550nm Green'},
        '575nm': {'wavelength': 575, 'color': '#FFD000', 'name': '575nm Yellow'}
    },
    'D': {
        '635nm': {'wavelength': 635, 'color': '#FF0000', 'name': '635nm Red'},
        '660nm': {'wavelength': 660, 'color': '#C00000', 'name': '660nm Deep Red'},
        '740nm': {'wavelength': 740, 'color': '#800000', 'name': '740nm NIR'},
        '770nm': {'wavelength': 770, 'color': '#600000', 'name': '770nm NIR'}
    }
}

class CoolLEDController:
    """Serial communication handler for CoolLED pE-4000"""
    
    def __init__(self, port):
        self.port = port
        self.serial = None
        self.connected = False
        self.available_wavelengths = {}  # Discovered wavelengths per channel
        
    def connect(self):
        """Establish serial connection"""
        try:
            # Try both common baud rates
            for baud in [57600, 38400]:
                try:
                    self.serial = serial.Serial(self.port, baud, timeout=0.5)
                    time.sleep(0.1)  # Allow connection to stabilize
                    
                    # Verify connection
                    version = self.get_version()
                    if version:
                        self.connected = True
                        # Query available wavelengths
                        self.query_available_wavelengths()
                        return True, f"{version} @ {baud} baud"
                    self.serial.close()
                except:
                    if self.serial:
                        self.serial.close()
                    continue
            
            return False, "No response from device"
        except Exception as e:
            return False, str(e)
    
    def disconnect(self):
        """Close serial connection"""
        if self.serial:
            # Turn all channels off before disconnecting
            self.all_off()
            self.serial.close()
            self.serial = None
        self.connected = False
    
    def send_command(self, command):
        """Send command and return response"""
        if not self.serial or not self.connected:
            return None
        try:
            # Use \r terminator for pE-4000
            self.serial.write(f"{command}\r".encode('utf-8'))
            time.sleep(0.05)  # Small delay for device processing
            response = self.serial.readline().decode('utf-8').strip()
            return response
        except Exception as e:
            print(f"Command error: {e}")
            return None
    
    def get_version(self):
        """Query firmware version"""
        response = self.send_command("XVER")
        return response
    
    def query_available_wavelengths(self):
        """Query all available wavelengths"""
        response = self.send_command("LAMBDAS")
        # Parse response to determine available wavelengths
        # Store for later use
        return response
    
    def query_loaded_wavelengths(self):
        """Query currently loaded wavelengths"""
        response = self.send_command("LAMS")
        return response
    
    def load_wavelength(self, wavelength_nm):
        """Load a wavelength (automatically selects correct channel)"""
        response = self.send_command(f"LOAD:{wavelength_nm}")
        return response
    
    def set_intensity(self, channel, intensity):
        """Set channel intensity and turn ON (0-100%)"""
        # Format: CSSxSNnnn where x=channel, nnn=intensity (3 digits)
        intensity_str = f"{int(intensity):03d}"
        response = self.send_command(f"CSS{channel}SN{intensity_str}")
        return True  # Command doesn't return OK
    
    def turn_on(self, channel, intensity=None):
        """Turn channel ON (optionally set intensity)"""
        if intensity is not None:
            return self.set_intensity(channel, intensity)
        else:
            # Just turn on with current intensity
            response = self.send_command("CSN")
            return True
    
    def turn_off(self, channel):
        """Turn channel OFF"""
        response = self.send_command(f"CSS{channel}SF")
        return True
    
    def get_status(self):
        """Get full channel status"""
        response = self.send_command("CSS?")
        return response
    
    def all_off(self):
        """Turn all channels OFF"""
        response = self.send_command("CSF")
        return True
    
    def all_on(self):
        """Turn all channels ON to previous settings"""
        response = self.send_command("CSN")
        return True
    
    def disable_front_panel(self):
        """Disable front panel control pod (for automation)"""
        response = self.send_command("PORT:P=OFF")
        return True
    
    def enable_front_panel(self):
        """Re-enable front panel control pod"""
        response = self.send_command("PORT:P=ON")
        return True
    
    @staticmethod
    def find_devices():
        """Find connected CoolLED devices"""
        devices = []
        
        if sys.platform.startswith('win'):
            ports = [f'COM{i+1}' for i in range(20)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            ports = glob.glob('/dev/tty[A-Za-z]*')
        elif sys.platform.startswith('darwin'):
            ports = glob.glob('/dev/tty.*')
        else:
            return devices
        
        for port in ports:
            try:
                ser = serial.Serial(port, 38400, timeout=0.5)
                time.sleep(0.1)
                
                # Try reading initial response
                initial = ser.readline()
                if b'CoolLED' in initial:
                    devices.append(port)
                    ser.close()
                    continue
                
                # Try XVER command
                ser.write(b'XVER\n')
                time.sleep(0.1)
                response = ser.read(200)
                
                if b'XFW_VER' in response or b'XUNIT' in response:
                    devices.append(port)
                
                ser.close()
            except (OSError, serial.SerialException):
                pass
        
        return devices


class CoolLEDGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CoolLED pE-4000 Controller")
        self.root.geometry("1100x700")
        
        # Apply professional theme
        self.apply_theme()
        
        self.controller = None
        self.connected = False
        self.demo_mode = False
        
        # Channel states (for demo mode) and configuration
        self.channel_states = {
            'A': {'on': False, 'intensity': 50, 'wavelength': '365nm'},
            'B': {'on': False, 'intensity': 50, 'wavelength': '470nm'},
            'C': {'on': False, 'intensity': 50, 'wavelength': '525nm'},
            'D': {'on': False, 'intensity': 50, 'wavelength': '635nm'}
        }
        
        # Channel intensity variables
        self.intensity_vars = {}
        self.channel_status_labels = {}
        self.channel_on_buttons = {}
        self.channel_off_buttons = {}
        self.intensity_sliders = {}
        self.wavelength_combos = {}
        self.intensity_labels = {}
        
        # Sequence management
        self.sequence_steps = []
        self.sequence_running = False
        self.sequence_thread = None
        self.stop_sequence_flag = False
        
        self.create_ui()
        
        # Set up proper window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def apply_theme(self):
        """Apply styling tweaks"""
        style = ttk.Style()
        
        # Increase Treeview row height
        style.configure('Treeview', rowheight=25)
        
        # Make LabelFrame labels bold
        style.configure('TLabelframe.Label', font=('TkDefaultFont', 9, 'bold'))
        
        # Add padding to buttons
        style.configure('TButton', padding=6)
        
        # Custom styles for ON/OFF buttons
        style.configure('ON.TButton', foreground='green')
        style.configure('OFF.TButton', foreground='red')
    
    def create_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=0)  # Left panel fixed width
        main_frame.columnconfigure(1, weight=1)  # Right panel grows
        main_frame.rowconfigure(1, weight=0)  # Channel controls - fixed
        main_frame.rowconfigure(2, weight=1)  # Sequence panel - grows
        
        # Top: Connection Panel (spans both columns)
        conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="10")
        conn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.status_label = ttk.Label(conn_frame, text="● Disconnected", foreground="red", font=('TkDefaultFont', 10, 'bold'))
        self.status_label.grid(row=0, column=0, sticky=tk.W, padx=(0, 20))
        
        self.device_info_label = ttk.Label(conn_frame, text="", foreground="gray")
        self.device_info_label.grid(row=0, column=1, sticky=tk.W, padx=(0, 20))
        
        btn_frame = ttk.Frame(conn_frame)
        btn_frame.grid(row=0, column=2, sticky=tk.E)
        
        self.connect_btn = ttk.Button(btn_frame, text="Connect", command=self.connect_device)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.disconnect_btn = ttk.Button(btn_frame, text="Disconnect", command=self.disconnect_device, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT)
        
        # Left: Global Controls (minimal)
        left_frame = ttk.LabelFrame(main_frame, text="Global Controls", padding="10")
        left_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N), padx=(0, 10))
        
        ttk.Button(left_frame, text="All Channels ON", command=self.all_channels_on, width=18).pack(fill=tk.X, pady=5)
        ttk.Button(left_frame, text="All Channels OFF", command=self.all_channels_off, width=18).pack(fill=tk.X, pady=5)
        
        # Right: Channel Controls
        right_frame = ttk.LabelFrame(main_frame, text="Channel Controls", padding="10")
        right_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Create 4 channel control panels
        channels = ['A', 'B', 'C', 'D']
        
        for i, channel in enumerate(channels):
            self.create_channel_control(right_frame, channel, i)
        
        # Sequence Editor Panel (spans both columns)
        self.create_sequence_panel(main_frame)
        
        # Application ready
    
    def create_channel_control(self, parent, channel, row):
        """Create compact horizontal control panel for a single channel"""
        # Get initial color from wavelength
        wavelength_key = self.channel_states[channel]['wavelength']
        color = CHANNEL_WAVELENGTHS[channel][wavelength_key]['color']
        
        # Main frame with colored indicator
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=3, padx=5)
        parent.rowconfigure(row, weight=0)
        
        # Column 0: Channel label with color indicator
        label_frame = ttk.Frame(frame)
        label_frame.grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        
        channel_label = tk.Label(label_frame, text=f"Ch {channel}", 
                                font=('TkDefaultFont', 10, 'bold'),
                                fg=color, width=5, anchor=tk.W)
        channel_label.pack(side=tk.TOP)
        self.intensity_labels[channel] = channel_label
        
        status_label = ttk.Label(label_frame, text="OFF", foreground="gray", 
                                font=('TkDefaultFont', 8))
        status_label.pack(side=tk.TOP)
        self.channel_status_labels[channel] = status_label
        
        # Column 1: Wavelength selector (compact)
        available = list(CHANNEL_WAVELENGTHS[channel].keys())
        wavelength_var = tk.StringVar(value=wavelength_key)
        wavelength_combo = ttk.Combobox(frame, textvariable=wavelength_var, 
                                       values=available, 
                                       state='readonly', width=8)
        wavelength_combo.grid(row=0, column=1, sticky=tk.W, padx=5)
        wavelength_combo.bind('<<ComboboxSelected>>', lambda e, ch=channel: self.on_wavelength_change(ch))
        self.wavelength_combos[channel] = wavelength_combo
        
        # Column 2: Intensity slider (grows)
        self.intensity_vars[channel] = tk.IntVar(value=50)
        slider = ttk.Scale(frame, from_=0, to=100, orient=tk.HORIZONTAL,
                          variable=self.intensity_vars[channel],
                          command=lambda v, ch=channel: self.on_intensity_change(ch, v),
                          length=300)
        slider.grid(row=0, column=2, sticky=(tk.W, tk.E), padx=5)
        frame.columnconfigure(2, weight=1)
        self.intensity_sliders[channel] = slider
        
        # Column 3: Numerical input
        intensity_entry = ttk.Entry(frame, textvariable=self.intensity_vars[channel], 
                                   width=5, justify=tk.CENTER)
        intensity_entry.grid(row=0, column=3, sticky=tk.W, padx=5)
        intensity_entry.bind('<Return>', lambda e, ch=channel: self.on_intensity_entry(ch))
        intensity_entry.bind('<FocusOut>', lambda e, ch=channel: self.on_intensity_entry(ch))
        
        # Column 4: ON/OFF toggle buttons
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=0, column=4, sticky=tk.W, padx=(5, 0))
        
        on_btn = ttk.Button(button_frame, text="ON", width=5,
                           command=lambda: self.turn_channel_on(channel))
        on_btn.pack(side=tk.LEFT, padx=2)
        self.channel_on_buttons[channel] = on_btn
        
        off_btn = ttk.Button(button_frame, text="OFF", width=5,
                            command=lambda: self.turn_channel_off(channel))
        off_btn.pack(side=tk.LEFT, padx=2)
        self.channel_off_buttons[channel] = off_btn
        
        # Initially disable controls
        on_btn.config(state=tk.DISABLED)
        off_btn.config(state=tk.DISABLED)
        slider.config(state=tk.DISABLED)
        wavelength_combo.config(state=tk.DISABLED)
        intensity_entry.config(state=tk.DISABLED)
    
    def on_wavelength_change(self, channel):
        """Handle wavelength selection change"""
        selected = self.wavelength_combos[channel].get()
        self.channel_states[channel]['wavelength'] = selected
        
        # Update channel label color
        color = CHANNEL_WAVELENGTHS[channel][selected]['color']
        self.intensity_labels[channel].config(fg=color)
        
        # Load wavelength on hardware if connected
        if self.controller and self.connected and not self.demo_mode:
            wavelength_nm = CHANNEL_WAVELENGTHS[channel][selected]['wavelength']
            self.controller.load_wavelength(wavelength_nm)
            pass  # Wavelength loaded
        else:
            pass  # Demo mode - wavelength set
    
    def on_intensity_entry(self, channel):
        """Handle manual intensity entry - allows precise value setting"""
        try:
            value = int(self.intensity_vars[channel].get())
            # Clamp to valid range
            value = max(0, min(100, value))
            self.intensity_vars[channel].set(value)
            
            # Update hardware if channel is ON
            if self.controller and self.connected and not self.demo_mode:
                if self.channel_status_labels[channel].cget('text') == 'ON':
                    wavelength_key = self.channel_states[channel]['wavelength']
                    wavelength_nm = CHANNEL_WAVELENGTHS[channel][wavelength_key]['wavelength']
                    self.controller.load_wavelength(wavelength_nm)
                    self.controller.set_intensity(channel, value)
        except ValueError:
            # Ignore invalid input, keep current value
            pass
    
    def on_closing(self):
        """Handle window close event"""
        if self.connected and not self.demo_mode:
            try:
                self.disconnect_device()
            except:
                pass
        self.root.destroy()
    
    def connect_device(self):
        """Find and connect to CoolLED device"""
        # Search in a separate thread to prevent UI freezing
        def search_and_connect():
            devices = CoolLEDController.find_devices()
            
            self.root.after(0, lambda: self.complete_connection(devices))
        
        threading.Thread(target=search_and_connect, daemon=True).start()
    
    def complete_connection(self, devices):
        """Complete connection after device search"""
        if not devices:
            # Offer demo mode
            result = messagebox.askyesno(
                "Hardware Not Found",
                "Could not find CoolLED pE-4000 device.\n\n"
                "Would you like to enable Demo Mode?\n\n"
                "Demo Mode lets you test all GUI features without hardware."
            )
            
            if result:
                self.enable_demo_mode()
            return
        
        # Connect to first device found
        port = devices[0]
        self.controller = CoolLEDController(port)
        success, message = self.controller.connect()
        
        if success:
            self.connected = True
            self.status_label.config(text="● Connected", foreground="green")
            self.device_info_label.config(text=f"Port: {port} | {message}")
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
            self.enable_controls()
            # Query initial intensities
            self.refresh_all_intensities()
        else:
            pass  # Connection failed
            messagebox.showerror("Connection Error", f"Could not connect:\n{message}")
    
    def disconnect_device(self):
        """Disconnect from device"""
        if self.controller and self.connected:
            self.controller.disconnect()
        
        self.connected = False
        self.demo_mode = False
        self.controller = None
        
        self.status_label.config(text="● Disconnected", foreground="red")
        self.device_info_label.config(text="")
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.disable_controls()
        pass  # Disconnected
    
    def enable_demo_mode(self):
        """Enable demo mode for testing without hardware"""
        self.demo_mode = True
        self.connected = True
        
        self.status_label.config(text="● Demo Mode", foreground="orange")
        self.device_info_label.config(text="No hardware connected - Testing mode")
        self.connect_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.NORMAL)
        self.enable_controls()
        
        pass  # Demo mode enabled
        messagebox.showinfo(
            "Demo Mode Enabled",
            "Demo Mode is now active!\n\n"
            "You can test all GUI features:\n"
            "• Control all 4 channels\n"
            "• Adjust intensity settings\n"
            "• Test presets and global controls\n\n"
            "Note: No actual hardware control will occur."
        )
    
    def enable_controls(self):
        """Enable all channel controls"""
        for channel in ['A', 'B', 'C', 'D']:
            self.channel_on_buttons[channel].config(state=tk.NORMAL)
            self.channel_off_buttons[channel].config(state=tk.NORMAL)
            self.intensity_sliders[channel].config(state=tk.NORMAL)
            self.wavelength_combos[channel].config(state='readonly')
    
    def disable_controls(self):
        """Disable all channel controls"""
        for channel in ['A', 'B', 'C', 'D']:
            self.channel_on_buttons[channel].config(state=tk.DISABLED)
            self.channel_off_buttons[channel].config(state=tk.DISABLED)
            self.intensity_sliders[channel].config(state=tk.DISABLED)
            self.wavelength_combos[channel].config(state=tk.DISABLED)
            self.channel_status_labels[channel].config(text="OFF", foreground="gray")
    
    def turn_channel_on(self, channel):
        """Turn a channel ON"""
        if self.demo_mode:
            self.channel_states[channel]['on'] = True
            self.channel_status_labels[channel].config(text="ON", foreground="green")
            pass  # Channel turned on
        elif self.controller:
            # First load the wavelength
            wavelength_key = self.channel_states[channel]['wavelength']
            wavelength_nm = CHANNEL_WAVELENGTHS[channel][wavelength_key]['wavelength']
            self.controller.load_wavelength(wavelength_nm)
            
            # Then set intensity and turn on
            intensity = self.intensity_vars[channel].get()
            self.controller.set_intensity(channel, intensity)
            
            self.channel_status_labels[channel].config(text="ON", foreground="green")
            pass  # Channel turned on with hardware
    
    def turn_channel_off(self, channel):
        """Turn a channel OFF"""
        if self.demo_mode:
            self.channel_states[channel]['on'] = False
            self.channel_status_labels[channel].config(text="OFF", foreground="gray")
            pass  # Channel turned off
        elif self.controller:
            if self.controller.turn_off(channel):
                self.channel_status_labels[channel].config(text="OFF", foreground="gray")
                pass  # Channel turned off
            else:
                pass  # Failed to turn off
    
    def on_intensity_change(self, channel, value):
        """Handle intensity slider change"""
        intensity = int(float(value))
        
        if self.demo_mode:
            self.channel_states[channel]['intensity'] = intensity
        elif self.controller:
            # Only update if channel is currently ON
            if self.channel_status_labels[channel].cget('text') == 'ON':
                self.controller.set_intensity(channel, intensity)
    
    def all_channels_on(self):
        """Turn all channels ON"""
        if self.demo_mode:
            for channel in ['A', 'B', 'C', 'D']:
                self.channel_states[channel]['on'] = True
                self.channel_status_labels[channel].config(text="ON", foreground="green")
            pass  # All channels on
        elif self.controller:
            if self.controller.all_on():
                for channel in ['A', 'B', 'C', 'D']:
                    self.channel_states[channel]['on'] = True
                    self.channel_status_labels[channel].config(text="ON", foreground="green")
                pass  # All channels on
            else:
                for channel in ['A', 'B', 'C', 'D']:
                    self.channel_states[channel]['on'] = False
                    self.channel_status_labels[channel].config(text="OFF", foreground="gray")
                pass  # Failed to turn on all
    
    def all_channels_off(self):
        """Turn all channels OFF"""
        if self.demo_mode:
            for channel in ['A', 'B', 'C', 'D']:
                self.channel_states[channel]['on'] = False
                self.channel_status_labels[channel].config(text="OFF", foreground="gray")
            pass  # All channels off
        elif self.controller:
            if self.controller.all_off():
                for channel in ['A', 'B', 'C', 'D']:
                    self.channel_status_labels[channel].config(text="OFF", foreground="gray")
                pass  # All channels off
            else:
                pass  # Failed to turn off all
    
    def apply_preset(self, active_channel):
        """Apply preset: turn on only one channel, others off"""
        if self.demo_mode:
            for channel in ['A', 'B', 'C', 'D']:
                if channel == active_channel:
                    self.channel_states[channel]['on'] = True
                    self.channel_status_labels[channel].config(text="ON", foreground="green")
                else:
                    self.channel_states[channel]['on'] = False
                    self.channel_status_labels[channel].config(text="OFF", foreground="gray")
            pass  # Preset applied
        elif self.controller:
            # First turn all off
            self.controller.all_off()
            for channel in ['A', 'B', 'C', 'D']:
                self.channel_status_labels[channel].config(text="OFF", foreground="gray")
            
            # Then turn on the selected channel
            intensity = self.intensity_vars[active_channel].get()
            self.controller.set_intensity(active_channel, intensity)
            if self.controller.turn_on(active_channel):
                self.channel_status_labels[active_channel].config(text="ON", foreground="green")
                pass  # Preset applied with hardware
    
    def refresh_all_intensities(self):
        """Query and update all channel intensities from hardware"""
        if not self.controller or self.demo_mode:
            return
        for channel in ['A', 'B', 'C', 'D']:
            intensity = self.controller.get_intensity(channel)
            if intensity is not None:
                self.intensity_vars[channel].set(intensity)
    
    # ==================== SEQUENCE EDITOR METHODS ====================
    
    def create_sequence_panel(self, parent):
        """Create the sequence editor panel"""
        seq_frame = ttk.LabelFrame(parent, text="Sequence Editor", padding="10")
        seq_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        seq_frame.columnconfigure(0, weight=1)
        seq_frame.rowconfigure(1, weight=1)
        
        # Quick Add Controls
        add_frame = ttk.Frame(seq_frame)
        add_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Label(add_frame, text="Quick Add:", font=('TkDefaultFont', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 10))
        
        # Action type
        ttk.Label(add_frame, text="Action:").pack(side=tk.LEFT, padx=(0, 5))
        self.seq_action_var = tk.StringVar(value='channel')
        ttk.Radiobutton(add_frame, text="Channel", variable=self.seq_action_var, value='channel', command=self.update_quick_add_state).pack(side=tk.LEFT)
        ttk.Radiobutton(add_frame, text="Wait", variable=self.seq_action_var, value='wait', command=self.update_quick_add_state).pack(side=tk.LEFT, padx=(0, 15))
        
        # Channel selection
        ttk.Label(add_frame, text="Ch:").pack(side=tk.LEFT, padx=(0, 5))
        self.seq_channel_var = tk.StringVar(value='A')
        self.seq_channel_combo = ttk.Combobox(add_frame, textvariable=self.seq_channel_var, values=['A', 'B', 'C', 'D'], state='readonly', width=3)
        self.seq_channel_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.seq_channel_combo.bind('<<ComboboxSelected>>', self.update_wavelength_options)
        
        # Wavelength selection
        ttk.Label(add_frame, text="λ:").pack(side=tk.LEFT, padx=(0, 5))
        self.seq_wavelength_var = tk.StringVar(value='365nm')
        self.seq_wavelength_combo = ttk.Combobox(add_frame, textvariable=self.seq_wavelength_var, values=list(CHANNEL_WAVELENGTHS['A'].keys()), state='readonly', width=8)
        self.seq_wavelength_combo.pack(side=tk.LEFT, padx=(0, 10))
        
        # Power
        ttk.Label(add_frame, text="Pwr:").pack(side=tk.LEFT, padx=(0, 5))
        self.seq_power_var = tk.StringVar(value='75')
        self.seq_power_entry = ttk.Entry(add_frame, textvariable=self.seq_power_var, width=5)
        self.seq_power_entry.pack(side=tk.LEFT, padx=(0, 2))
        ttk.Label(add_frame, text="%").pack(side=tk.LEFT, padx=(0, 10))
        
        # Duration
        ttk.Label(add_frame, text="Time:").pack(side=tk.LEFT, padx=(0, 5))
        self.seq_duration_var = tk.StringVar(value='1.0')
        ttk.Entry(add_frame, textvariable=self.seq_duration_var, width=6).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Label(add_frame, text="s").pack(side=tk.LEFT, padx=(0, 15))
        
        # Buttons
        ttk.Button(add_frame, text="+ Add Step", command=self.add_sequence_step).pack(side=tk.LEFT, padx=2)
        ttk.Button(add_frame, text="⚡ Generate Pattern", command=self.open_pattern_generator).pack(side=tk.LEFT, padx=2)
        ttk.Button(add_frame, text="Clear All", command=self.clear_sequence).pack(side=tk.LEFT, padx=2)
        
        # Sequence Table
        table_frame = ttk.Frame(seq_frame)
        table_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        
        columns = ('step', 'type', 'channel', 'wavelength', 'power', 'duration')
        self.sequence_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=8)
        self.sequence_tree.heading('step', text='#')
        self.sequence_tree.heading('type', text='Type')
        self.sequence_tree.heading('channel', text='Ch')
        self.sequence_tree.heading('wavelength', text='λ (nm)')
        self.sequence_tree.heading('power', text='Power (%)')
        self.sequence_tree.heading('duration', text='Time (s)')
        
        self.sequence_tree.column('step', width=40, anchor=tk.CENTER)
        self.sequence_tree.column('type', width=80)
        self.sequence_tree.column('channel', width=50, anchor=tk.CENTER)
        self.sequence_tree.column('wavelength', width=80, anchor=tk.CENTER)
        self.sequence_tree.column('power', width=80, anchor=tk.CENTER)
        self.sequence_tree.column('duration', width=80, anchor=tk.CENTER)
        
        self.sequence_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.sequence_tree.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.sequence_tree.configure(yscrollcommand=scrollbar.set)
        
        # Control Buttons
        control_frame = ttk.Frame(seq_frame)
        control_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
        # Left side - editing
        edit_frame = ttk.Frame(control_frame)
        edit_frame.pack(side=tk.LEFT)
        
        ttk.Button(edit_frame, text="▲ Move Up", command=self.move_step_up, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(edit_frame, text="▼ Move Down", command=self.move_step_down, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(edit_frame, text="🗑 Remove", command=self.remove_step, width=12).pack(side=tk.LEFT, padx=2)
        
        # Center - info
        info_frame = ttk.Frame(control_frame)
        info_frame.pack(side=tk.LEFT, padx=20)
        
        self.seq_total_label = ttk.Label(info_frame, text="Total: 0.0s", font=('TkDefaultFont', 9, 'bold'))
        self.seq_total_label.pack(side=tk.LEFT, padx=10)
        
        ttk.Label(info_frame, text="Repeat:").pack(side=tk.LEFT, padx=(10, 5))
        self.seq_repeat_var = tk.StringVar(value='1')
        ttk.Spinbox(info_frame, textvariable=self.seq_repeat_var, from_=1, to=999, width=5).pack(side=tk.LEFT)
        ttk.Label(info_frame, text="times").pack(side=tk.LEFT, padx=(5, 0))
        
        # Right side - execution
        exec_frame = ttk.Frame(control_frame)
        exec_frame.pack(side=tk.RIGHT)
        
        self.seq_run_btn = ttk.Button(exec_frame, text="▶ Run Sequence", command=self.run_sequence, width=15)
        self.seq_run_btn.pack(side=tk.LEFT, padx=2)
        
        self.seq_stop_btn = ttk.Button(exec_frame, text="⏹ Stop", command=self.stop_sequence, state=tk.DISABLED, width=10)
        self.seq_stop_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(exec_frame, text="💾 Save", command=self.save_sequence, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(exec_frame, text="📂 Load", command=self.load_sequence, width=10).pack(side=tk.LEFT, padx=2)
    
    def update_quick_add_state(self):
        """Enable/disable controls based on action type"""
        is_channel = self.seq_action_var.get() == 'channel'
        state = 'readonly' if is_channel else 'disabled'
        entry_state = tk.NORMAL if is_channel else tk.DISABLED
        
        self.seq_channel_combo.config(state=state)
        self.seq_wavelength_combo.config(state=state)
        self.seq_power_entry.config(state=entry_state)
    
    def update_wavelength_options(self, event=None):
        """Update wavelength options when channel changes"""
        channel = self.seq_channel_var.get()
        wavelengths = list(CHANNEL_WAVELENGTHS[channel].keys())
        self.seq_wavelength_combo.config(values=wavelengths)
        self.seq_wavelength_var.set(wavelengths[0])
    
    def add_sequence_step(self):
        """Add a step to the sequence"""
        try:
            action_type = self.seq_action_var.get()
            duration = float(self.seq_duration_var.get())
            
            if duration <= 0:
                messagebox.showerror("Invalid Duration", "Duration must be greater than 0")
                return
            
            step = {'duration': duration}
            
            if action_type == 'channel':
                channel = self.seq_channel_var.get()
                wavelength = self.seq_wavelength_var.get()
                power = int(self.seq_power_var.get())
                
                if power < 0 or power > 100:
                    messagebox.showerror("Invalid Power", "Power must be between 0 and 100")
                    return
                
                step.update({
                    'type': 'channel',
                    'channel': channel,
                    'wavelength': wavelength,
                    'power': power
                })
            else:
                step['type'] = 'wait'
            
            self.sequence_steps.append(step)
            self.refresh_sequence_table()
            
        except ValueError:
            messagebox.showerror("Invalid Input", "Please check your input values")
    
    def remove_step(self):
        """Remove selected step from sequence"""
        selection = self.sequence_tree.selection()
        if not selection:
            return
        
        idx = self.sequence_tree.index(selection[0])
        del self.sequence_steps[idx]
        self.refresh_sequence_table()
    
    def move_step_up(self):
        """Move selected step up"""
        selection = self.sequence_tree.selection()
        if not selection:
            return
        
        idx = self.sequence_tree.index(selection[0])
        if idx == 0:
            return
        
        self.sequence_steps[idx], self.sequence_steps[idx-1] = self.sequence_steps[idx-1], self.sequence_steps[idx]
        self.refresh_sequence_table()
        
        items = self.sequence_tree.get_children()
        self.sequence_tree.selection_set(items[idx-1])
        self.sequence_tree.focus(items[idx-1])
    
    def move_step_down(self):
        """Move selected step down"""
        selection = self.sequence_tree.selection()
        if not selection:
            return
        
        idx = self.sequence_tree.index(selection[0])
        if idx >= len(self.sequence_steps) - 1:
            return
        
        self.sequence_steps[idx], self.sequence_steps[idx+1] = self.sequence_steps[idx+1], self.sequence_steps[idx]
        self.refresh_sequence_table()
        
        items = self.sequence_tree.get_children()
        self.sequence_tree.selection_set(items[idx+1])
        self.sequence_tree.focus(items[idx+1])
    
    def clear_sequence(self):
        """Clear all sequence steps"""
        if self.sequence_steps and messagebox.askyesno("Confirm", "Clear entire sequence?"):
            self.sequence_steps.clear()
            self.refresh_sequence_table()
    
    def refresh_sequence_table(self):
        """Refresh the sequence table display"""
        # Clear existing items
        for item in self.sequence_tree.get_children():
            self.sequence_tree.delete(item)
        
        # Add all steps
        total_time = 0
        for i, step in enumerate(self.sequence_steps):
            if step['type'] == 'channel':
                values = (
                    i + 1,
                    'Channel',
                    step['channel'],
                    step['wavelength'],
                    step['power'],
                    f"{step['duration']:.1f}"
                )
            else:  # wait
                values = (
                    i + 1,
                    'Wait',
                    '-',
                    '-',
                    '-',
                    f"{step['duration']:.1f}"
                )
            
            self.sequence_tree.insert('', tk.END, values=values)
            total_time += step['duration']
        
        # Update total time display
        self.seq_total_label.config(text=f"Total: {total_time:.1f}s")
    
    def run_sequence(self):
        """Execute the sequence"""
        if not self.sequence_steps:
            messagebox.showwarning("No Sequence", "Please add steps to the sequence first")
            return
        
        if not self.connected:
            messagebox.showwarning("Not Connected", "Please connect to device or enable demo mode first")
            return
        
        if self.sequence_running:
            return
        
        self.sequence_running = True
        self.stop_sequence_flag = False
        self.seq_run_btn.config(state=tk.DISABLED)
        self.seq_stop_btn.config(state=tk.NORMAL)
        
        # Run in separate thread
        self.sequence_thread = threading.Thread(target=self._execute_sequence, daemon=True)
        self.sequence_thread.start()
    
    def _execute_sequence(self):
        """Execute sequence in background thread"""
        try:
            repeat_count = int(self.seq_repeat_var.get())
            
            for cycle in range(repeat_count):
                if self.stop_sequence_flag:
                    break
                
                for i, step in enumerate(self.sequence_steps):
                    if self.stop_sequence_flag:
                        break
                    
                    # Highlight current step
                    self.root.after(0, lambda idx=i: self.highlight_step(idx))
                    
                    if step['type'] == 'channel':
                        # Execute channel command
                        if self.controller and not self.demo_mode:
                            channel = step['channel']
                            wavelength = step['wavelength']
                            power = step['power']
                            
                            # Load wavelength
                            wavelength_nm = CHANNEL_WAVELENGTHS[channel][wavelength]['wavelength']
                            self.controller.load_wavelength(wavelength_nm)
                            
                            # Turn on with intensity
                            self.controller.set_intensity(channel, power)
                            
                            # Update UI
                            self.root.after(0, lambda ch=channel: self.channel_status_labels[ch].config(text="ON", foreground="green"))
                        
                        # Wait for duration
                        time.sleep(step['duration'])
                        
                        # Turn off
                        if self.controller and not self.demo_mode:
                            self.controller.turn_off(step['channel'])
                            self.root.after(0, lambda ch=step['channel']: self.channel_status_labels[ch].config(text="OFF", foreground="gray"))
                    
                    else:  # wait
                        time.sleep(step['duration'])
            
            # Turn all channels off at end
            if self.controller and not self.demo_mode:
                self.controller.all_off()
                for ch in ['A', 'B', 'C', 'D']:
                    self.root.after(0, lambda channel=ch: self.channel_status_labels[channel].config(text="OFF", foreground="gray"))
        
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Sequence Error", f"Error during sequence: {e}"))
        
        finally:
            self.root.after(0, self._sequence_complete)
    
    def highlight_step(self, index):
        """Highlight current step in table"""
        # Clear previous selection
        for item in self.sequence_tree.selection():
            self.sequence_tree.selection_remove(item)
        
        # Select current step
        if index < len(self.sequence_tree.get_children()):
            item = self.sequence_tree.get_children()[index]
            self.sequence_tree.selection_set(item)
            self.sequence_tree.see(item)
    
    def stop_sequence(self):
        """Stop running sequence"""
        self.stop_sequence_flag = True
    
    def _sequence_complete(self):
        """Cleanup after sequence completes"""
        self.sequence_running = False
        self.seq_run_btn.config(state=tk.NORMAL)
        self.seq_stop_btn.config(state=tk.DISABLED)
        
        # Clear selection
        for item in self.sequence_tree.selection():
            self.sequence_tree.selection_remove(item)
    
    def open_pattern_generator(self):
        """Open the pattern generator dialog"""
        PatternGeneratorDialog(self.root, self)
    
    def save_sequence(self):
        """Save sequence to JSON file"""
        if not self.sequence_steps:
            messagebox.showwarning("No Sequence", "No sequence to save")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".clseq",
            filetypes=[("CoolLED Sequence", "*.clseq"), ("JSON", "*.json"), ("All Files", "*.*")],
            title="Save Sequence"
        )
        
        if not filename:
            return
        
        try:
            sequence_data = {
                'name': filename.split('/')[-1].replace('.clseq', '').replace('.json', ''),
                'created': datetime.now().isoformat(),
                'repeat': int(self.seq_repeat_var.get()),
                'steps': self.sequence_steps
            }
            
            with open(filename, 'w') as f:
                json.dump(sequence_data, f, indent=2)
            
            messagebox.showinfo("Success", f"Sequence saved to {filename}")
        
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save sequence:\n{e}")
    
    def load_sequence(self):
        """Load sequence from JSON file"""
        filename = filedialog.askopenfilename(
            filetypes=[("CoolLED Sequence", "*.clseq"), ("JSON", "*.json"), ("All Files", "*.*")],
            title="Load Sequence"
        )
        
        if not filename:
            return
        
        try:
            with open(filename, 'r') as f:
                sequence_data = json.load(f)
            
            self.sequence_steps = sequence_data.get('steps', [])
            self.seq_repeat_var.set(str(sequence_data.get('repeat', 1)))
            
            self.refresh_sequence_table()
            messagebox.showinfo("Success", f"Sequence loaded from {filename}")
        
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load sequence:\n{e}")


class PatternGeneratorDialog:
    """Dialog for generating waveform patterns"""
    
    def __init__(self, parent, main_app):
        self.main_app = main_app
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Pattern Generator")
        self.dialog.geometry("700x600")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.create_ui()
        self.update_preview()
    
    def create_ui(self):
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Parameters Frame
        params_frame = ttk.LabelFrame(main_frame, text="Pattern Parameters", padding="10")
        params_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Row 0: Channel and Wavelength
        row = 0
        ttk.Label(params_frame, text="Channel:").grid(row=row, column=0, sticky=tk.W, pady=5, padx=(0, 5))
        self.channel_var = tk.StringVar(value='A')
        channel_combo = ttk.Combobox(params_frame, textvariable=self.channel_var, values=['A', 'B', 'C', 'D'], state='readonly', width=5)
        channel_combo.grid(row=row, column=1, sticky=tk.W, pady=5)
        channel_combo.bind('<<ComboboxSelected>>', self.on_channel_change)
        
        ttk.Label(params_frame, text="Wavelength:").grid(row=row, column=2, sticky=tk.W, pady=5, padx=(20, 5))
        self.wavelength_var = tk.StringVar(value='365nm')
        self.wavelength_combo = ttk.Combobox(params_frame, textvariable=self.wavelength_var, values=list(CHANNEL_WAVELENGTHS['A'].keys()), state='readonly', width=10)
        self.wavelength_combo.grid(row=row, column=3, sticky=tk.W, pady=5)
        self.wavelength_combo.bind('<<ComboboxSelected>>', lambda e: self.update_preview())
        
        # Row 1: Pattern Type
        row += 1
        ttk.Label(params_frame, text="Pattern Type:", font=('TkDefaultFont', 9, 'bold')).grid(row=row, column=0, columnspan=4, sticky=tk.W, pady=(10, 5))
        
        row += 1
        self.pattern_var = tk.StringVar(value='sine')
        patterns = [
            ('Sine Wave', 'sine'),
            ('Ramp Up', 'ramp_up'),
            ('Ramp Down', 'ramp_down'),
            ('Triangle', 'triangle'),
            ('Square Wave', 'square'),
            ('Step Function', 'step')
        ]
        
        for i, (label, value) in enumerate(patterns):
            ttk.Radiobutton(params_frame, text=label, variable=self.pattern_var, value=value, command=self.update_preview).grid(row=row, column=i%3, sticky=tk.W, padx=10, pady=2)
            if i == 2:
                row += 1
        
        # Row: Duration
        row += 1
        ttk.Label(params_frame, text="Duration:").grid(row=row, column=0, sticky=tk.W, pady=5, padx=(0, 5))
        self.duration_var = tk.StringVar(value='10.0')
        ttk.Entry(params_frame, textvariable=self.duration_var, width=10).grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(params_frame, text="seconds").grid(row=row, column=2, sticky=tk.W, pady=5, padx=(5, 0))
        self.duration_var.trace('w', lambda *args: self.update_preview())
        
        # Row: Min/Max Power
        row += 1
        ttk.Label(params_frame, text="Min Power:").grid(row=row, column=0, sticky=tk.W, pady=5, padx=(0, 5))
        self.min_power_var = tk.StringVar(value='20')
        ttk.Entry(params_frame, textvariable=self.min_power_var, width=10).grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(params_frame, text="%").grid(row=row, column=2, sticky=tk.W, pady=5, padx=(5, 0))
        self.min_power_var.trace('w', lambda *args: self.update_preview())
        
        ttk.Label(params_frame, text="Max Power:").grid(row=row, column=3, sticky=tk.W, pady=5, padx=(20, 5))
        self.max_power_var = tk.StringVar(value='80')
        ttk.Entry(params_frame, textvariable=self.max_power_var, width=10).grid(row=row, column=4, sticky=tk.W, pady=5)
        ttk.Label(params_frame, text="%").grid(row=row, column=5, sticky=tk.W, pady=5, padx=(5, 0))
        self.max_power_var.trace('w', lambda *args: self.update_preview())
        
        # Row: Frequency/Period
        row += 1
        ttk.Label(params_frame, text="Frequency:").grid(row=row, column=0, sticky=tk.W, pady=5, padx=(0, 5))
        self.frequency_var = tk.StringVar(value='0.5')
        ttk.Entry(params_frame, textvariable=self.frequency_var, width=10).grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(params_frame, text="Hz").grid(row=row, column=2, sticky=tk.W, pady=5, padx=(5, 0))
        self.frequency_var.trace('w', lambda *args: self.update_preview())
        
        ttk.Label(params_frame, text="Resolution:").grid(row=row, column=3, sticky=tk.W, pady=5, padx=(20, 5))
        self.resolution_var = tk.StringVar(value='0.1')
        ttk.Entry(params_frame, textvariable=self.resolution_var, width=10).grid(row=row, column=4, sticky=tk.W, pady=5)
        ttk.Label(params_frame, text="seconds/step").grid(row=row, column=5, sticky=tk.W, pady=5, padx=(5, 0))
        self.resolution_var.trace('w', lambda *args: self.update_preview())
        
        # Preview Frame
        preview_frame = ttk.LabelFrame(main_frame, text="Preview", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.canvas = tk.Canvas(preview_frame, bg='white', height=250)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Info Label
        self.info_label = ttk.Label(preview_frame, text="", foreground="blue", font=('TkDefaultFont', 9))
        self.info_label.pack(pady=(5, 0))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Insert into Sequence", command=self.insert_pattern).pack(side=tk.RIGHT, padx=2)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=2)
    
    def on_channel_change(self, event=None):
        """Update wavelength options when channel changes"""
        channel = self.channel_var.get()
        wavelengths = list(CHANNEL_WAVELENGTHS[channel].keys())
        self.wavelength_combo.config(values=wavelengths)
        self.wavelength_var.set(wavelengths[0])
        self.update_preview()
    
    def generate_waveform(self):
        """Generate waveform data points"""
        try:
            duration = float(self.duration_var.get())
            min_power = float(self.min_power_var.get())
            max_power = float(self.max_power_var.get())
            frequency = float(self.frequency_var.get())
            resolution = float(self.resolution_var.get())
            pattern = self.pattern_var.get()
            
            if duration <= 0 or resolution <= 0:
                return []
            
            points = []
            t = 0
            amplitude = (max_power - min_power) / 2
            offset = (max_power + min_power) / 2
            
            while t <= duration:
                if pattern == 'sine':
                    power = offset + amplitude * math.sin(2 * math.pi * frequency * t)
                
                elif pattern == 'ramp_up':
                    # Linear ramp from min to max
                    power = min_power + (max_power - min_power) * (t / duration)
                
                elif pattern == 'ramp_down':
                    # Linear ramp from max to min
                    power = max_power - (max_power - min_power) * (t / duration)
                
                elif pattern == 'triangle':
                    # Triangle wave
                    period = 1.0 / frequency if frequency > 0 else duration
                    phase = (t % period) / period
                    if phase < 0.5:
                        power = min_power + (max_power - min_power) * (phase * 2)
                    else:
                        power = max_power - (max_power - min_power) * ((phase - 0.5) * 2)
                
                elif pattern == 'square':
                    # Square wave
                    period = 1.0 / frequency if frequency > 0 else duration
                    phase = (t % period) / period
                    power = max_power if phase < 0.5 else min_power
                
                elif pattern == 'step':
                    # Step function (3 levels)
                    third = duration / 3
                    if t < third:
                        power = min_power
                    elif t < 2 * third:
                        power = offset
                    else:
                        power = max_power
                
                points.append((t, max(0, min(100, power))))
                t += resolution
            
            return points
        
        except ValueError:
            return []
    
    def update_preview(self):
        """Update the waveform preview"""
        points = self.generate_waveform()
        
        if not points:
            self.info_label.config(text="Invalid parameters")
            return
        
        # Clear canvas
        self.canvas.delete('all')
        
        # Get canvas dimensions
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if width < 100:  # Canvas not yet sized
            width = 600
            height = 250
        
        # Margins
        margin_left = 50
        margin_right = 20
        margin_top = 20
        margin_bottom = 40
        
        plot_width = width - margin_left - margin_right
        plot_height = height - margin_top - margin_bottom
        
        # Draw axes
        self.canvas.create_line(margin_left, height - margin_bottom, 
                               width - margin_right, height - margin_bottom, width=2)  # X-axis
        self.canvas.create_line(margin_left, margin_top, 
                               margin_left, height - margin_bottom, width=2)  # Y-axis
        
        # Draw grid
        for i in range(5):
            y = margin_top + (plot_height / 4) * i
            self.canvas.create_line(margin_left, y, width - margin_right, y, fill='lightgray', dash=(2, 4))
            power_label = 100 - (i * 25)
            self.canvas.create_text(margin_left - 10, y, text=f"{power_label}%", anchor=tk.E, font=('TkDefaultFont', 8))
        
        # Plot waveform
        if len(points) > 1:
            max_time = points[-1][0]
            
            # Scale points to canvas
            scaled_points = []
            for t, power in points:
                x = margin_left + (t / max_time) * plot_width
                y = height - margin_bottom - (power / 100) * plot_height
                scaled_points.append((x, y))
            
            # Draw line
            for i in range(len(scaled_points) - 1):
                self.canvas.create_line(scaled_points[i][0], scaled_points[i][1],
                                       scaled_points[i+1][0], scaled_points[i+1][1],
                                       fill='blue', width=2)
            
            # Time labels
            for i in range(6):
                t = (max_time / 5) * i
                x = margin_left + (i / 5) * plot_width
                self.canvas.create_text(x, height - margin_bottom + 15, 
                                       text=f"{t:.1f}s", font=('TkDefaultFont', 8))
        
        # Update info
        step_count = len(points)
        try:
            duration = float(self.duration_var.get())
            self.info_label.config(text=f"Steps to generate: {step_count} | Total duration: {duration:.1f}s")
        except:
            self.info_label.config(text=f"Steps to generate: {step_count}")
    
    def insert_pattern(self):
        """Insert generated pattern into sequence"""
        points = self.generate_waveform()
        
        if not points:
            messagebox.showerror("Invalid Parameters", "Please check your input values")
            return
        
        try:
            channel = self.channel_var.get()
            wavelength = self.wavelength_var.get()
            resolution = float(self.resolution_var.get())
            
            # Convert points to sequence steps
            generated_steps = []
            for t, power in points:
                step = {
                    'type': 'channel',
                    'channel': channel,
                    'wavelength': wavelength,
                    'power': int(power),
                    'duration': resolution
                }
                generated_steps.append(step)
            
            # Add to main app's sequence
            self.main_app.sequence_steps.extend(generated_steps)
            self.main_app.refresh_sequence_table()
            
            messagebox.showinfo("Success", f"Added {len(generated_steps)} steps to sequence")
            self.dialog.destroy()
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to insert pattern:\n{e}")


def main():
    if THEMED_AVAILABLE:
        root = ThemedTk(theme="arc")
    else:
        root = tk.Tk()
    
    app = CoolLEDGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
