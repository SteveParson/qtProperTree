import json
import os
import subprocess
import sys

from PySide6.QtCore import QThread, Signal


class UpdateCheckWorker(QThread):
    """Background worker to check for qtProperTree updates."""

    finished = Signal(dict)

    def __init__(self, version_url=None, user_initiated=False, parent=None):
        super().__init__(parent)
        self.version_url = version_url
        self.user_initiated = user_initiated

    def run(self):
        try:
            args = [sys.executable]
            file_path = os.path.join(
                os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "propertree", "update_check.py"
            )
            if not os.path.exists(file_path):
                self.finished.emit(
                    {
                        "exception": "Could not locate update_check.py.",
                        "error": "Missing Required Files",
                        "user_initiated": self.user_initiated,
                    }
                )
                return
            args.append(file_path)
            if self.version_url:
                args.extend(["-u", self.version_url])
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            o, _ = proc.communicate()
            o = o.decode("utf-8")
            try:
                json_data = json.loads(o)
                json_data["user_initiated"] = self.user_initiated
            except Exception:
                self.finished.emit(
                    {
                        "exception": "Could not serialize returned JSON data.",
                        "error": "An Error Occurred Checking For Updates",
                        "user_initiated": self.user_initiated,
                    }
                )
                return
            self.finished.emit(json_data)
        except Exception as e:
            self.finished.emit(
                {
                    "exception": str(e),
                    "error": "An Error Occurred Checking For Updates",
                    "user_initiated": self.user_initiated,
                }
            )


class TexDownloadWorker(QThread):
    """Background worker to download Configuration.tex."""

    finished = Signal(dict)

    def __init__(self, tex_url=None, tex_path=None, parent=None):
        super().__init__(parent)
        self.tex_url = tex_url
        self.tex_path = tex_path

    def run(self):
        try:
            args = [sys.executable]
            file_path = os.path.join(
                os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "propertree", "update_check.py"
            )
            if not os.path.exists(file_path):
                self.finished.emit(
                    {"exception": "Could not locate update_check.py.", "error": "Missing Required Files"}
                )
                return
            args.extend([file_path, "-m", "tex", "-t", self.tex_path])
            if self.tex_url:
                args.extend(["-u", self.tex_url])
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            o, _ = proc.communicate()
            o = o.decode("utf-8")
            try:
                json_data = json.loads(o)
            except Exception:
                self.finished.emit(
                    {
                        "exception": "Could not serialize returned JSON data.",
                        "error": "An Error Occurred Downloading Configuration.tex",
                    }
                )
                return
            self.finished.emit(json_data)
        except Exception as e:
            self.finished.emit({"exception": str(e), "error": "An Error Occurred Downloading Configuration.tex"})
