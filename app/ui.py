import logging
import threading
import customtkinter as ctk
from tkinter import Scrollbar, END
from app.config_manager import config
from app.main import VideoPipeline

# Configure CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class TextHandler(logging.Handler):
    """Logging handler that writes to a Tkiner textbox"""
    def __init__(self, textbox):
        super().__init__()
        self.textbox = textbox

    def emit(self, record):
        msg = self.format(record)
        def append():
            self.textbox.configure(state="normal")
            self.textbox.insert(END, msg + "\n")
            self.textbox.configure(state="disabled")
            self.textbox.see(END)
        self.textbox.after(0, append)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Auto Video Creator")
        self.geometry("900x600")

        # Grid config
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(4, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar, text="Auto Video\nCreator", font=("Roboto", 20, "bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.start_btn = ctk.CTkButton(self.sidebar, text="Start Generation", command=self.start_pipeline)
        self.start_btn.grid(row=1, column=0, padx=20, pady=10)

        self.settings_btn = ctk.CTkButton(self.sidebar, text="Settings", command=self.open_settings)
        self.settings_btn.grid(row=2, column=0, padx=20, pady=10)

        self.count_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.count_frame.grid(row=3, column=0, padx=20, pady=10)
        ctk.CTkLabel(self.count_frame, text="Max Videos:").pack(anchor="w")
        self.count_entry = ctk.CTkEntry(self.count_frame, width=140)
        self.count_entry.pack(anchor="w")
        self.count_entry.insert(0, "5")

        # Config Display/Main Area
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(self.main_frame, text="Ready", font=("Roboto", 14))
        self.status_label.grid(row=0, column=0, sticky="w", pady=(0, 10))

        # Console Output
        self.console = ctk.CTkTextbox(self.main_frame, width=400, activate_scrollbars=True)
        self.console.grid(row=1, column=0, sticky="nsew")
        self.console.configure(state="disabled")

        # Setup Logging Redirect
        self.logger = logging.getLogger()
        handler = TextHandler(self.console)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(handler)

        self.pipeline_running = False

    def start_pipeline(self):
        if self.pipeline_running:
            return
        
        try:
            max_v = int(self.count_entry.get())
        except ValueError:
            max_v = 5
            self.count_entry.delete(0, END)
            self.count_entry.insert(0, "5")

        self.pipeline_running = True
        self.start_btn.configure(state="disabled", text="Running...")
        self.status_label.configure(text=f"Pipeline Running (Max: {max_v})...")
        
        thread = threading.Thread(target=self._run_pipeline_thread, args=(max_v,))
        thread.start()

    def _run_pipeline_thread(self, max_v):
        try:
            pipeline = VideoPipeline()
            pipeline.run(max_videos=max_v)
            self.after(0, lambda: self.status_label.configure(text="Completed Successfully"))
        except Exception as e:
            self.logger.error(f"Pipeline crashed: {e}")
            self.after(0, lambda: self.status_label.configure(text="Error occurred"))
        finally:
            self.pipeline_running = False
            self.after(0, lambda: self.start_btn.configure(state="normal", text="Start Generation"))

    def open_settings(self):
        SettingsWindow(self)

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings check 'config.json' for more")
        self.geometry("500x400")
        
        # We will expose a few key settings
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        self.label = ctk.CTkLabel(self, text="Configuration", font=("Roboto", 16, "bold"))
        self.label.grid(row=0, column=0, pady=10)

        # Model Input
        self.model_frame = ctk.CTkFrame(self)
        self.model_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        ctk.CTkLabel(self.model_frame, text="AI Model:").pack(side="left", padx=10)
        self.model_entry = ctk.CTkEntry(self.model_frame, width=250)
        self.model_entry.pack(side="right", padx=10, expand=True)
        self.model_entry.insert(0, config.ai_settings.get("model", ""))

        # Video Res
        self.res_frame = ctk.CTkFrame(self)
        self.res_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        ctk.CTkLabel(self.res_frame, text="Width:").pack(side="left", padx=10)
        self.width_entry = ctk.CTkEntry(self.res_frame, width=80)
        self.width_entry.pack(side="left", padx=5)
        self.width_entry.insert(0, str(config.video_settings.get("width", 1280)))

        ctk.CTkLabel(self.res_frame, text="Height:").pack(side="left", padx=10)
        self.height_entry = ctk.CTkEntry(self.res_frame, width=80)
        self.height_entry.pack(side="left", padx=5)
        self.height_entry.insert(0, str(config.video_settings.get("height", 720)))

        # Save Button
        self.save_btn = ctk.CTkButton(self, text="Save & Close", command=self.save_settings)
        self.save_btn.grid(row=4, column=0, pady=20)
        
        self.info_label = ctk.CTkLabel(self, text="Note: Restart app to apply changes fully.", text_color="gray")
        self.info_label.grid(row=5, column=0)

    def save_settings(self):
        # Update config manager
        config.update_setting("ai_settings", "model", self.model_entry.get())
        try:
            w = int(self.width_entry.get())
            h = int(self.height_entry.get())
            config.update_setting("video_settings", "width", w)
            config.update_setting("video_settings", "height", h)
        except ValueError:
            pass
        
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
