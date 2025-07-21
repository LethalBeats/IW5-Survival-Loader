import customtkinter
from PIL import Image
import threading
import requests
import os
import time
import hashlib
import json
import win32gui
import win32con
import re
import sys

BTN_DOWNLOAD = "Download"
BTN_DISABLED = "disabled"
MSG_FETCHING = "Fetching update info..."
MSG_CHECKING = "Checking updates..."
MSG_NO_TAGS = "No update tags found."
MSG_UPDATE_AVAILABLE = "Update available!"
MSG_UPDATED = "Updated!"
MSG_ERROR_FETCH = "Error fetching tags: "
MSG_ERROR_DOWNLOAD = "Error downloading"
MSG_ERROR_UPDATE = "Error updating: "
MSG_DOWNLOADING = "Downloading..."
MSG_FILE_DOWNLOADING = "Downloading: {fname} ({percent}%)"

IW5_DIR = os.path.expandvars(r'%localappdata%/plutonium/storage/iw5')
GITHUB_API_TAGS = "https://api.github.com/repos/LastDemon99/IW5-Survival-Reimagined/tags"
GITHUB_RELEASE_BASE = "https://github.com/LastDemon99/IW5-Survival-Reimagined/releases/download"

class LauncherGUI():
    def __init__(self):
        customtkinter.set_appearance_mode("dark")
        customtkinter.set_default_color_theme("dark-blue")

        root = customtkinter.CTk()
        root.geometry("350x400")
        root.title("IW5 Survival Loader")
        root.resizable(False, False)

        # Detectar ruta de recursos según entorno (PyInstaller o script)
        if hasattr(sys, '_MEIPASS'):
            media_path = os.path.join(sys._MEIPASS, 'media')
        else:
            media_path = os.path.join(os.path.dirname(__file__), 'media')

        icon_path = os.path.join(media_path, 'icon.ico')
        root.iconbitmap(default=icon_path)

        discord_img_path = os.path.join(media_path, 'discord.png')
        discord_img = customtkinter.CTkImage(light_image=Image.open(discord_img_path), size=(22, 22))
        def open_discord():
            import webbrowser
            webbrowser.open_new('https://discord.com/invite/PrpYznV33s')
        discord_btn = customtkinter.CTkButton(root, image=discord_img, text="", width=32, height=32, fg_color="transparent", command=open_discord)
        discord_btn.place(x=308, y=10)

        logo_path = os.path.join(media_path, 'lethalbeats.png')
        logo = customtkinter.CTkImage(light_image=Image.open(logo_path), size=(320, 190))
        image_label = customtkinter.CTkLabel(root, image=logo, text="")
        image_label.pack(side='top', pady=(40, 0))

        frame = customtkinter.CTkFrame(master=root, width=660, height=40, fg_color="transparent")
        frame.pack(side='bottom')
        self.progressbar_frame = frame

        self.button = customtkinter.CTkButton(root, text="", width=200, height=55, command=self.on_button_click)
        self.button.pack(side='bottom', pady=35)
        self.status_label = customtkinter.CTkLabel(root, text="", width=200, height=55)
        self.status_label.pack_forget()

        progressbar = customtkinter.CTkProgressBar(frame, orientation="horizontal", width=660)
        progressbar.pack(padx=6, pady=3)
        self.progressbar = progressbar

        self.progressbar_label = customtkinter.CTkLabel(frame, text="Progress: 0%", fg_color="transparent")
        self.progressbar_label.pack()

        self.update_needed = False
        self.latest_tag = None
        self.latest_sha = None
        self.latest_file_data = None
        self.retry_count = 0
        self.max_retries = 3

        threading.Thread(target=self.fetch_and_check, daemon=True).start()
        root.mainloop()

    def show_status_label(self, text):
        self.button.pack_forget()
        self.status_label.configure(text=text)
        self.status_label.pack(side='bottom', pady=35)

    def show_button(self):
        self.status_label.pack_forget()
        self.button.pack(side='bottom', pady=35)

    def set_button_state(self, text, state):
        self.button.configure(text=text, state=state)

    def set_progress(self, percent, label):
        self.progressbar.set(percent / 100)
        self.progressbar_label.configure(text=label)
        self.progressbar_frame.update_idletasks()

    def fetch_and_check(self):
        self.retry_count += 1
        self.set_progress(0, MSG_FETCHING)
        running = True

        def animate():
            while running:
                for i in range(0, 101, 10):
                    if not running:
                        break
                    self.set_progress(i, MSG_FETCHING)
                    time.sleep(0.05)
                if running:
                    self.set_progress(0, MSG_FETCHING)

        anim_thread = threading.Thread(target=animate, daemon=True)
        anim_thread.start()

        try:
            tags = self.get_tags()
            running = False
            anim_thread.join(timeout=1)
            self.retry_count = 0
        except Exception as e:
            running = False
            anim_thread.join(timeout=1)
            error_msg = str(e)

            if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                error_msg = "Connection timeout. Check your internet connection."

            if self.retry_count < self.max_retries:
                self.set_progress(100, f"Error: {error_msg} (Retry {self.retry_count}/{self.max_retries})")
                self.set_button_state("Retry", "normal")
                self.update_needed = False
                return
            else:
                self.set_progress(100, MSG_ERROR_FETCH + error_msg)
                self.set_button_state("Retry", "normal")
                self.retry_count = 0
                return
        
        self.set_progress(0, MSG_CHECKING)
        try:
            self.check_update_status(tags)
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                error_msg = "Connection timeout during update check."            
            if self.retry_count < self.max_retries:
                self.set_progress(100, f"Error: {error_msg} (Retry {self.retry_count}/{self.max_retries})")
                self.set_button_state("Retry", "normal")
                self.update_needed = False
            else:
                self.set_progress(100, MSG_ERROR_UPDATE + error_msg)
                self.set_button_state("Retry", "normal")
                self.retry_count = 0

    def get_tags(self, force_reload=False):
        try:
            response = requests.get(GITHUB_API_TAGS, timeout=15)
            response.raise_for_status()
            if not response.content:
                raise Exception("Empty response from GitHub API")
            tags = response.json()
            if not isinstance(tags, list):
                raise Exception("Invalid response format from GitHub API")
            self.tags_cache = tags
            return tags
        except requests.exceptions.Timeout:
            raise Exception("Connection timeout while fetching tags")
        except requests.exceptions.ConnectionError:
            raise Exception("Network connection error")
        except requests.exceptions.HTTPError as e:
            raise Exception(f"HTTP error {e.response.status_code}")
        except json.JSONDecodeError:
            raise Exception("Invalid JSON response from GitHub API")
        except Exception as e:
            if hasattr(e, 'args') and e.args:
                raise
            else:
                raise Exception("Unknown error while fetching tags")

    def find_tag(self, prefix):
        tags = self.get_tags()
        return [t for t in tags if t['name'].startswith(prefix)]

    def check_update_status(self, tags=None):
        if not tags:
            tags = self.get_tags()
        valid_tags = [t for t in tags if t['name'].startswith('iw5-mp-survival')]
        if not valid_tags:
            self.set_progress(100, MSG_NO_TAGS)
            self.set_button_state(BTN_DOWNLOAD, BTN_DISABLED)
            return
        latest_tag = sorted(valid_tags, key=lambda t: t['name'], reverse=True)[0]
        tag_name = latest_tag['name']
        validation_url = f"{GITHUB_RELEASE_BASE}/{tag_name}/survival_validation.json"
        try:
            response = requests.get(validation_url, timeout=15)
            response.raise_for_status()
            
            if not response.content:
                raise Exception("Empty validation file")
                
            validation_json = response.text
            validation_dict = json.loads(validation_json)
            
            if not isinstance(validation_dict, dict):
                raise Exception("Invalid validation file format")
                
        except requests.exceptions.Timeout:
            self.set_progress(100, "Timeout downloading validation file")
            self.set_button_state(BTN_DOWNLOAD, BTN_DISABLED)
            return
        except requests.exceptions.ConnectionError:
            self.set_progress(100, "Network error downloading validation file")
            self.set_button_state(BTN_DOWNLOAD, BTN_DISABLED)
            return
        except requests.exceptions.HTTPError as e:
            self.set_progress(100, f"Validation file not found (HTTP {e.response.status_code})")
            self.set_button_state(BTN_DOWNLOAD, BTN_DISABLED)
            return
        except json.JSONDecodeError:
            self.set_progress(100, "Invalid validation file format")
            self.set_button_state(BTN_DOWNLOAD, BTN_DISABLED)
            return
        except Exception as e:
            self.set_progress(100, MSG_ERROR_DOWNLOAD + f": {str(e)}")
            self.set_button_state(BTN_DOWNLOAD, BTN_DISABLED)
            return
            
        update_needed = False
        files_to_update = []
        
        for fname, remote_sha in validation_dict.get("checksum", {}).items():
            local_path = os.path.join(IW5_DIR, fname)
            local_sha = None
            if os.path.exists(local_path):
                try:
                    with open(local_path, 'rb') as f:
                        local_sha = hashlib.sha1(f.read()).hexdigest()
                except Exception:
                    local_sha = None
            if (not os.path.exists(local_path)) or (local_sha != remote_sha):
                update_needed = True
                files_to_update.append(fname)
        
        missing_files = []
        for fname in validation_dict.get("exist", []):
            local_path = os.path.join(IW5_DIR, fname)
            if not os.path.exists(local_path):
                update_needed = True
                missing_files.append(fname)
                if fname not in files_to_update:
                    files_to_update.append(fname)
        
        self.latest_tag = latest_tag
        self.latest_sha = validation_dict.get("checksum", {})
        self.files_to_update = files_to_update
        self.missing_files = missing_files

        if update_needed:
            self.set_button_state(BTN_DOWNLOAD, "normal")
            self.update_needed = True
            self.set_progress(100, MSG_UPDATE_AVAILABLE)
        else:
            self.set_button_state("Waiting game", BTN_DISABLED)
            self.update_needed = False
            self.set_progress(100, MSG_UPDATED)
            threading.Thread(target=self.wait_for_game_and_load_mod, daemon=True).start()

    def wait_for_game_and_load_mod(self):
        def get_game_hwnd_and_version():
            hwnd_list = []
            def enum_windows_callback(hwnd, _):
                window_text = win32gui.GetWindowText(hwnd)
                match = re.search(r"Plutonium IW5: Multiplayer \(r(\d+)\)", window_text)
                if match:
                    hwnd_list.append((hwnd, f"r{match.group(1)}"))
            win32gui.EnumWindows(enum_windows_callback, None)
            return hwnd_list[0] if hwnd_list else (None, None)
        def get_version_subwindow(version):
            hwnd_list = []
            def enum_windows_callback(hwnd, _):
                window_text = win32gui.GetWindowText(hwnd)
                if window_text == f"Plutonium {version}":
                    hwnd_list.append(hwnd)
            win32gui.EnumWindows(enum_windows_callback, None)
            return hwnd_list[0] if hwnd_list else None
        def send_cmd(texto, hwnd):
            texto = texto + "\r"
            for char in texto:
                win32gui.SendMessage(hwnd, win32con.WM_CHAR, ord(char), 0)
                time.sleep(0.01)
            win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
            win32gui.SendMessage(hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
            time.sleep(0.05)
        while True:
            hwnd, version = get_game_hwnd_and_version()
            while not hwnd:
                time.sleep(0.05)
                hwnd, version = get_game_hwnd_and_version()
            game_hwnd = get_version_subwindow(version)
            while not game_hwnd:
                time.sleep(0.05)
                game_hwnd = get_version_subwindow(version)
            self.set_button_state("Game Open", BTN_DISABLED)
            self.set_progress(100, MSG_UPDATED)
            send_cmd("fs_game mods/survival", game_hwnd)
            send_cmd("vid_restart_safe", game_hwnd)
            send_cmd("load_dsr survival", game_hwnd)
            self.set_button_state("Mod Loaded", BTN_DISABLED)
            self.set_progress(100, MSG_UPDATED)
            while win32gui.IsWindow(game_hwnd):
                time.sleep(1)
            self.set_button_state("Waiting game", BTN_DISABLED)
            self.set_progress(100, MSG_UPDATED)

    def on_button_click(self):
        if not self.update_needed and (self.button.cget("text") == "Retry" or not hasattr(self, 'latest_tag') or self.latest_tag is None):
            threading.Thread(target=self.fetch_and_check, daemon=True).start()
            return
            
        if self.update_needed:
            def download_and_update():
                self.set_progress(0, MSG_DOWNLOADING)
                try:
                    def download_file(url, dest_path, label=None, progress_start=0, progress_end=50):
                        with requests.get(url, timeout=30, stream=True) as response:
                            response.raise_for_status()
                            total_size = int(response.headers.get('content-length', 0))
                            downloaded_size = 0
                            with open(dest_path, "wb") as f:
                                for chunk in response.iter_content(chunk_size=1024*1024):
                                    if chunk:
                                        f.write(chunk)
                                        downloaded_size += len(chunk)
                                        if total_size > 0 and label:
                                            percent = progress_start + int((downloaded_size / total_size) * (progress_end-progress_start))
                                            self.set_progress(percent, f"{label} ({percent}%)")

                    def extract_from_rar(rar_path, files, extract_dir):
                        import rarfile
                        with rarfile.RarFile(rar_path) as rf:
                            total_files = len(files)
                            for idx, fname in enumerate(files):
                                dest_path = os.path.join(extract_dir, fname)
                                dest_dir = os.path.dirname(dest_path)
                                if not os.path.exists(dest_dir):
                                    os.makedirs(dest_dir, exist_ok=True)
                                try:
                                    rf.extract(fname, path=extract_dir)
                                    percent = 50 + int(((idx + 1) / total_files) * 50)
                                    self.set_progress(percent, MSG_FILE_DOWNLOADING.format(fname=fname, percent=percent))
                                except Exception as e:
                                    print(f"Error extracting {fname}: {e}")

                    def extract_from_zip(zip_path, filename, extract_dir):
                        import zipfile
                        dest_path = os.path.join(extract_dir, filename)
                        dest_dir = os.path.dirname(dest_path)
                        if not os.path.exists(dest_dir):
                            os.makedirs(dest_dir, exist_ok=True)
                        with zipfile.ZipFile(zip_path, "r") as zf:
                            if filename in zf.namelist():
                                zf.extract(filename, path=extract_dir)
                            else:
                                raise Exception(f"{filename} not found in ZIP")

                    rar_files = list(set(self.files_to_update))
                    if rar_files:
                        import tempfile
                        rar_path = os.path.join(tempfile.gettempdir(), "IW5-Survival-Reimagined.rar")
                        tag_name = self.latest_tag['name']
                        rar_url = f"{GITHUB_RELEASE_BASE}/{tag_name}/IW5-Survival-Reimagined.rar"
                        download_file(rar_url, rar_path, label="Downloading: IW5-Survival-Reimagined.rar")
                        self.set_progress(50, "Download complete, extracting files...")
                        try:
                            extract_from_rar(rar_path, rar_files, IW5_DIR)
                        finally:
                            try:
                                os.remove(rar_path)
                            except:
                                pass

                    if "z_svr_bots.iwd" in self.files_to_update:
                        bots_url = "https://github.com/ineedbots/iw5_bot_warfare/releases/download/v2.3.0/iw5bw230.zip"
                        self.set_progress(0, "Downloading: z_svr_bots.iwd (Bot Warfare)")
                        import tempfile
                        zip_path = os.path.join(tempfile.gettempdir(), "iw5bw230.zip")
                        download_file(bots_url, zip_path, label="Downloading: z_svr_bots.iwd (Bot Warfare)", progress_start=0, progress_end=10)
                        extract_from_zip(zip_path, "z_svr_bots.iwd", IW5_DIR)
                        try:
                            os.remove(zip_path)
                        except:
                            pass
                        self.set_progress(10, "z_svr_bots.iwd downloaded")

                    self.set_button_state("Waiting game", BTN_DISABLED)
                    self.set_progress(100, MSG_UPDATED)
                    self.update_needed = False
                    threading.Thread(target=self.wait_for_game_and_load_mod, daemon=True).start()
                    
                except requests.exceptions.Timeout:
                    self.set_progress(100, "Download timeout. Try again.")
                    self.set_button_state(BTN_DOWNLOAD, "normal")
                except requests.exceptions.ConnectionError:
                    self.set_progress(100, "Network error during download. Try again.")
                    self.set_button_state(BTN_DOWNLOAD, "normal")
                except requests.exceptions.HTTPError as e:
                    self.set_progress(100, f"Download failed (HTTP {e.response.status_code})")
                    self.set_button_state(BTN_DOWNLOAD, "normal")
                except Exception as e:
                    error_msg = str(e)
                    if "rarfile" in error_msg.lower():
                        error_msg = "Error extracting files. RAR file may be corrupted."
                    self.set_progress(100, MSG_ERROR_UPDATE + error_msg)
                    self.set_button_state(BTN_DOWNLOAD, "normal")
            threading.Thread(target=download_and_update, daemon=True).start()
        else:
            threading.Thread(target=self.wait_for_game_and_load_mod, daemon=True).start()

launcher = LauncherGUI()
