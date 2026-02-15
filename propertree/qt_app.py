import json
import os
import re
import subprocess
import sys
import webbrowser
from collections import OrderedDict

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox

from propertree import plist
from propertree.qt_workers import TexDownloadWorker, UpdateCheckWorker


class ProperTreeApp:
    def __init__(self, app, plists=None):
        if plists is None:
            plists = []
        self.app = app
        self.creating_window = False
        self.is_opening = False
        self.is_quitting = False
        self.is_checking_for_updates = False
        self.start_window = None

        # Set up our defaults for our option lists
        self.allowed_types = ("XML", "Binary")
        self.allowed_data = ("Hex", "Base64")
        self.allowed_int = ("Decimal", "Hex")
        self.allowed_bool = ("True/False", "YES/NO", "On/Off", "1/0", "\u2714/\u274c")
        self.allowed_conv = ("Ascii", "Base64", "Decimal", "Hex", "Binary")

        # Set the default max undo/redo steps to retain
        self.max_undo = 200

        # Window tracking
        self.windows = []

        # Default color themes
        self.default_dark = {
            "alternating_color_1": "#161616",
            "alternating_color_2": "#202020",
            "highlight_color": "#1E90FF",
            "background_color": "#161616",
            "invert_background_text_color": False,
            "invert_row1_text_color": False,
            "invert_row2_text_color": False,
        }
        self.default_light = {
            "alternating_color_1": "#F0F1F1",
            "alternating_color_2": "#FEFEFE",
            "highlight_color": "#1E90FF",
            "background_color": "#FEFEFE",
            "invert_background_text_color": False,
            "invert_row1_text_color": False,
            "invert_row2_text_color": False,
        }

        # URLs
        self.version_url = "https://raw.githubusercontent.com/corpnewt/ProperTree/master/Scripts/version.json"
        self.tex_url = "https://raw.githubusercontent.com/acidanthera/OpenCorePkg/master/Docs/Configuration.tex"
        self.repo_url = "https://github.com/corpnewt/ProperTree"

        # Regex to find the processor serial numbers when opened from the Finder
        self.regexp = re.compile(r"^-psn_[0-9]+_[0-9]+$")

        # Resolve the base directory (where qtProperTree lives)
        if getattr(sys, "frozen", False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

        # macOS: try to set the app name via NSBundle
        if sys.platform == "darwin":
            try:
                from Foundation import NSBundle

                bundle = NSBundle.mainBundle()
                if bundle:
                    info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
                    if info and info.get("CFBundleName") == "Python":
                        info["CFBundleName"] = "qtProperTree"
            except Exception:
                pass

        # Load settings
        self.settings = {}
        settings_path = os.path.join(self.base_dir, "propertree", "settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r") as f:
                    self.settings = json.load(f)
            except Exception:
                pass

        # Load snapshot data
        self.snapshot_data = {}
        snapshot_path = os.path.join(self.base_dir, "propertree", "snapshot.plist")
        if os.path.exists(snapshot_path):
            try:
                with open(snapshot_path, "rb") as f:
                    self.snapshot_data = plist.load(f)
            except Exception:
                pass

        # Load version info
        self.version = {}
        version_path = os.path.join(self.base_dir, "propertree", "version.json")
        if os.path.exists(version_path):
            try:
                with open(version_path, "r") as f:
                    self.version = json.load(f)
            except Exception:
                pass

        # Detect initial dark mode
        self.use_dark = self.get_dark()

        # Normalize the pathing for Open Recents
        self.normpath_recents()

        # Workers (will be set when a check/download is in progress)
        self._update_worker = None
        self._tex_worker = None

        # Start dark mode polling timer
        self._dark_mode_timer = QTimer()
        self._dark_mode_timer.timeout.connect(self._check_dark_mode)
        self._dark_mode_timer.start(1500)

        # Open initial plists or create a new window
        self.check_open(plists)

        # Check for updates at startup if enabled
        if self.settings.get("check_for_updates_at_startup", True):
            QTimer.singleShot(0, lambda: self.check_for_updates(user_initiated=False))

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def save_settings(self):
        """Save current settings to propertree/settings.json."""
        settings_path = os.path.join(self.base_dir, "propertree", "settings.json")
        try:
            with open(settings_path, "w") as f:
                json.dump(self.settings, f, indent=4)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Window tracking helpers
    # ------------------------------------------------------------------

    def add_window(self, window):
        """Register a PlistWindow instance."""
        if window not in self.windows:
            self.windows.append(window)

    def remove_window(self, window):
        """Unregister a PlistWindow instance."""
        if window in self.windows:
            self.windows.remove(window)

    def get_active_window(self):
        """Return the currently focused PlistWindow, or None."""
        active = self.app.activeWindow()
        if active is not None and active in self.windows:
            return active
        # Fall back to the last window in the list
        if self.windows:
            return self.windows[-1]
        return None

    # ------------------------------------------------------------------
    # Dark mode detection
    # ------------------------------------------------------------------

    def get_dark(self):
        """Detect whether the system is in dark mode."""
        if os.name == "nt":
            try:
                p = subprocess.Popen(
                    [
                        "reg",
                        "query",
                        "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
                        "/v",
                        "AppsUseLightTheme",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                c = p.communicate()
                return c[0].decode("utf-8", "ignore").strip().lower().split(" ")[-1] in ("", "0x0")
            except Exception:
                return False
        elif sys.platform != "darwin":
            return True  # Default to dark mode on Linux
        # macOS
        try:
            p = subprocess.Popen(
                ["defaults", "read", "-g", "AppleInterfaceStyle"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            c = p.communicate()
            return c[0].decode("utf-8", "ignore").strip().lower() == "dark"
        except Exception:
            return False

    def _check_dark_mode(self):
        """Periodic callback to detect dark/light mode changes."""
        check_dark = self.get_dark()
        if check_dark != self.use_dark:
            self.use_dark = check_dark
            # Notify all open windows about the mode change
            for window in list(self.windows):
                try:
                    window.update_colors()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Color helpers
    # ------------------------------------------------------------------

    def text_color(self, hex_color, invert=False):
        """Compute black or white text color based on background luminance."""
        hex_color = hex_color.lower()
        if hex_color.startswith("0x"):
            hex_color = hex_color[2:]
        if hex_color.startswith("#"):
            hex_color = hex_color[1:]
        # Validate hex
        if len(hex_color) != 6 or not all(c in "0123456789abcdef" for c in hex_color):
            return "white" if invert else "black"
        r = float(int(hex_color[0:2], 16))
        g = float(int(hex_color[2:4], 16))
        b = float(int(hex_color[4:6], 16))
        luminance_high = (r * 0.299 + g * 0.587 + b * 0.114) > 186
        if luminance_high:
            return "white" if invert else "black"
        return "black" if invert else "white"

    # ------------------------------------------------------------------
    # Version comparison
    # ------------------------------------------------------------------

    def compare_version(self, v1, v2):
        """Compare two dotted version strings.

        Returns True if v1 > v2, None if equal, False if v1 < v2.
        """
        if not all(isinstance(x, str) for x in (v1, v2)):
            return False
        v1_seg = v1.split(".")
        v2_seg = v2.split(".")
        # Pad with 0s to ensure common length
        v1_seg += ["0"] * (len(v2_seg) - len(v1_seg))
        v2_seg += ["0"] * (len(v1_seg) - len(v2_seg))
        for i in range(len(v1_seg)):
            a, b = v1_seg[i], v2_seg[i]
            try:
                a = int("".join(x for x in a if x.isdigit()))
            except Exception:
                a = 0
            try:
                b = int("".join(x for x in b if x.isdigit()))
            except Exception:
                b = 0
            if a > b:
                return True
            if a < b:
                return False
        return None

    # ------------------------------------------------------------------
    # Update checking
    # ------------------------------------------------------------------

    def check_for_updates(self, user_initiated=False):
        if self.is_checking_for_updates:
            if user_initiated:
                QMessageBox.critical(
                    self.get_active_window(),
                    "Already Checking For Updates",
                    "An update check is already in progress.  If you consistently get this "
                    "error when manually checking for updates - it may indicate a network issue.",
                )
            return
        self.is_checking_for_updates = True
        self._update_worker = UpdateCheckWorker(version_url=self.version_url, user_initiated=user_initiated)
        self._update_worker.finished.connect(self._on_update_check_finished)
        self._update_worker.start()

    def _on_update_check_finished(self, output_dict):
        self.is_checking_for_updates = False
        user_initiated = output_dict.get("user_initiated", False)

        # Check for errors
        if "exception" in output_dict or "error" in output_dict:
            error = output_dict.get("error", "An Error Occurred Checking For Updates")
            excep = output_dict.get("exception", "Something went wrong when checking for updates.")
            if user_initiated:
                QMessageBox.critical(self.get_active_window(), error, excep)
            return

        # Parse the output
        version_dict = output_dict.get("json", {})
        if not version_dict.get("version"):
            if user_initiated:
                QMessageBox.critical(
                    self.get_active_window(),
                    "An Error Occurred Checking For Updates",
                    "Data returned was malformed or nonexistent.",
                )
            return

        check_version = str(version_dict["version"]).lower()
        our_version = str(self.version.get("version", "0.0.0")).lower()
        notify_once = self.settings.get("notify_once_per_version", True)
        last_version = str(self.settings.get("last_version_checked", "0.0.0")).lower()

        if self.compare_version(check_version, our_version) is True:
            if notify_once and last_version == check_version and not user_initiated:
                return
            self.settings["last_version_checked"] = check_version
            result = QMessageBox.question(
                self.get_active_window(),
                "New qtProperTree Version Available",
                "Version {} is available (currently on {}).\n\n"
                "What's new in {}:\n{}\n\n"
                "Visit qtProperTree's github repo now?".format(
                    check_version, our_version, check_version, version_dict.get("changes", "No changes listed.")
                ),
                QMessageBox.Yes | QMessageBox.No,
            )
            if result == QMessageBox.Yes:
                webbrowser.open(self.repo_url)
        elif user_initiated:
            QMessageBox.information(
                self.get_active_window(),
                "No Updates Available",
                "You are currently running the latest version of qtProperTree ({}).".format(our_version),
            )

    # ------------------------------------------------------------------
    # Tex download
    # ------------------------------------------------------------------

    def get_latest_tex(self):
        self._tex_worker = TexDownloadWorker(tex_url=self.tex_url, tex_path=self.get_best_tex_path())
        self._tex_worker.finished.connect(self._on_tex_download_finished)
        self._tex_worker.start()

    def _on_tex_download_finished(self, output_dict):
        if "exception" in output_dict or "error" in output_dict:
            error = output_dict.get("error", "An Error Occurred Downloading Configuration.tex")
            excep = output_dict.get("exception", "Something went wrong when getting the latest Configuration.tex.")
            QMessageBox.critical(self.get_active_window(), error, excep)
        else:
            tex_path = self.get_best_tex_path()
            if os.path.isfile(tex_path):
                version = self.get_tex_version(file_path=tex_path)
                if not version:
                    QMessageBox.critical(
                        self.get_active_window(),
                        "An Error Occurred Downloading Configuration.tex",
                        "Something went wrong when getting the latest Configuration.tex.",
                    )
                else:
                    QMessageBox.information(
                        self.get_active_window(),
                        "Updated Configuration.tex",
                        "Configuration.tex ({}) saved to:\n\n{}".format(version, tex_path),
                    )

    # ------------------------------------------------------------------
    # Tex path / version helpers
    # ------------------------------------------------------------------

    def get_best_tex_path(self):
        pt_path = self.base_dir
        config_tex_paths = [os.path.join(pt_path, "Configuration.tex")]
        pt_path_parts = pt_path.split(os.sep)
        if (
            len(pt_path_parts) >= 3
            and pt_path_parts[-2:] == ["Contents", "MacOS"]
            and pt_path_parts[-3].lower().endswith(".app")
        ):
            temp_path = pt_path
            for _ in range(3):
                temp_path = os.path.dirname(temp_path)
                config_tex_paths.append(os.path.join(temp_path, "Configuration.tex"))
        for path in config_tex_paths:
            if os.path.isfile(path):
                return path
        if config_tex_paths:
            return config_tex_paths[0]
        return None

    def get_tex_version(self, file_path=None):
        file_path = file_path or self.get_best_tex_path()
        if not file_path or not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, "r") as f:
                t = f.read()
            for line in t.split("\n"):
                line = line.strip().lower()
                if line.startswith("reference manual (") and line.endswith(")"):
                    return line.split("(")[-1].split(")")[0]
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Window management methods
    # ------------------------------------------------------------------

    def new_plist(self, event=None):
        if self.creating_window:
            return None
        self.creating_window = True
        try:
            from propertree.qt_plist_window import PlistWindow

            title = self._get_unique_title(title="Untitled.plist")
            window = PlistWindow(self)
            self.add_window(window)
            window.open_plist(title, {})
            window.current_plist = None  # Ensure it is initialized as new
            window.show()
            window.raise_()
            window.activateWindow()
        finally:
            self.creating_window = False
        return window

    def open_plist(self, event=None):
        path, _ = QFileDialog.getOpenFileName(
            self.get_active_window(), "Select plist file", "", "Plist Files (*.plist);;All Files (*)"
        )
        if not path:
            return None
        path = os.path.abspath(os.path.expanduser(path))
        return self.pre_open_with_path(path)

    def pre_open_with_path(self, path, current_window=None):
        if not path:
            return None
        path = os.path.abspath(os.path.expanduser(path))
        # Check if already open
        for window in list(self.windows):
            if hasattr(window, "current_plist") and window.current_plist == path:
                window.show()
                window.raise_()
                window.activateWindow()
                try:
                    window.reload_from_disk(None)
                except Exception:
                    pass
                return None
        # If we have a single fresh/untitled window, reuse it
        if current_window is None and len(self.windows) == 1:
            w = self.windows[0]
            if w == self.start_window and not getattr(w, "edited", True) and getattr(w, "current_plist", "x") is None:
                current_window = w
        return self.open_plist_with_path(None, path, current_window)

    def open_plist_with_path(self, event=None, path=None, current_window=None):
        if not path:
            return None
        path = os.path.abspath(os.path.expanduser(path))
        # Try to load the plist
        try:
            with open(path, "rb") as f:
                plist_type = "Binary" if plist._is_binary(f) else "XML"
                plist_data = plist.load(f, dict_type=dict if self.settings.get("sort_dict", False) else OrderedDict)
        except Exception as e:
            QMessageBox.critical(
                self.get_active_window(), "An Error Occurred While Opening {}".format(os.path.basename(path)), str(e)
            )
            return None

        if not current_window:
            from propertree.qt_plist_window import PlistWindow

            current_window = PlistWindow(self)
            self.add_window(current_window)

        current_window.open_plist(
            path, plist_data, plist_type=plist_type, auto_expand=self.settings.get("expand_all_items_on_open", True)
        )
        current_window.show()
        current_window.raise_()
        current_window.activateWindow()
        # Add to recent files
        self.add_recent(path)
        return current_window

    def duplicate_plist(self, event=None):
        if self.creating_window:
            return
        self.creating_window = True
        try:
            window = self.get_active_window()
            if window is None:
                return
            from propertree.qt_plist_window import PlistWindow

            title = self._get_unique_title(title="Untitled.plist")
            plist_data = window.nodes_to_values()
            new_window = PlistWindow(self)
            self.add_window(new_window)
            new_window.open_plist(
                None, plist_data, auto_expand=self.settings.get("expand_all_items_on_open", True), title=title
            )
            new_window.show()
            new_window.raise_()
            new_window.activateWindow()
        finally:
            self.creating_window = False

    def save_plist(self, event=None):
        window = self.get_active_window()
        if window is None:
            return
        if window.save_plist(event):
            self.add_recent(window.current_plist)

    def save_plist_as(self, event=None):
        window = self.get_active_window()
        if window is None:
            return
        if window.save_plist_as(event):
            self.add_recent(window.current_plist)

    def undo(self, event=None):
        window = self.get_active_window()
        if window is None:
            return
        window.reundo(event)

    def redo(self, event=None):
        window = self.get_active_window()
        if window is None:
            return
        window.reundo(event, False)

    def close_window(self, window=None):
        if window is None:
            window = self.get_active_window()
        if window is None:
            return
        window.close()

    def quit(self, event=None):
        if self.is_quitting:
            return
        self.is_quitting = True
        # Get windows with unsaved changes
        unsaved = [w for w in self.windows if getattr(w, "edited", False)]
        ask_to_save = True
        if len(unsaved) > 1:
            answer = QMessageBox.question(
                self.get_active_window(),
                "Unsaved Changes",
                "You have {:,} document{} with unsaved changes.\n"
                "Would you like to review?\n"
                "(If you don't review, all unsaved changes will be lost)".format(
                    len(unsaved), "" if len(unsaved) == 1 else "s"
                ),
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if answer == QMessageBox.Cancel:
                self.is_quitting = False
                return
            ask_to_save = answer == QMessageBox.Yes

        if ask_to_save:
            for window in list(self.windows)[::-1]:
                if not getattr(window, "edited", False):
                    continue
                window.raise_()
                window.activateWindow()
                if not window.close_window(check_saving=ask_to_save, check_close=False):
                    self.is_quitting = False
                    return

        # Save settings before quitting
        self.save_settings()
        self.app.quit()

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def _clipboard_append(self, clipboard_string=None):
        """Copy a string to the system clipboard via subprocess."""
        if clipboard_string is None:
            clipboard_string = ""
        # Also set via Qt clipboard
        clipboard = self.app.clipboard()
        if clipboard is not None:
            clipboard.setText(clipboard_string)
        # Mirror to system clipboard via native commands
        if os.name == "nt":
            args_list = [["clip"]]
        elif sys.platform == "darwin":
            args_list = [["pbcopy"]]
        else:
            args_list = [["xclip", "-sel", "c"], ["xsel", "-ib"]]

        for args in args_list:
            try:
                proc = subprocess.Popen(
                    args, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                )
            except Exception:
                continue
            proc.stdin.write(clipboard_string.encode("utf-8"))
            proc.stdin.flush()
            proc.stdin.close()
            break

    # ------------------------------------------------------------------
    # Recent files management
    # ------------------------------------------------------------------

    def add_recent(self, recent):
        recent = os.path.normpath(recent)
        recents = [x for x in self.settings.get("open_recent", []) if x != recent]
        recents.insert(0, recent)
        recent_max = self.settings.get("recent_max", 10)
        recents = recents[:recent_max]
        self.settings["open_recent"] = recents

    def rem_recent(self, recent):
        recent = os.path.normpath(recent)
        recents = [x for x in self.settings.get("open_recent", []) if x != recent]
        self.settings["open_recent"] = recents

    def clear_recents(self):
        self.settings.pop("open_recent", None)

    def open_recent(self, path=None):
        if path is None:
            paths = self.settings.get("open_recent", [])
            if paths:
                path = paths[0]
        if path is None:
            return
        path = os.path.normpath(path)
        if not (os.path.exists(path) and os.path.isfile(path)):
            QMessageBox.critical(
                self.get_active_window(),
                "An Error Occurred While Opening {}".format(os.path.basename(path)),
                "The path '{}' does not exist.".format(path),
            )
            return
        return self.pre_open_with_path(path)

    def normpath_recents(self):
        normalized = [os.path.normpath(x) for x in self.settings.get("open_recent", [])]
        new_paths = []
        for path in normalized:
            if path not in new_paths:
                new_paths.append(path)
        self.settings["open_recent"] = new_paths

    # ------------------------------------------------------------------
    # Unique title generation
    # ------------------------------------------------------------------

    def _get_unique_title(self, title="Untitled.plist", suffix=""):
        if "." in title:
            final_title = ".".join(title.split(".")[:-1])
            ext = "." + title.split(".")[-1]
        else:
            final_title = title
            ext = ""
        titles = set()
        for w in self.windows:
            t = getattr(w, "windowTitle", lambda: "")()
            if t:
                titles.add(t.lower())
        number = 0
        while True:
            temp = "{}{}{}{}".format(final_title, suffix, "" if number == 0 else "-" + str(number), ext)
            temp_edit = temp + " - edited"
            if temp.lower() not in titles and temp_edit.lower() not in titles:
                return temp
            number += 1

    # ------------------------------------------------------------------
    # check_open - opens plists passed as args, or creates new
    # ------------------------------------------------------------------

    def check_open(self, plists=None):
        if plists is None:
            plists = []
        if self.is_opening:
            QTimer.singleShot(5, lambda: self.check_open(plists))
            return
        self.is_opening = True
        try:
            plists = [x for x in plists if not self.regexp.search(x)]
            if isinstance(plists, list) and len(plists):
                at_least_one = False
                for p in set(plists):
                    window = self.pre_open_with_path(p)
                    if not window:
                        continue
                    at_least_one = True
                    if self.start_window is None:
                        self.start_window = window
                if not at_least_one:
                    if not self.windows:
                        self.start_window = self.new_plist()
            elif not self.windows:
                self.start_window = self.new_plist()
        except Exception as e:
            QMessageBox.critical(self.get_active_window(), "Error in check_open() function", repr(e))
        self.is_opening = False

    # ------------------------------------------------------------------
    # Snapshot data helpers
    # ------------------------------------------------------------------

    def get_snapshot_data(self):
        return self.snapshot_data

    def get_version(self):
        return self.version

    # ------------------------------------------------------------------
    # Forwarding methods - get active window and delegate
    # ------------------------------------------------------------------

    def strip_comments(self, event=None):
        window = self.get_active_window()
        if window is not None:
            window.strip_comments(event)

    def strip_disabled(self, event=None):
        window = self.get_active_window()
        if window is not None:
            window.strip_disabled(event)

    def strip_whitespace(self, event=None, keys=False, values=False):
        window = self.get_active_window()
        if window is not None:
            window.strip_whitespace(event, keys=keys, values=values)

    def hide_show_find(self, event=None):
        window = self.get_active_window()
        if window is not None:
            window.hide_show_find(event)

    def hide_show_type(self, event=None):
        window = self.get_active_window()
        if window is not None:
            window.hide_show_type(event)

    def oc_snapshot(self, event=None, clean=False):
        window = self.get_active_window()
        if window is not None:
            window.oc_snapshot(event, clean)

    def oc_clean_snapshot(self, event=None):
        self.oc_snapshot(event, True)

    def reload_from_disk(self, event=None):
        window = self.get_active_window()
        if window is not None:
            window.reload_from_disk(event)
