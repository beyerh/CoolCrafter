#!/usr/bin/env python3
"""
CoolCrafter Launcher
Simple application selector for CoolCrafter suite
"""
import tkinter as tk
from tkinter import ttk
from ttkthemes import ThemedTk
import subprocess
import sys
import os

class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CoolCrafter Launcher")
        self.root.geometry("500x500")
        self.root.resizable(False, False)
        
        # Center window on screen
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        
        self.create_ui()
    
    def create_ui(self):
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="25")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header frame
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(pady=(0, 15))
        
        # Title
        title_label = ttk.Label(
            header_frame,
            text="CoolCrafter",
            font=('TkDefaultFont', 22, 'bold')
        )
        title_label.pack(pady=(0, 8))
        
        subtitle_label = ttk.Label(
            header_frame,
            text="Synchronized DMD & LED Control",
            font=('TkDefaultFont', 10)
        )
        subtitle_label.pack(pady=(0, 5))
        
        # Separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(15, 20))
        
        # Instructions
        instruction_label = ttk.Label(
            main_frame,
            text="Select an application to launch:",
            font=('TkDefaultFont', 11, 'bold')
        )
        instruction_label.pack(pady=(0, 18))
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.BOTH, expand=True)
        
        # Application buttons
        apps = [
            {
                'name': 'CoolCrafter',
                'desc': 'Synchronized DMD + LED Control',
                'file': 'CoolCrafter_gui.py',
                'color': '#2196F3'
            },
            {
                'name': 'CoolLED',
                'desc': 'LED Standalone Control',
                'file': 'CoolLED_gui.py',
                'color': '#FF9800'
            },
            {
                'name': 'GitHub Repository',
                'desc': 'View source code and documentation',
                'url': 'https://github.com/beyerh/CoolCrafter',
                'color': '#6e5494'  # GitHub purple
            }
        ]
        
        for app in apps:
            self.create_app_button(button_frame, app)
    
    def create_app_button(self, parent, app):
        """Create a styled button for an application"""
        # Create a clickable frame that looks like a button
        button_frame = ttk.Frame(parent, relief='raised', borderwidth=1)
        button_frame.pack(fill=tk.X, pady=7, padx=5)
        
        # Inner frame for padding
        inner_frame = ttk.Frame(button_frame)
        inner_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=15)
        
        # App name label (centered)
        name_label = ttk.Label(
            inner_frame,
            text=app['name'],
            font=('TkDefaultFont', 11, 'bold'),
            anchor='center'
        )
        name_label.pack()
        
        # Description label (centered)
        desc_label = ttk.Label(
            inner_frame,
            text=app['desc'],
            font=('TkDefaultFont', 9),
            foreground='#666666',
            anchor='center'
        )
        desc_label.pack(pady=(3, 0))
        
        # Make the entire frame clickable
        for widget in [button_frame, inner_frame, name_label, desc_label]:
            widget.bind('<Button-1>', lambda e, a=app: self.launch_app(a))
            widget.bind('<Enter>', lambda e, f=button_frame: f.configure(relief='sunken'))
            widget.bind('<Leave>', lambda e, f=button_frame: f.configure(relief='raised'))
            widget.configure(cursor='hand2')
    
    def launch_app(self, app):
        """Launch the selected application or open URL and close launcher"""
        try:
            if 'url' in app:
                # Open URL in default web browser
                import webbrowser
                webbrowser.open(app['url'])
            else:
                # Get the directory where launcher.py is located
                script_dir = os.path.dirname(os.path.abspath(__file__))
                app_path = os.path.join(script_dir, app['file'])
                
                # Launch the application
                if sys.platform == 'win32':
                    # Windows: use pythonw to avoid console window
                    subprocess.Popen([sys.executable, app_path])
                else:
                    # Unix-like: standard python
                    subprocess.Popen([sys.executable, app_path])
            
            # Close launcher after successful launch
            self.root.quit()
            self.root.destroy()
            
        except Exception as e:
            # Show error message
            error_window = tk.Toplevel(self.root)
            error_window.title("Launch Error")
            error_window.geometry("400x150")
            
            ttk.Label(
                error_window,
                text=f"Failed to launch {app_file}",
                font=('TkDefaultFont', 10, 'bold')
            ).pack(pady=(20, 10))
            
            ttk.Label(
                error_window,
                text=str(e),
                wraplength=350
            ).pack(pady=(0, 20))
            
            ttk.Button(
                error_window,
                text="OK",
                command=error_window.destroy
            ).pack()

def main():
    root = ThemedTk(theme="arc")
    app = LauncherApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
