import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import subprocess
import threading
import os
import datetime
import queue
import time
import getpass
import urllib.request
import zipfile
import shutil
import sys
import tempfile
import hashlib
import requests  # pip install requests

# ---------------- OTA CONFIG ----------------
APP_VERSION = "1.0.0"  # bump this when you release a new build
MANIFEST_URL = "https://raw.githubusercontent.com/saisanthoshmanepalli/LogCaptureTool/main/release/manifest.json"

def get_manifest():
    try:
        resp = requests.get(MANIFEST_URL, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[OTA] Failed to fetch manifest: {e}")
        return None

def check_for_update(root=None):
    manifest = get_manifest()
    if not manifest:
        return

    latest_version = manifest["version"]
    notes = manifest.get("notes", "")

    if latest_version == APP_VERSION:
        return  # Already up to date

    if root is None:
        root = tk.Tk()
        root.withdraw()

    if messagebox.askyesno(
        "Update Available",
        f"A new version ({latest_version}) is available.\n\n{notes}\n\nUpdate now?"
    ):
        do_update(manifest)

def do_update(manifest):
    url = manifest["url"]
    sha256_expected = manifest["sha256"]

    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, "update.zip")

    try:
        # Download
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        # Verify
        sha256 = hashlib.sha256()
        with open(zip_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        if sha256.hexdigest() != sha256_expected:
            messagebox.showerror("Update Failed", "Checksum mismatch. Aborting update.")
            return

        # Extract into current folder
        extract_dir = os.path.dirname(__file__)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)

        messagebox.showinfo("Update Complete", "Tool has been updated. Please restart it.")
        sys.exit(0)

    except Exception as e:
        messagebox.showerror("Update Failed", f"Error during update:\n{e}")
    finally:
        try:
            os.remove(zip_path)
        except Exception:
            pass

# ---------------- Device Tools ----------------
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5 MB

IOS_RELEASE_URL = (
    "https://github.com/libimobiledevice-win32/imobiledevice-net/releases/download/"
    "v1.3.17/libimobiledevice.1.2.1-r1122-win-x64.zip"
)
IOS_TOOLS_DIR = os.path.join(os.getcwd(), "ios_tools")

def prepare_ios_tools():
    if os.path.exists(IOS_TOOLS_DIR) and os.path.isfile(os.path.join(IOS_TOOLS_DIR, "idevice_id.exe")):
        return True
    os.makedirs(IOS_TOOLS_DIR, exist_ok=True)
    zip_path = os.path.join(IOS_TOOLS_DIR, "libimobiledevice.zip")
    try:
        urllib.request.urlretrieve(IOS_RELEASE_URL, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(IOS_TOOLS_DIR)
        os.remove(zip_path)
        for root, dirs, files in os.walk(IOS_TOOLS_DIR):
            for file in files:
                if file.endswith(".exe"):
                    try:
                        shutil.move(os.path.join(root, file), os.path.join(IOS_TOOLS_DIR, file))
                    except shutil.Error:
                        pass
        return True
    except Exception as e:
        messagebox.showerror("iOS Tools Setup Failed", f"Error: {e}")
        return False

def check_ios_tools_ready():
    idevice_id_path = os.path.join(IOS_TOOLS_DIR, "idevice_id.exe")
    if not os.path.isfile(idevice_id_path):
        messagebox.showerror("iOS Tools Missing", f"Could not find 'idevice_id.exe' in {IOS_TOOLS_DIR}")
        return False
    return True

# ---------------- Main App ----------------
class LogCaptureApp:
    COLORS = {
        "not_connected": "#e74c3c",
        "connected": "#2ecc71",
        "logging": "#f1c40f",
        "dashboard_bg": "#34495e",
        "dashboard_text": "#ffffff",
        "dashboard_frame": "#2c3e50",
        "button_bg": "#3498db",
        "button_fg": "#ffffff",
        "button_disabled": "#95a5a6",
    }

    def __init__(self, root, tester_name):
        self.root = root
        self.tester_name = tester_name
        self.root.title(f"Log Capture Tool - Tester: {tester_name}")
        self.root.geometry("1000x700")
        self.root.configure(bg="#ecf0f1")

        tk.Label(root, text=f"Tester: {tester_name}", font=("Arial", 16, "bold"), bg="#ecf0f1").pack(pady=10)

        self.platforms = ["Android", "iOS", "Amazon", "WebGL", "Standalone"]

        # Dashboard
        self.dashboard_frame = tk.Frame(root, bg=self.COLORS["dashboard_frame"], relief="raised", bd=2)
        self.dashboard_frame.pack(fill="x", pady=10, padx=10)
        tk.Label(self.dashboard_frame, text="Today's Log Dashboard", font=("Arial", 16, "bold"),
                 fg=self.COLORS["dashboard_text"], bg=self.COLORS["dashboard_frame"]).pack(pady=5)

        self.dashboard_labels = {}
        for platform in self.platforms:
            lbl = tk.Label(self.dashboard_frame, text=f"{platform}: 0 logs", font=("Arial", 12, "bold"),
                           fg=self.COLORS["dashboard_text"], bg=self.COLORS["dashboard_bg"],
                           width=25, anchor="w", padx=10, pady=5)
            lbl.pack(pady=2)
            self.dashboard_labels[platform] = lbl

        # Controls
        self.status_labels = {}
        self.line_labels = {}
        self.buttons = {}
        self.upload_buttons = {}
        self.view_buttons = {}
        self.log_threads = {}
        self.log_queues = {}
        self.running_flags = {}
        self.log_counters = {}
        self.line_counters = {}

        for platform in self.platforms:
            frame = tk.Frame(root, bg="#ecf0f1", relief="groove", bd=2)
            frame.pack(fill="x", pady=5, padx=10)

            tk.Label(frame, text=platform, font=("Arial", 14, "bold"), width=15, anchor="w", bg="#ecf0f1").pack(
                side="left", padx=10
            )

            self.line_labels[platform] = tk.Label(frame, text="0 logs", width=12, anchor="w", bg="#bdc3c7")
            self.line_labels[platform].pack(side="right", padx=5)

            status_label = tk.Label(frame, text="Not started", width=30, anchor="w",
                                    bg=self.COLORS["not_connected"], fg="#ffffff")
            status_label.pack(side="right", padx=10)
            self.status_labels[platform] = status_label

            # Button frame
            button_frame = tk.Frame(frame, bg="#ecf0f1")
            button_frame.pack(side="right", padx=5)

            # Start Logging button
            btn = tk.Button(button_frame, text="Start Logging", state="disabled", width=15,
                            bg=self.COLORS["button_disabled"], fg=self.COLORS["button_fg"],
                            font=("Arial", 12, "bold"), relief="raised", bd=3,
                            command=lambda p=platform: self.start_logging(p))
            btn.pack(side="left", padx=2)
            self.buttons[platform] = btn

            # Upload Build button
            upload_btn = tk.Button(button_frame, text="Upload Build", state="disabled", width=15,
                                   bg=self.COLORS["button_disabled"], fg=self.COLORS["button_fg"],
                                   font=("Arial", 12, "bold"), relief="raised", bd=3,
                                   command=lambda p=platform: self.upload_build(p))
            upload_btn.pack(side="left", padx=2)
            self.upload_buttons[platform] = upload_btn

            # View Logs button
            view_btn = tk.Button(button_frame, text="View Logs", state="normal", width=15,
                                 bg=self.COLORS["button_bg"], fg=self.COLORS["button_fg"],
                                 font=("Arial", 12, "bold"), relief="raised", bd=3,
                                 command=lambda p=platform: self.view_logs(p))
            view_btn.pack(side="left", padx=2)
            self.view_buttons[platform] = view_btn

            self.running_flags[platform] = False
            self.log_queues[platform] = queue.Queue()
            self.log_counters[platform] = 1
            self.line_counters[platform] = 0

        self.update_status_labels()
        self.update_dashboard()
        threading.Thread(target=self.monitor_loop, daemon=True).start()
        threading.Thread(target=self.device_disconnect_monitor, daemon=True).start()

    # (rest of your logging, uploading, and dashboard methods remain unchanged)
    # ...

    # ---------------- Monitoring ----------------
    def monitor_loop(self):
        while True:
            self.update_status_labels()
            self.update_dashboard()
            time.sleep(2)

    def device_disconnect_monitor(self):
        while True:
            android_connected = self.is_android_device_connected()
            ios_connected = self.is_ios_device_connected()
            for platform in self.platforms:
                if platform in ["Android", "Amazon"]:
                    connected = android_connected
                elif platform == "iOS":
                    connected = ios_connected
                else:
                    connected = True
                if connected:
                    self.upload_buttons[platform].config(state="normal", bg=self.COLORS["button_bg"])
                    self.buttons[platform].config(state="normal", bg=self.COLORS["button_bg"])
                else:
                    self.upload_buttons[platform].config(state="disabled", bg=self.COLORS["button_disabled"])
                    self.buttons[platform].config(state="disabled", bg=self.COLORS["button_disabled"])
            time.sleep(5)

# ---------------- Entry ----------------
def ask_tester_name():
    if not prepare_ios_tools() or not check_ios_tools_ready():
        sys.exit(1)

    # 🚀 Run OTA check before showing tester input
    check_for_update()

    popup = tk.Tk()
    popup.title("Enter Name")
    popup.geometry("350x180")
    popup.configure(bg="#ecf0f0")
    tk.Label(popup, text="Tester Name:", font=("Arial", 12), bg="#ecf0f0").pack(pady=10)
    name_entry = tk.Entry(popup, font=("Arial", 12))
    name_entry.pack()

    def submit_name():
        tester_name = name_entry.get().strip()
        if tester_name:
            popup.destroy()
            root = tk.Tk()
            app = LogCaptureApp(root, tester_name)
            root.mainloop()
        else:
            messagebox.showwarning("Missing Name", "Please enter the tester's name.")

    tk.Button(popup, text="Continue", command=submit_name, width=15, bg="#2ecc71", fg="#ffffff").pack(pady=15)
    popup.mainloop()

if __name__ == "__main__":
    ask_tester_name()
