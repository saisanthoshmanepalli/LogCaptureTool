import tkinter as tk
from tkinter import messagebox, ttk, scrolledtext, filedialog
import subprocess
import threading
import os
import datetime
import time
import urllib.request
import zipfile
import shutil
import sys
import tempfile
import hashlib
import requests

MAX_LOG_SIZE = 5 * 1024 * 1024  # 5 MB

# OTA CONFIG
APP_VERSION = "1.4.7"
MANIFEST_URL = "https://raw.githubusercontent.com/saisanthoshmanepalli/LogCaptureTool/main/release/manifest.json"

# ---------------- OTA FUNCTIONS ----------------
def get_manifest():
    try:
        resp = requests.get(MANIFEST_URL, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[OTA] Failed to fetch manifest: {e}")
        return None

def check_for_update(root):
    manifest = get_manifest()
    if not manifest:
        return
    latest_version = manifest["version"]
    notes = manifest.get("notes", "")
    if latest_version == APP_VERSION:
        return
    if messagebox.askyesno(
        "Update Available",
        f"A new version ({latest_version}) is available.\n\n{notes}\n\nUpdate now?"
    ):
        threading.Thread(target=lambda: do_update(root, manifest), daemon=True).start()

def do_update(root, manifest):
    url = manifest["url"]
    sha256_expected = manifest["sha256"]
    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, "update.zip")

    progress_win = tk.Toplevel(root)
    progress_win.title("Updating...")
    tk.Label(progress_win, text="Downloading update...").pack(pady=10)
    progress_bar = ttk.Progressbar(progress_win, length=300, mode="determinate")
    progress_bar.pack(pady=10)
    progress_win.update()

    try:
        # ---- Download the update ----
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        progress = int(downloaded / total * 100)
                        progress_bar["value"] = progress
                        progress_win.update()

        # ---- Verify checksum ----
        sha256 = hashlib.sha256()
        with open(zip_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        if sha256.hexdigest() != sha256_expected:
            messagebox.showerror("Update Failed", "Checksum mismatch. Aborting update.")
            progress_win.destroy()
            return

        # ---- Extract to temp dir ----
        extract_dir = os.path.join(tmp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)

        # ---- Overwrite current folder ----
        current_dir = os.getcwd()
        for item in os.listdir(extract_dir):
            s = os.path.join(extract_dir, item)
            d = os.path.join(current_dir, item)
            if os.path.isdir(s):
                if os.path.exists(d):
                    shutil.rmtree(d)
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)

        progress_win.destroy()
        messagebox.showinfo("Update Complete", f"Tool updated to {manifest['version']}.\nRestarting now...")

        # ---- Restart from the same script ----
        exe = sys.executable
        script_path = os.path.abspath(sys.argv[0])
        os.execl(exe, exe, script_path, *sys.argv[1:])

    except Exception as e:
        progress_win.destroy()
        messagebox.showerror("Update Failed", f"Error during update:\n{e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)



# ---------------- iOS TOOLS ----------------
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
        for root_dir, dirs, files in os.walk(IOS_TOOLS_DIR):
            for file in files:
                if file.endswith(".exe"):
                    try:
                        shutil.move(os.path.join(root_dir, file), os.path.join(IOS_TOOLS_DIR, file))
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

# ---------------- MAIN APP ----------------
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

    PREDEFINED_KEYWORDS = ["Unity", "GameException", "Exception"]

    def __init__(self, root, tester_name, feature_name):
        self.root = root
        self.tester_name = tester_name
        self.feature_name = feature_name
        self.root.title(f"Log Capture Tool - Tester: {tester_name} - Feature: {feature_name}")
        self.root.geometry("900x700")
        self.root.configure(bg="#ecf0f1")

        tk.Label(root, text=f"Tester: {tester_name} | Feature: {feature_name}",
                 font=("Arial", 16, "bold"), bg="#ecf0f1").pack(pady=10)

        self.platforms = ["Android", "iOS", "Amazon", "WebGL", "Standalone"]

        # Dashboard
        self.dashboard_frame = tk.Frame(root, bg=self.COLORS["dashboard_frame"], relief="raised", bd=2)
        self.dashboard_frame.pack(fill="x", pady=10, padx=10)
        tk.Label(self.dashboard_frame, text="Today's Log Dashboard",
                 font=("Arial", 16, "bold"), fg=self.COLORS["dashboard_text"], bg=self.COLORS["dashboard_frame"]).pack(pady=5)

        self.dashboard_labels = {}
        for platform in self.platforms:
            lbl = tk.Label(self.dashboard_frame, text=f"{platform}: 0 logs",
                           font=("Arial", 12, "bold"), fg=self.COLORS["dashboard_text"],
                           bg=self.COLORS["dashboard_bg"], width=25, anchor="w", padx=10, pady=5)
            lbl.pack(pady=2)
            self.dashboard_labels[platform] = lbl

        # Controls
        self.status_labels = {}
        self.line_labels = {}
        self.buttons = {}
        self.view_buttons = {}
        self.log_threads = {}
        self.running_flags = {}
        self.line_counters = {}

        for platform in self.platforms:
            frame = tk.Frame(root, bg="#ecf0f1", relief="groove", bd=2)
            frame.pack(fill="x", pady=5, padx=10)

            tk.Label(frame, text=platform, font=("Arial", 14, "bold"), width=15, anchor="w", bg="#ecf0f1").pack(side="left", padx=10)

            self.line_labels[platform] = tk.Label(frame, text="0 lines", width=12, anchor="w", bg="#bdc3c7")
            self.line_labels[platform].pack(side="right", padx=5)

            status_label = tk.Label(frame, text="Not started", width=30, anchor="w", bg=self.COLORS["not_connected"], fg="#ffffff")
            status_label.pack(side="right", padx=10)
            self.status_labels[platform] = status_label

            btn = tk.Button(frame, text="Start Logging", state="disabled", width=15,
                            bg=self.COLORS["button_disabled"], fg=self.COLORS["button_fg"],
                            font=("Arial", 12, "bold"), relief="raised", bd=3,
                            command=lambda p=platform: self.start_logging(p))
            btn.pack(side="right", padx=10)
            self.buttons[platform] = btn

            view_btn = tk.Button(frame, text="View Logs", width=12, bg="#8e44ad", fg="#ffffff",
                                 font=("Arial", 10, "bold"),
                                 command=lambda p=platform: self.view_logs_popup(p))
            view_btn.pack(side="right", padx=10)
            self.view_buttons[platform] = view_btn

            self.running_flags[platform] = False
            self.line_counters[platform] = 0

        self.update_status_labels()
        self.update_dashboard()
        threading.Thread(target=self.monitor_loop, daemon=True).start()
        self.last_no_device_time = None
        threading.Thread(target=self.device_disconnect_monitor, daemon=True).start()

    # ---------------- LOG VIEWER WITH DOWNLOAD ----------------
    def view_logs_popup(self, platform):
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        hour_str = datetime.datetime.now().strftime("%H")
        log_dir = os.path.join("logs", date_str, self.tester_name, hour_str, self.feature_name, platform.lower())
        if not os.path.exists(log_dir):
            messagebox.showinfo("No Logs", f"No logs found for {platform} yet.")
            return

        popup = tk.Toplevel(self.root)
        popup.title(f"View Logs - {platform}")
        popup.geometry("800x600")

        tk.Label(popup, text=f"Filter Keywords:", font=("Arial", 12, "bold")).pack(pady=5)
        keyword_vars = {}
        frame = tk.Frame(popup)
        frame.pack()
        for kw in self.PREDEFINED_KEYWORDS:
            var = tk.BooleanVar(value=True)
            tk.Checkbutton(frame, text=kw, variable=var, font=("Arial", 12)).pack(side="left", padx=5)
            keyword_vars[kw] = var

        text_area = scrolledtext.ScrolledText(popup, width=100, height=25)
        text_area.pack(pady=10)

        filtered_lines = []

        def search_logs():
            nonlocal filtered_lines
            text_area.delete("1.0", tk.END)
            filtered_lines.clear()
            keywords = [kw for kw, var in keyword_vars.items() if var.get()]
            if not keywords:
                messagebox.showwarning("No Keywords", "Select at least one keyword")
                return

            colors = ["#e74c3c", "#f1c40f", "#2ecc71", "#3498db", "#8e44ad"]
            for i, kw in enumerate(keywords):
                text_area.tag_config(kw, foreground=colors[i % len(colors)], font=("Arial", 10, "bold"))

            log_files = sorted(
                f for f in os.listdir(log_dir)
                if f.startswith(f"log_{self.tester_name}_{self.feature_name}") and f.endswith(".txt")
            )

            for file in log_files:
                file_path = os.path.join(log_dir, file)
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if any(kw.lower() in line.lower() for kw in keywords):
                            start_index = text_area.index(tk.END)
                            text_area.insert(tk.END, line)
                            filtered_lines.append(line)
                            for kw in keywords:
                                idx = start_index
                                while True:
                                    idx = text_area.search(kw, idx, nocase=1, stopindex=tk.END)
                                    if not idx:
                                        break
                                    end_idx = f"{idx}+{len(kw)}c"
                                    text_area.tag_add(kw, idx, end_idx)
                                    idx = end_idx

            text_area.see(tk.END)
            download_btn.config(state="normal")

        def download_filtered_logs():
            if not filtered_lines:
                messagebox.showwarning("No Data", "No filtered logs to download.")
                return
            save_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt")],
                title="Save Filtered Logs As"
            )
            if save_path:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.writelines(filtered_lines)
                messagebox.showinfo("Download Complete", f"Filtered logs saved to {save_path}")

        tk.Button(popup, text="Search", command=search_logs,
                  bg="#27ae60", fg="#ffffff", font=("Arial", 12, "bold")).pack(pady=5)

        download_btn = tk.Button(popup, text="Download Filtered Logs",
                                 command=download_filtered_logs, bg="#2980b9",
                                 fg="#ffffff", font=("Arial", 12, "bold"), state="disabled")
        download_btn.pack(pady=5)

    # ---------------- DEVICE CHECKS ----------------
    def is_android_device_connected(self):
        try:
            result = subprocess.check_output(["adb", "devices"], stderr=subprocess.STDOUT, text=True)
            devices = [line for line in result.strip().split("\n")[1:] if "device" in line]
            return len(devices) > 0
        except Exception:
            return False

    def is_ios_device_connected(self):
        try:
            idevice_id = os.path.join(IOS_TOOLS_DIR, "idevice_id.exe")
            result = subprocess.check_output([idevice_id, "-l"], stderr=subprocess.STDOUT, text=True)
            return len(result.strip().splitlines()) > 0
        except Exception:
            return False

    # ---------------- START LOGGING ----------------
    def start_logging(self, platform):
        if self.running_flags[platform]:
            messagebox.showwarning("Already Running", f"{platform} logging is already running.")
            return

        self.running_flags[platform] = True
        self.status_labels[platform].config(text="Starting...", bg=self.COLORS["logging"])
        self.buttons[platform].config(state="disabled", bg=self.COLORS["button_disabled"])

        date_str = datetime.datetime.now().strftime("%Y%m%d")
        hour_str = datetime.datetime.now().strftime("%H")
        tester = self.tester_name
        log_dir = os.path.join("logs", date_str, tester, hour_str, self.feature_name, platform.lower())
        os.makedirs(log_dir, exist_ok=True)
        log_file_base = os.path.join(log_dir, f"log_{tester}_{self.feature_name}")

        # Clear device log buffer
        if platform in ["Android", "Amazon"]:
            try:
                subprocess.run(["adb", "logcat", "-c"], check=True)
                print(f"[{platform}] Device log buffer cleared")
            except Exception as e:
                print(f"[{platform}] Failed to clear device log buffer: {e}")
        elif platform == "iOS":
            try:
                subprocess.run(["taskkill", "/F", "/IM", "idevicesyslog.exe"], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("[iOS] Cleared existing idevicesyslog processes")
            except Exception as e:
                print(f"[iOS] Failed to clear idevicesyslog: {e}")

        # Start logging thread
        if platform in ["Android", "Amazon"]:
            thread = threading.Thread(target=self._run_adb_logcat, args=(platform, log_file_base), daemon=True)
        elif platform == "iOS":
            thread = threading.Thread(target=self._run_ios_syslog, args=(platform, log_file_base), daemon=True)
        else:
            thread = threading.Thread(target=self._simulate_log_capture, args=(platform, log_file_base), daemon=True)

        self.log_threads[platform] = thread
        thread.start()

    # ---------------- LOGGING THREADS ----------------
    def _run_adb_logcat(self, platform, log_file_base):
        try:
            proc = subprocess.Popen(["adb", "logcat"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            file_index = 1
            log_file_path = f"{log_file_base}_{file_index}.txt"
            f = open(log_file_path, "a", encoding="utf-8")

            while self.running_flags[platform]:
                line = proc.stdout.readline()
                if not line:
                    break
                f.write(line)
                self.line_counters[platform] += 1

                if f.tell() >= MAX_LOG_SIZE:
                    f.close()
                    file_index += 1
                    log_file_path = f"{log_file_base}_{file_index}.txt"
                    f = open(log_file_path, "a", encoding="utf-8")

        finally:
            f.close()
            self.running_flags[platform] = False
            if proc.poll() is None:
                proc.terminate()

    def _run_ios_syslog(self, platform, log_file_base):
        try:
            subprocess.run(["taskkill", "/F", "/IM", "idevicesyslog.exe"], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc = subprocess.Popen([os.path.join(IOS_TOOLS_DIR, "idevicesyslog.exe")],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            file_index = 1
            log_file_path = f"{log_file_base}_{file_index}.txt"
            f = open(log_file_path, "a", encoding="utf-8")

            while self.running_flags[platform]:
                line = proc.stdout.readline()
                if not line:
                    break
                f.write(line)
                self.line_counters[platform] += 1

                if f.tell() >= MAX_LOG_SIZE:
                    f.close()
                    file_index += 1
                    log_file_path = f"{log_file_base}_{file_index}.txt"
                    f = open(log_file_path, "a", encoding="utf-8")

        finally:
            f.close()
            self.running_flags[platform] = False
            if proc.poll() is None:
                proc.terminate()

    def _simulate_log_capture(self, platform, log_file_base):
        file_index = 1
        log_file_path = f"{log_file_base}_{file_index}.txt"
        try:
            f = open(log_file_path, "a", encoding="utf-8")
            while self.running_flags[platform]:
                line = f"{platform} log entry at {datetime.datetime.now()}\n"
                f.write(line)
                self.line_counters[platform] += 1
                time.sleep(1)
                if f.tell() >= MAX_LOG_SIZE:
                    f.close()
                    file_index += 1
                    log_file_path = f"{log_file_base}_{file_index}.txt"
                    f = open(log_file_path, "a", encoding="utf-8")
        finally:
            f.close()
            self.running_flags[platform] = False

    # ---------------- MONITORING ----------------
    def monitor_loop(self):
        while True:
            self.update_status_labels()
            self.update_dashboard()
            time.sleep(2)

    def device_disconnect_monitor(self):
        while True:
            android_connected = self.is_android_device_connected()
            ios_connected = self.is_ios_device_connected()
            if not android_connected and not ios_connected:
                if getattr(self, 'last_no_device_time', None) is None:
                    self.last_no_device_time = time.time()
                elif time.time() - self.last_no_device_time >= 60:
                    self.root.after(0, lambda: messagebox.showwarning(
                        "Device Disconnected",
                        "No device has been connected for more than 1 minute!"
                    ))
                    self.last_no_device_time = time.time()
            else:
                self.last_no_device_time = None
            time.sleep(5)

    def update_status_labels(self):
        android_connected = self.is_android_device_connected()
        ios_connected = self.is_ios_device_connected()

        for platform in self.platforms:
            if platform in ["Android", "Amazon"]:
                connected = android_connected
            elif platform == "iOS":
                connected = ios_connected
            else:
                connected = True

            if self.running_flags[platform]:
                status_text, status_bg = "Logging...", self.COLORS["logging"]
            elif connected:
                status_text, status_bg = "Connected", self.COLORS["connected"]
            else:
                status_text, status_bg = "Not Connected", self.COLORS["not_connected"]

            self.status_labels[platform].config(text=status_text, bg=status_bg)

            if connected and not self.running_flags[platform]:
                self.buttons[platform].config(state="normal", bg=self.COLORS["button_bg"])
            else:
                self.buttons[platform].config(state="disabled", bg=self.COLORS["button_disabled"])

    def update_dashboard(self):
        for platform in self.platforms:
            self.dashboard_labels[platform].config(text=f"{platform}: {self.line_counters[platform]} lines")
            self.line_labels[platform].config(text=f"{self.line_counters[platform]} lines")

# ---------------- ENTRY ----------------
def ask_tester_and_feature():
    if not prepare_ios_tools() or not check_ios_tools_ready():
        sys.exit(1)

    popup = tk.Tk()
    popup.title("Enter Tester and Feature")
    popup.geometry("400x220")
    popup.configure(bg="#ecf0f0")

    tk.Label(popup, text="Tester Name:", font=("Arial", 12), bg="#ecf0f0").pack(pady=5)
    name_entry = tk.Entry(popup, font=("Arial", 12))
    name_entry.pack()

    tk.Label(popup, text="Feature Name:", font=("Arial", 12), bg="#ecf0f0").pack(pady=5)
    feature_entry = tk.Entry(popup, font=("Arial", 12))
    feature_entry.pack()

    def submit():
        tester = name_entry.get().strip()
        feature = feature_entry.get().strip()
        if not tester or not feature:
            messagebox.showwarning("Missing Info", "Please enter both tester and feature names.")
            return
        popup.destroy()
        root = tk.Tk()
        app = LogCaptureApp(root, tester, feature)
        root.mainloop()

    tk.Button(popup, text="Continue", command=submit, width=15, bg="#2ecc71", fg="#ffffff").pack(pady=20)
    popup.mainloop()

if __name__ == "__main__":
    ask_tester_and_feature()
