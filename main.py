
import os
import sys
import base64
import time
import socket
import serial
import serial.tools.list_ports
import sqlite3
import platform
import re
import subprocess
import shutil
import ipaddress
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QProcess, QSize, QRect, QPoint
from PySide6.QtGui import QIcon, QPixmap, QFont, QColor, QTextCursor
from PySide6.QtNetwork import QTcpSocket
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QFrame,
    QVBoxLayout, QHBoxLayout, QGridLayout, QProgressBar, QStackedWidget,
    QLineEdit, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QSpinBox, QCheckBox, QHeaderView, QDialog, QFormLayout, QTextEdit, QPlainTextEdit, QComboBox, QDialogButtonBox, QLayout
, QPlainTextEdit)

APP_NAME = "N-Console"
APP_VERSION = "22.0.3"
DEVELOPER = "Mr. Neeraj Kumar (IT System Administration)"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)

def _asset_candidates(filename):
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "assets", filename))
    candidates.append(os.path.join(BASE_DIR, "assets", filename))
    candidates.append(os.path.join(os.path.dirname(sys.executable), "assets", filename))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", filename))
    # preserve order while removing duplicates
    return list(dict.fromkeys(candidates))

def asset_path(filename):
    for candidate in _asset_candidates(filename):
        if os.path.isfile(candidate):
            return candidate
    return _asset_candidates(filename)[0]

ASSET_DIR = os.path.join(BASE_DIR, "assets")
ICON_PATH = asset_path("n_console_icon.png")
ILLUSTRATION_PATH = asset_path("home_illustration.png")
ICON_ICO_PATH = asset_path("n_console_icon.ico")
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", BASE_DIR), "N-Console")
DB_PATH = os.path.join(DATA_DIR, "nconsole_history.db")


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)


class HistoryDB:
    def __init__(self):
        ensure_dirs()
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.lock = threading.Lock()
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                device TEXT NOT NULL,
                ip TEXT NOT NULL,
                protocol TEXT NOT NULL,
                username TEXT,
                status TEXT NOT NULL,
                duration TEXT
            )
        """)
        self.conn.commit()

    def add(self, device, ip, protocol, username="", status="Launched", duration=""):
        with self.lock:
            self.conn.execute(
                "INSERT INTO history(timestamp,device,ip,protocol,username,status,duration)"
                " VALUES(?,?,?,?,?,?,?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 device, ip, protocol, username, status, duration)
            )
            self.conn.commit()

    def rows(self):
        with self.lock:
            return self.conn.execute(
                "SELECT timestamp,device,ip,protocol,username,status,duration "
                "FROM history ORDER BY id DESC"
            ).fetchall()

    def clear(self):
        with self.lock:
            self.conn.execute("DELETE FROM history")
            self.conn.commit()



def _run_hidden(*args, **kwargs):
    """Run a background OS command without creating a Windows console window."""
    if platform.system().lower() == "windows":
        kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
        startupinfo = kwargs.get("startupinfo")
        if startupinfo is None:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = startupinfo
    return subprocess.run(*args, **kwargs)


def run_client(protocol, host, port, username):
    if protocol == "RDP":
        if platform.system().lower() != "windows":
            raise RuntimeError("Windows Remote Desktop is available only on Windows.")
        if not shutil.which("mstsc.exe"):
            raise RuntimeError("mstsc.exe is not available.")
        return subprocess.Popen(["mstsc.exe", f"/v:{host}:{port}"])
    if protocol == "SSH":
        target = f"{username}@{host}" if username else host
        if not shutil.which("ssh.exe"):
            raise RuntimeError("OpenSSH client is not installed. Use N-Console's built-in SSH page.")
        return subprocess.Popen(["ssh.exe", "-p", str(port), target])
    if protocol == "Telnet":
        raise RuntimeError("Use N-Console's built-in Telnet terminal.")
    raise RuntimeError("Unsupported protocol.")


def load_pixmap(filename, fallback_width=0, fallback_height=0):
    """Load a packaged asset reliably in source, PyInstaller, and Inno installs."""
    path = asset_path(filename)
    pixmap = QPixmap(path)
    if not pixmap.isNull():
        return pixmap

    # Last-resort lookup next to the executable and current working directory.
    for candidate in (
        os.path.join(os.getcwd(), "assets", filename),
        os.path.join(os.path.dirname(sys.executable), filename),
    ):
        pixmap = QPixmap(candidate)
        if not pixmap.isNull():
            return pixmap

    return QPixmap()


class SplashScreen(QWidget):
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(ICON_PATH))
        self.setStyleSheet("background:#f6fbff;")
        self.started = time.monotonic()

        root = QVBoxLayout(self)
        root.setContentsMargins(55, 42, 55, 34)
        root.setSpacing(12)

        top = QHBoxLayout()
        icon = QLabel()
        icon.setFixedSize(96, 96)
        icon.setAlignment(Qt.AlignCenter)
        icon_pixmap = load_pixmap("n_console_icon.png")
        if not icon_pixmap.isNull():
            icon.setPixmap(icon_pixmap.scaled(86, 86, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon.setText("N")
            icon.setStyleSheet("color:#0b76b8;font-size:44px;font-weight:800;border:3px solid #0b76b8;border-radius:43px;")
        top.addWidget(icon)

        brand = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setFont(QFont("Segoe UI", 32, QFont.Bold))
        title.setStyleSheet("color:#123a56;")
        subtitle = QLabel("Network & Remote Administration Console")
        subtitle.setStyleSheet("color:#5b7485;font-size:13px;")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        top.addLayout(brand)
        top.addStretch()
        root.addLayout(top)

        root.addStretch()

        art = QLabel()
        art.setAlignment(Qt.AlignCenter)
        art.setMinimumSize(520, 300)
        art_pixmap = load_pixmap("home_illustration.png")
        if not art_pixmap.isNull():
            art.setPixmap(art_pixmap.scaled(
                1050, 590, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        else:
            art.setText("N-Console\nNetwork & Remote Administration Console")
            art.setStyleSheet("color:#1769c2;font-size:24px;font-weight:700;")
        root.addWidget(art, 0, Qt.AlignCenter)

        root.addStretch()

        self.status = QLabel("Initializing N-Console...")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("color:#48687a;font-size:11px;")
        root.addWidget(self.status)

        self.progress = QProgressBar()
        self.progress.setRange(1, 100)
        self.progress.setValue(1)
        self.progress.setFormat("%p%  •  Loading N-Console")
        self.progress.setFixedHeight(17)
        root.addWidget(self.progress)

        version = QLabel(f"N-Console {APP_VERSION}")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color:#1769c2;font-size:10px;font-weight:700;")
        root.addWidget(version)

        dev = QLabel(f"Developer Name:- {DEVELOPER}")
        dev.setAlignment(Qt.AlignCenter)
        dev.setStyleSheet("color:#29485b;font-size:10px;font-weight:700;")
        root.addWidget(dev)

        self.value = 1
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(40)

    def showEvent(self, event):
        super().showEvent(event)
        self.showFullScreen()

    def tick(self):
        self.value = min(100, self.value + 1)
        self.progress.setValue(self.value)
        if self.value < 20:
            self.status.setText("Loading application components...")
        elif self.value < 40:
            self.status.setText("Loading network modules...")
        elif self.value < 60:
            self.status.setText("Preparing remote access...")
        elif self.value < 80:
            self.status.setText("Preparing scanner and reporting...")
        elif self.value < 98:
            self.status.setText("Loading history database...")
        else:
            self.status.setText("Starting N-Console...")
        # Never close before 8 seconds.
        if self.value >= 100:
            elapsed = time.monotonic() - self.started
            delay = max(0, int((8.0 - elapsed) * 1000))
            self.timer.stop()
            QTimer.singleShot(delay, self.finished.emit)


class StatCard(QFrame):
    def __init__(self, title, value, accent):
        super().__init__()
        self.setObjectName("statCard")
        self.setStyleSheet(
            f"QFrame#statCard{{background:#ffffff;border:1px solid #d9e7f1;"
            f"border-left:5px solid {accent};border-radius:16px;}}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("statTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("statValue")
        self.value_label.setStyleSheet(
            f"color:{accent};font-size:24px;font-weight:800;border:none;"
        )
        lay.addWidget(self.title_label)
        lay.addWidget(self.value_label)

    def set_value(self, value):
        self.value_label.setText(str(value))


class AnimatedReadyCard(StatCard):
    def __init__(self, title, accent):
        super().__init__(title, "Ready", accent)
        self._dots = 0
        self._base = "Ready"
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(650)

    def animate(self):
        self._dots = (self._dots + 1) % 4
        self.value_label.setText(self._base + "." * self._dots)

class TerminalWidget(QPlainTextEdit):
    """PuTTY-style terminal surface with protected output, history and password masking."""

    command_entered = Signal(str)
    space_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._input_start = 0
        self._history = []
        self._history_index = -1
        self._saved_current = ""
        self._secret_mode = False
        self._secret_value = ""
        self._input_enabled = True
        self.setReadOnly(False)
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setStyleSheet("""
            QPlainTextEdit {
                background:#071a25;
                color:#e8f5fb;
                border:1px solid #315465;
                border-radius:8px;
                padding:7px;
                font-family:Consolas,"Cascadia Mono","Courier New";
                font-size:10pt;
                selection-background-color:#1f5f85;
            }
        """)

    def begin_input(self):
        self._input_start = len(self.toPlainText())
        self._history_index = -1
        self._saved_current = ""
        self._secret_value = ""
        self.moveCursor(QTextCursor.End)
        self.ensureCursorVisible()

    def set_input_enabled(self, enabled):
        self._input_enabled = bool(enabled)
        self.moveCursor(QTextCursor.End)
        self.ensureCursorVisible()

    def set_secret_mode(self, enabled):
        enabled = bool(enabled)
        if enabled == self._secret_mode:
            return
        current = self.input_text()
        self._secret_mode = enabled
        if enabled:
            self._secret_value = current
        else:
            self._secret_value = ""
        self._replace_input(current)

    def input_text(self):
        if self._secret_mode:
            return self._secret_value
        text = self.toPlainText()
        return text[self._input_start:]

    def _visible_input(self):
        if self._secret_mode:
            return "•" * len(self._secret_value)
        return self.input_text()

    def _replace_input(self, value):
        if self._secret_mode:
            self._secret_value = value
            visible = "•" * len(value)
        else:
            visible = value

        cursor = self.textCursor()
        cursor.setPosition(self._input_start)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(visible)
        self.setTextCursor(cursor)
        self.moveCursor(QTextCursor.End)
        self.ensureCursorVisible()

    def append_output(self, value):
        """Append device output without destroying an active command/password input."""
        if not value:
            return
        # Network-device CRLF is a line ending. A lone CR is also normalized so
        # prompts cannot overwrite/edit the preceding line in QPlainTextEdit.
        value = value.replace("\r\n", "\n").replace("\r", "\n")

        old_input = self.input_text()
        current = self.toPlainText()
        protected = current[:self._input_start]
        new_text = protected + value
        visible_input = "•" * len(old_input) if self._secret_mode else old_input
        new_text += visible_input

        self.setPlainText(new_text)
        self._input_start = len(protected) + len(value)
        self.moveCursor(QTextCursor.End)
        self.ensureCursorVisible()

    def _history_up(self):
        if self._secret_mode or not self._history or not self._input_enabled:
            return
        current = self.input_text()
        if self._history_index == -1:
            self._saved_current = current
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        self._replace_input(self._history[self._history_index])

    def _history_down(self):
        if self._secret_mode or not self._history or self._history_index == -1 or not self._input_enabled:
            return
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._replace_input(self._history[self._history_index])
        else:
            self._history_index = -1
            self._replace_input(self._saved_current)

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key_C and (mods & Qt.ControlModifier):
            self.command_entered.emit("\x03")
            event.accept()
            return

        if key == Qt.Key_U and (mods & Qt.ControlModifier):
            if self._input_enabled:
                self._replace_input("")
            event.accept()
            return

        if not self._input_enabled:
            # Output is still selectable/copyable, but no new command can be
            # typed while the remote device is producing a command result.
            if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right,
                       Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown):
                super().keyPressEvent(event)
            else:
                event.accept()
            return

        if key in (Qt.Key_Return, Qt.Key_Enter):
            command = self.input_text().rstrip("\r\n")
            if command:
                if not self._secret_mode:
                    if not self._history or self._history[-1] != command:
                        self._history.append(command)
                        if len(self._history) > 100:
                            self._history = self._history[-100:]
            # Remove local echo before sending. The network device supplies its
            # own echo when echo is enabled, so the command appears only once.
            self._replace_input("")
            self._history_index = -1
            self._saved_current = ""
            self.command_entered.emit(command)
            event.accept()
            return

        if key == Qt.Key_Up:
            self._history_up()
            event.accept()
            return

        if key == Qt.Key_Down:
            self._history_down()
            event.accept()
            return

        if self._secret_mode:
            if key == Qt.Key_Backspace:
                if self._secret_value:
                    self._secret_value = self._secret_value[:-1]
                    self._replace_input(self._secret_value)
                event.accept()
                return
            if key == Qt.Key_Delete:
                event.accept()
                return
            if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End):
                event.accept()
                return
            text = event.text()
            if text and not (mods & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)):
                self._secret_value += text
                self._replace_input(self._secret_value)
            event.accept()
            return

        # Never allow mouse-selected/history text to be overwritten. If the
        # cursor is in protected output, typing starts at the live input line.
        cursor = self.textCursor()
        if cursor.position() < self._input_start or cursor.anchor() < self._input_start:
            cursor.clearSelection()
            cursor.setPosition(len(self.toPlainText()))
            self.setTextCursor(cursor)

        if key == Qt.Key_Backspace:
            if self.textCursor().position() <= self._input_start:
                event.accept()
                return
            super().keyPressEvent(event)
            self._clamp_cursor()
            return

        if key == Qt.Key_Delete:
            cursor = self.textCursor()
            if cursor.position() < self._input_start:
                event.accept()
                return

        if key == Qt.Key_Home:
            cursor = self.textCursor()
            cursor.setPosition(self._input_start)
            self.setTextCursor(cursor)
            event.accept()
            return

        if key == Qt.Key_Left:
            cursor = self.textCursor()
            if cursor.position() <= self._input_start:
                event.accept()
                return

        super().keyPressEvent(event)
        self._clamp_cursor()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        cursor = self.textCursor()
        if cursor.position() < self._input_start:
            cursor.clearSelection()
            cursor.setPosition(len(self.toPlainText()))
            self.setTextCursor(cursor)

    def _clamp_cursor(self):
        cursor = self.textCursor()
        if cursor.position() < self._input_start:
            cursor.setPosition(self._input_start)
            self.setTextCursor(cursor)


class SerialPage(QWidget):
    """Physical USB/COM serial console for switches and routers."""

    output_received = Signal(str)
    session_closed = Signal()
    session_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.ser = None
        self.reader_thread = None
        self.reader_stop = threading.Event()
        self.connected = False
        self._display_buffer = ""
        self._display_timer = QTimer(self)
        self._display_timer.setInterval(45)
        self._display_timer.timeout.connect(self._flush_display_buffer)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(5)

        header = QHBoxLayout()
        title = QLabel("Serial Console")
        title.setStyleSheet("font-size:18px;font-weight:750;color:#0f3d5e;")
        self.state = QLabel("Disconnected")
        self.state.setStyleSheet("color:#d9534f;font-weight:700;")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.state)
        root.addLayout(header)

        controls = QHBoxLayout()
        controls.setSpacing(6)

        controls.addWidget(QLabel("COM Port"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(110)
        controls.addWidget(self.port_combo)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_ports)
        controls.addWidget(refresh)

        controls.addWidget(QLabel("Baud"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.baud_combo.setCurrentText("9600")
        controls.addWidget(self.baud_combo)

        controls.addWidget(QLabel("Data"))
        self.data_combo = QComboBox()
        self.data_combo.addItems(["8", "7"])
        controls.addWidget(self.data_combo)

        controls.addWidget(QLabel("Parity"))
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["None", "Even", "Odd"])
        controls.addWidget(self.parity_combo)

        controls.addWidget(QLabel("Stop"))
        self.stop_combo = QComboBox()
        self.stop_combo.addItems(["1", "2"])
        controls.addWidget(self.stop_combo)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("primaryButton")
        self.connect_btn.clicked.connect(self.connect_serial)
        controls.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.disconnect)
        self.disconnect_btn.setEnabled(False)
        controls.addWidget(self.disconnect_btn)

        root.addLayout(controls)

        # One terminal surface: typing and command execution happen here.
        self.terminal = TerminalWidget()
        self.terminal.command_entered.connect(self._terminal_command)
        root.addWidget(self.terminal, 1)

        self.output_received.connect(self._queue_output)
        self.session_closed.connect(self._remote_disconnect)
        self.session_error.connect(self._show_error)

        self.refresh_ports()
        self.terminal.setFocus()

    def refresh_ports(self):
        current = self.port_combo.currentText()
        self.port_combo.clear()
        try:
            ports = list(serial.tools.list_ports.comports())
            names = [p.device for p in ports]
        except Exception:
            names = []
        if names:
            self.port_combo.addItems(names)
            if current in names:
                self.port_combo.setCurrentText(current)
        else:
            self.port_combo.addItem("No COM port detected")

    def connect_serial(self):
        if self.connected:
            return

        port = self.port_combo.currentText()
        if not port or port == "No COM port detected":
            QMessageBox.warning(
                self, "Serial Console",
                "No COM port detected. Connect the USB-to-Serial console cable and click Refresh."
            )
            return

        parity_map = {
            "None": serial.PARITY_NONE,
            "Even": serial.PARITY_EVEN,
            "Odd": serial.PARITY_ODD,
        }
        data_bits = serial.EIGHTBITS if self.data_combo.currentText() == "8" else serial.SEVENBITS
        stop_bits = serial.STOPBITS_ONE if self.stop_combo.currentText() == "1" else serial.STOPBITS_TWO

        self.terminal.clear()
        self.terminal.begin_input()
        self.terminal.append_output(
            f"Opening {port} @ {self.baud_combo.currentText()} baud...\n"
        )

        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=int(self.baud_combo.currentText()),
                bytesize=data_bits,
                parity=parity_map[self.parity_combo.currentText()],
                stopbits=stop_bits,
                timeout=0.10,
                write_timeout=2,
            )
            self.connected = True
            self.reader_stop.clear()
            self._display_timer.start()

            self.state.setText(f"Connected • {port}")
            self.state.setStyleSheet("color:#0a9f67;font-weight:700;")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)

            self.reader_thread = threading.Thread(
                target=self._reader_loop, daemon=True
            )
            self.reader_thread.start()

            # Wake most switch console sessions and show their prompt.
            self._send_bytes(b"\r\n")
            self.terminal.begin_input()

        except Exception as exc:
            self.ser = None
            self.connected = False
            self._display_timer.stop()
            self.state.setText("Connection Failed")
            self.state.setStyleSheet("color:#d9534f;font-weight:700;")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.terminal.append_output(f"Serial connection error: {exc}\n")
            self.terminal.begin_input()

    def _reader_loop(self):
        while not self.reader_stop.is_set():
            ser_obj = self.ser
            if not ser_obj:
                break
            try:
                waiting = ser_obj.in_waiting
                if waiting:
                    data = ser_obj.read(min(waiting, 16384))
                    if data:
                        self.output_received.emit(
                            data.decode("utf-8", errors="replace")
                        )
                else:
                    time.sleep(0.01)
            except Exception as exc:
                if not self.reader_stop.is_set():
                    self.session_error.emit(str(exc))
                break

        if not self.reader_stop.is_set():
            self.session_closed.emit()

    def _queue_output(self, value):
        self._display_buffer += value
        if not self._display_timer.isActive():
            self._display_timer.start()

    def _flush_display_buffer(self):
        if not self._display_buffer:
            if not self.connected:
                self._display_timer.stop()
            return

        # 4 KB per UI tick prevents huge results from appearing as one
        # instant block while retaining responsive live output.
        chunk = self._display_buffer[:1024]
        self._display_buffer = self._display_buffer[1024:]

        # Strip terminal escape/control noise, but keep tabs/newlines.
        chunk = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", chunk)
        chunk = chunk.replace("\x00", "").replace("\x08", "")
        chunk = "".join(
            c for c in chunk
            if c in "\r\n\t" or ord(c) >= 32
        )

        self.terminal.append_output(chunk)

    def _terminal_command(self, command):
        if not self.connected:
            return
        if command == "\x03":
            self._send_bytes(b"\x03")
            return
        self._send_bytes(
            command.encode("utf-8", errors="replace") + b"\r\n"
        )

    def _send_bytes(self, data):
        ser_obj = self.ser
        if not ser_obj or not self.connected:
            return
        try:
            ser_obj.write(data)
            ser_obj.flush()
        except Exception as exc:
            self.terminal.append_output(f"\n[Send error] {exc}\n")

    def disconnect(self):
        self.reader_stop.set()
        ser_obj = self.ser
        self.ser = None
        self.connected = False

        if ser_obj:
            try:
                ser_obj.close()
            except Exception:
                pass

        self._display_timer.stop()
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.state.setText("Disconnected")
        self.state.setStyleSheet("color:#d9534f;font-weight:700;")
        self.terminal.append_output("\n[Serial disconnected]\n")
        self.terminal.begin_input()

    def _remote_disconnect(self):
        self.connected = False
        self.ser = None
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.state.setText("Disconnected")
        self.state.setStyleSheet("color:#d9534f;font-weight:700;")
        self.terminal.append_output("\n[Serial device disconnected]\n")
        self.terminal.begin_input()

    def _show_error(self, message):
        self.terminal.append_output(f"\n[Serial error] {message}\n")
        self.terminal.begin_input()

    def closeEvent(self, event):
        self.disconnect()
        super().closeEvent(event)


class TelnetPage(QWidget):
    """PuTTY-style interactive Telnet terminal with automatic --More-- paging."""

    output_received = Signal(str)
    session_closed = Signal()
    session_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.sock = None
        self.reader_thread = None
        self.reader_stop = threading.Event()
        self.connected = False
        self.host = ""
        self.port = 23
        self._pending = bytearray()
        self.command_history = []
        self.history_index = -1
        self._pager_lock = threading.Lock()
        self._display_buffer = ""
        self._display_timer = QTimer(self)
        self._display_timer.setInterval(35)
        self._display_timer.timeout.connect(self._flush_display_buffer)
        self._prompt_tail = ""
        self._awaiting_command = False
        self._last_secret = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(5)

        header = QHBoxLayout()
        self.title = QLabel("Telnet")
        self.title.setStyleSheet("font-size:18px;font-weight:750;color:#0f3d5e;")
        self.state = QLabel("Disconnected")
        self.state.setStyleSheet("color:#d9534f;font-weight:700;")
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.state)
        root.addLayout(header)

        row = QHBoxLayout()
        row.addWidget(QLabel("Host / IP"))
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("e.g. 172.16.24.1")
        self.port_edit = QSpinBox()
        self.port_edit.setRange(1, 65535)
        self.port_edit.setValue(23)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("primaryButton")
        self.connect_btn.clicked.connect(self._connect_from_bar)
        row.addWidget(self.host_edit, 1)
        row.addWidget(QLabel("Port"))
        row.addWidget(self.port_edit)
        row.addWidget(self.connect_btn)
        root.addLayout(row)

        # The terminal itself is now the command input. No separate bottom card.
        self.terminal = TerminalWidget()
        self.terminal.command_entered.connect(self._terminal_command)
        root.addWidget(self.terminal, 1)

        self.output_received.connect(self._queue_output)
        self.session_closed.connect(self._remote_disconnect)
        self.session_error.connect(self._show_error)

        # Focus the terminal after page creation.
        self.terminal.setFocus()

    def _connect_from_bar(self):
        host = self.host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, "Telnet", "Enter an IP address or hostname.")
            return
        self.connect_to_target(host, self.port_edit.value())

    def configure_target(self, host, port=23):
        self.host = str(host).strip()
        self.port = int(port)
        self.host_edit.setText(self.host)
        self.port_edit.setValue(self.port)
        self.title.setText(f"Telnet  •  {self.host}:{self.port}")

    def connect_to_target(self, host=None, port=23):
        if host:
            self.configure_target(host, port)
        if not self.host:
            return

        self.disconnect(silent=True)
        self.terminal.clear()
        self.terminal.begin_input()
        self.connect_btn.setEnabled(False)
        self.terminal.append_output(
            f"Connecting to {self.host}:{self.port} ...\n"
        )

        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=8)
            self.sock.settimeout(0.25)
            self.connected = True
            self.reader_stop.clear()

            self.state.setText("Connected")
            self.state.setStyleSheet("color:#0a9f67;font-weight:700;")
            self.connect_btn.setEnabled(True)

            self.terminal.begin_input()

            self.reader_thread = threading.Thread(
                target=self._reader_loop, daemon=True
            )
            self.reader_thread.start()

        except Exception as exc:
            self.sock = None
            self.connected = False
            self.connect_btn.setEnabled(True)
            self.state.setText("Connection Failed")
            self.state.setStyleSheet("color:#d9534f;font-weight:700;")
            self.terminal.append_output(f"\nConnection error: {exc}\n")
            self.terminal.begin_input()

    def _reader_loop(self):
        while not self.reader_stop.is_set():
            sock = self.sock
            if not sock:
                break
            try:
                data = sock.recv(16384)
                if not data:
                    break
                self._parse_telnet(data)
            except socket.timeout:
                continue
            except Exception as exc:
                if not self.reader_stop.is_set():
                    self.session_error.emit(str(exc))
                break
        if not self.reader_stop.is_set():
            self.session_closed.emit()

    def _parse_telnet(self, data):
        self._pending.extend(data)
        buf = self._pending
        out = bytearray()
        reply = bytearray()
        i = 0

        while i < len(buf):
            if buf[i] != 255:
                out.append(buf[i])
                i += 1
                continue

            if i + 1 >= len(buf):
                break

            cmd = buf[i + 1]

            if cmd == 255:
                out.append(255)
                i += 2
                continue

            if cmd in (251, 252, 253, 254):
                if i + 2 >= len(buf):
                    break
                opt = buf[i + 2]
                # Refuse optional negotiations cleanly.
                reply.extend((255, 254 if cmd in (251, 252) else 252, opt))
                i += 3
                continue

            if cmd == 250:
                j = i + 2
                complete = False
                while j + 1 < len(buf):
                    if buf[j] == 255 and buf[j + 1] == 240:
                        j += 2
                        complete = True
                        break
                    j += 1
                if not complete:
                    break
                i = j
                continue

            i += 2

        if i:
            del buf[:i]

        if reply and self.sock:
            try:
                self.sock.sendall(reply)
            except Exception:
                pass

        if out:
            decoded = out.decode("utf-8", errors="replace")
            cleaned = self._clean_terminal_text(decoded)
            self._update_prompt_state(cleaned)

            # Cisco/IOS/HP-style pagers emit --More--. Remove the pager text
            # and automatically request the next page with a space.
            if self._contains_more(cleaned):
                cleaned = self._remove_more_markers(cleaned)
                if cleaned:
                    self.output_received.emit(cleaned)
                self._send_pager_space()
            elif cleaned:
                self.output_received.emit(cleaned)

    @staticmethod
    def _clean_terminal_text(value):
        # Remove ANSI escape/control sequences and backspace artifacts that
        # otherwise appear as "��������" or duplicated pager text.
        value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
        value = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", value)
        value = value.replace("\x00", "")
        value = value.replace("\x08", "")
        value = value.replace("\x7f", "")
        # Keep CR/LF/TAB and printable Unicode; remove other C0 controls.
        value = "".join(
            ch for ch in value
            if ch in "\r\n\t" or ord(ch) >= 32
        )
        # Remove replacement characters caused by Telnet/control bytes.
        value = value.replace("\ufffd", "")
        return value

    @staticmethod
    def _contains_more(value):
        return bool(re.search(r"--\s*More\s*--", value, re.I))

    @staticmethod
    def _remove_more_markers(value):
        value = re.sub(r"--\s*More\s*--", "", value, flags=re.I)
        value = value.replace("\r", "")
        return value

    def _send_pager_space(self):
        sock = self.sock
        if not sock or not self.connected:
            return
        # One space advances Cisco/HP-style pagers. Do it asynchronously so
        # the socket reader never blocks waiting on its own send.
        def send_space():
            try:
                sock.sendall(b" ")
            except Exception:
                pass
        threading.Thread(target=send_space, daemon=True).start()

    def _terminal_command(self, command):
        if not self.connected:
            return

        if command == "\x03":
            self.send_raw(b"\x03")
            self._awaiting_command = False
            self.terminal.set_input_enabled(True)
            return

        if command.strip():
            # Store normal commands only. Passwords are never stored in history.
            if not self.terminal._secret_mode:
                self.command_history.append(command)
                self.command_history = self.command_history[-100:]
                self.history_index = len(self.command_history)
            else:
                self._last_secret = command

        # Do not display a local echo. Cisco/IOS/HP devices normally echo the
        # command themselves. Disable editing until the next device prompt so
        # output can never overwrite the active prompt/input line.
        if command.strip() and not self.terminal._secret_mode:
            self._awaiting_command = True
            self.terminal.set_input_enabled(False)
        else:
            # Authentication prompts may require another credential immediately.
            self.terminal.set_secret_mode(False)

        self.send_raw(command.encode("utf-8", errors="replace") + b"\r\n")

    def _update_prompt_state(self, text):
        if not text:
            return

        tail = (self._prompt_tail + text)[-400:]
        self._prompt_tail = tail
        low = tail.lower()

        # Authentication prompts: password input is displayed only as bullets.
        if re.search(r"(?:password|passcode)\s*:\s*$", low):
            self.terminal.set_input_enabled(True)
            self.terminal.set_secret_mode(True)
            return
        if re.search(r"(?:username|login)\s*:\s*$", low):
            self.terminal.set_secret_mode(False)
            self.terminal.set_input_enabled(True)
            return

        # Cisco/IOS/HP-style operational/config prompts. A prompt at the end
        # means the previous command has completed and the terminal is editable.
        if re.search(r"(?:^|\n)[A-Za-z0-9_.()/:\-]+(?:\([A-Za-z0-9_.-]+\))?[#>]\s*$", tail):
            self._awaiting_command = False
            self.terminal.set_secret_mode(False)
            self.terminal.set_input_enabled(True)

    def send_raw(self, data):
        if not self.connected or not self.sock:
            return
        try:
            self.sock.sendall(data)
        except Exception as exc:
            self.terminal.append_output(f"\n[Send error] {exc}\n")

    def _queue_output(self, value):
        self._display_buffer += value
        if not self._display_timer.isActive():
            self._display_timer.start()

    def _flush_display_buffer(self):
        if not self._display_buffer:
            if not self.connected:
                self._display_timer.stop()
            return
        chunk = self._display_buffer[:768]
        self._display_buffer = self._display_buffer[1024:]
        self.append_terminal(chunk)

    def append_terminal(self, value):
        # Never display an echoed authentication secret, even if a legacy
        # device ignores password echo suppression.
        if self._last_secret:
            value = value.replace(self._last_secret, "•" * len(self._last_secret))
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        self.terminal.append_output(value)
        if self._last_secret and re.search(r"(?:^|\n)[^\n]*(?:[#>])\s*$", value):
            self._last_secret = ""

    def disconnect(self, silent=False):
        self.reader_stop.set()
        sock = self.sock
        self.sock = None
        self.connected = False

        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass

        self.connect_btn.setEnabled(True)
        self.state.setText("Disconnected")
        self.state.setStyleSheet("color:#d9534f;font-weight:700;")

        if not silent:
            self.terminal.append_output("\n[Disconnected]\n")
            self.terminal.begin_input()

    def _remote_disconnect(self):
        self.connected = False
        self.sock = None
        self.connect_btn.setEnabled(True)
        self.state.setText("Disconnected")
        self.state.setStyleSheet("color:#d9534f;font-weight:700;")
        self.terminal.append_output("\n[Remote Telnet connection closed]\n")
        self.terminal.begin_input()

    def _show_error(self, message):
        self.terminal.append_output(f"\n[Telnet error] {message}\n")
        self.terminal.begin_input()

    def closeEvent(self, event):
        self.disconnect(silent=True)
        super().closeEvent(event)


class SSHPage(QWidget):
    """Built-in SSH terminal using Paramiko."""

    def __init__(self):
        super().__init__()
        self.client = None
        self.channel = None
        self.reader_thread = None
        self.reader_stop = threading.Event()
        self.connected = False

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        self.title = QLabel("SSH / Terminal")
        self.title.setStyleSheet("font-size:18px;font-weight:750;color:#0f3d5e;")
        self.state = QLabel("Disconnected")
        self.state.setStyleSheet("color:#d9534f;font-weight:700;")
        top.addWidget(self.title)
        top.addStretch()
        top.addWidget(self.state)
        root.addLayout(top)

        form = QHBoxLayout()
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("IP / Hostname")
        self.port_edit = QSpinBox()
        self.port_edit.setRange(1, 65535)
        self.port_edit.setValue(22)
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("Username")
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.connect_btn = QPushButton("Connect SSH")
        self.connect_btn.setObjectName("primaryButton")
        self.connect_btn.clicked.connect(self.connect_ssh)
        form.addWidget(self.host_edit, 2)
        form.addWidget(self.port_edit)
        form.addWidget(self.user_edit, 1)
        form.addWidget(self.password_edit, 1)
        form.addWidget(self.connect_btn)
        root.addLayout(form)

        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.terminal.setStyleSheet("""
            QPlainTextEdit {
                background:#071a25;color:#e8f5fb;
                border:1px solid #315465;border-radius:8px;
                padding:7px;font-family:Consolas,"Cascadia Mono","Courier New";
                font-size:10pt;
            }
        """)
        root.addWidget(self.terminal, 1)

        command_row = QHBoxLayout()
        self.command = QLineEdit()
        self.command.setPlaceholderText("Type SSH command and press Enter...")
        self.command.returnPressed.connect(self.send_command)
        self.command.setEnabled(False)
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.clicked.connect(self.send_command)
        self.send_btn.setEnabled(False)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.disconnect)
        self.disconnect_btn.setEnabled(False)
        command_row.addWidget(self.command, 1)
        command_row.addWidget(self.send_btn)
        command_row.addWidget(self.disconnect_btn)
        root.addLayout(command_row)

    def configure_target(self, host, port=22, username="", password=""):
        self.host_edit.setText(str(host))
        self.port_edit.setValue(int(port))
        self.user_edit.setText(username)
        self.password_edit.setText(password)

    def connect_ssh(self):
        host = self.host_edit.text().strip()
        username = self.user_edit.text().strip()
        password = self.password_edit.text()
        port = self.port_edit.value()

        if not host or not username:
            QMessageBox.warning(self, "SSH", "Enter Host/IP and Username.")
            return

        try:
            import paramiko
        except ImportError:
            QMessageBox.critical(
                self, "SSH Component Missing",
                "Paramiko is not installed.\n\nRun:\npy -m pip install paramiko"
            )
            return

        self.disconnect(silent=True)
        self.terminal.clear()
        self.append_output(f"Connecting to {host}:{port} ...\n")
        self.state.setText("Connecting...")
        self.state.setStyleSheet("color:#e29b17;font-weight:700;")
        self.connect_btn.setEnabled(False)

        def worker():
            client = None
            channel = None
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password if password else None,
                    timeout=10,
                    banner_timeout=10,
                    auth_timeout=10,
                    look_for_keys=not bool(password),
                    allow_agent=not bool(password)
                )
                channel = client.invoke_shell(width=180, height=48)
                channel.settimeout(0.25)
                self.client = client
                self.channel = channel
                self.connected = True
                QTimer.singleShot(0, self._connected_ui)

                while not self.reader_stop.is_set() and not channel.closed:
                    try:
                        if channel.recv_ready():
                            data = channel.recv(8192)
                            if data:
                                decoded = data.decode("utf-8", errors="replace")
                                QTimer.singleShot(
                                    0, lambda d=decoded: self.append_output(d)
                                )
                        else:
                            time.sleep(0.04)
                    except Exception:
                        break
            except Exception as exc:
                QTimer.singleShot(0, lambda e=str(exc): self._ssh_failed(e))
            finally:
                try:
                    if channel:
                        channel.close()
                except Exception:
                    pass
                try:
                    if client:
                        client.close()
                except Exception:
                    pass
                QTimer.singleShot(0, self._remote_closed)

        self.reader_stop.clear()
        self.reader_thread = threading.Thread(target=worker, daemon=True)
        self.reader_thread.start()

    def _connected_ui(self):
        self.state.setText("Connected")
        self.state.setStyleSheet("color:#0a9f67;font-weight:700;")
        self.command.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(True)
        self.connect_btn.setEnabled(True)
        self.append_output("\n[SSH session connected]\n")

    def _ssh_failed(self, message):
        self.connected = False
        self.state.setText("Connection Failed")
        self.state.setStyleSheet("color:#d9534f;font-weight:700;")
        self.connect_btn.setEnabled(True)
        self.append_output(f"\n[SSH error] {message}\n")

    def _remote_closed(self):
        if self.connected:
            self.connected = False
            self.state.setText("Disconnected")
            self.state.setStyleSheet("color:#d9534f;font-weight:700;")
            self.command.setEnabled(False)
            self.send_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(False)
            self.connect_btn.setEnabled(True)
            self.append_output("\n[SSH connection closed]\n")

    def append_output(self, value):
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.terminal.setTextCursor(cursor)
        self.terminal.insertPlainText(value)
        self.terminal.ensureCursorVisible()

    def send_command(self):
        if not self.connected or not self.channel:
            return
        try:
            self.channel.send(self.command.text() + "\n")
            self.command.clear()
        except Exception as exc:
            self.append_output(f"\n[Send error] {exc}\n")

    def disconnect(self, silent=False):
        self.reader_stop.set()
        self.connected = False
        ch, cl = self.channel, self.client
        self.channel = None
        self.client = None
        try:
            if ch:
                ch.close()
        except Exception:
            pass
        try:
            if cl:
                cl.close()
        except Exception:
            pass
        self.command.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(False)
        self.connect_btn.setEnabled(True)
        self.state.setText("Disconnected")
        self.state.setStyleSheet("color:#d9534f;font-weight:700;")
        if not silent:
            self.append_output("\n[Disconnected]\n")

    def closeEvent(self, event):
        self.disconnect(silent=True)
        super().closeEvent(event)


class ConnectionDialog(QDialog):
    """Launcher for built-in SSH/Telnet and native Windows RDP."""

    def __init__(self, protocol, history, main_window):
        super().__init__(main_window)
        self.protocol = protocol
        self.history = history
        self.main_window = main_window
        self.setWindowTitle(f"{protocol} Connection")
        self.setMinimumWidth(470)

        root = QVBoxLayout(self)
        title = QLabel(f"{protocol} Connection")
        title.setStyleSheet("font-size:20px;font-weight:800;color:#123a56;")
        root.addWidget(title)

        form = QFormLayout()
        self.host = QLineEdit()
        self.host.setPlaceholderText("IP / Hostname")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue({"SSH":22, "Telnet":23, "RDP":3389}[protocol])
        form.addRow("Host / IP:", self.host)
        form.addRow("Port:", self.port)

        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)

        if protocol in ("SSH", "RDP"):
            form.addRow("Username:", self.username)
        if protocol == "SSH":
            form.addRow("Password:", self.password)
        root.addLayout(form)

        hint = QLabel()
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#61798a;font-size:10px;")
        hint.setText(
            "SSH uses the built-in Paramiko terminal. "
            "Telnet uses the built-in Telnet terminal. "
            "RDP uses the native Windows Remote Desktop client."
        )
        root.addWidget(hint)

        row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        connect = QPushButton(f"Connect via {protocol}")
        connect.setObjectName("primaryButton")
        connect.clicked.connect(self.connect_now)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(connect)
        root.addLayout(row)

    def connect_now(self):
        host = self.host.text().strip()
        if not host:
            QMessageBox.warning(self, "Connection", "Enter an IP address or hostname.")
            return
        port = self.port.value()
        username = self.username.text().strip()
        password = self.password.text()

        try:
            if self.protocol == "Telnet":
                self.main_window.open_telnet(host, port)
                self.history.add(host, host, "Telnet", "", "Connected")
            elif self.protocol == "SSH":
                self.main_window.open_ssh(host, port, username, password)
                self.history.add(host, host, "SSH", username, "Launched")
            elif self.protocol == "RDP":
                self.main_window.open_rdp(host, port)
                self.history.add(host, host, "RDP", username, "Launched")
            self.accept()
        except Exception as exc:
            self.history.add(host, host, self.protocol, username, "Failed")
            QMessageBox.critical(self, "Connection Error", str(exc))


class TelnetTerminalDialog(QDialog):
    """Compatibility wrapper for older scanner paths."""
    def __init__(self, host, port, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Telnet • {host}:{port}")
        layout = QVBoxLayout(self)
        self.page = TelnetPage()
        layout.addWidget(self.page)
        self.resize(1100, 700)
        QTimer.singleShot(0, lambda: self.page.connect_to_target(host, port))


class HistoryPage(QWidget):
    history_changed = Signal()

    def __init__(self, history):
        super().__init__()
        self.history = history
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)

        title = QLabel("Connection History")
        title.setObjectName("pageTitle")
        sub = QLabel("Audit trail of N-Console device connections.")
        sub.setObjectName("pageSub")
        root.addWidget(title)
        root.addWidget(sub)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Date / Time", "Device", "IP", "Protocol", "Username", "Status", "Duration"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table)

        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.load)
        clear = QPushButton("Clear History")
        clear.setObjectName("dangerButton")
        clear.clicked.connect(self.clear_history)
        buttons.addWidget(refresh)
        buttons.addWidget(clear)
        buttons.addStretch()
        root.addLayout(buttons)
        self.load()

    def load(self):
        rows = self.history.rows()
        self.table.setRowCount(0)
        for data in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, value in enumerate(data):
                self.table.setItem(row, col, QTableWidgetItem(str(value or "")))

    def clear_history(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Clear all N-Console connection history?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.history.clear()
            self.load()
            self.history_changed.emit()


class FlowLayout(QLayout):
    """Compact wrapping layout for service buttons; never overlaps."""
    def __init__(self, parent=None, margin=2, spacing=4):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        right = rect.right()
        space_x = self.spacing()
        space_y = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + space_x
            if next_x - space_x > right and line_height > 0:
                x = rect.x()
                y += line_height + space_y
                next_x = x + hint.width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + self.contentsMargins().bottom()


class ScanWorker(QObject):
    result = Signal(object)
    progress = Signal(int, int, str)
    finished = Signal()
    error = Signal(str)

    COMMON_PORTS = {
        20: "FTP-DATA", 21: "FTP", 22: "SSH", 23: "TELNET",
        25: "SMTP", 53: "DNS", 67: "DHCP", 68: "DHCP",
        69: "TFTP", 80: "HTTP", 110: "POP3", 111: "RPC",
        123: "NTP", 135: "MS-RPC", 137: "NETBIOS-NS",
        138: "NETBIOS-DGM", 139: "NETBIOS-SSN", 143: "IMAP",
        161: "SNMP", 389: "LDAP", 443: "HTTPS", 445: "SMB",
        502: "MODBUS", 514: "SYSLOG", 554: "RTSP", 587: "SMTP-SUBMISSION",
        631: "IPP", 993: "IMAPS", 995: "POP3S", 1433: "MSSQL",
        1521: "ORACLE", 1883: "MQTT", 2049: "NFS", 2375: "DOCKER",
        3306: "MYSQL", 3389: "RDP", 5432: "POSTGRESQL", 5900: "VNC",
        5985: "WINRM-HTTP", 5986: "WINRM-HTTPS", 6379: "REDIS",
        6443: "K8S-API", 8080: "HTTP-ALT", 8443: "HTTPS-ALT",
        9100: "JETDIRECT"
    }

    def __init__(self, hosts, workers, deep):
        super().__init__()
        self.hosts = hosts
        self.workers = workers
        self.deep = deep
        self.cancelled = False
        self._executor = None
        self._local_ip_mac = self.get_local_ip_mac_map()

    def cancel(self):
        self.cancelled = True
        # Do not wait for every queued host scan. Running socket probes have
        # short timeouts and will finish in the background; queued work is
        # cancelled immediately so the UI can be reused for another CIDR.
        executor = self._executor
        if executor is not None:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                executor.shutdown(wait=False)
            except Exception:
                pass

    @staticmethod
    def get_local_ip_mac_map():
        """Return IPv4 -> adapter MAC for interfaces on this computer.

        This is intentionally collected once per scan. It fixes the important
        case where the scanned range contains the machine running N-Console:
        that address has no ARP entry for itself, so an ARP-only lookup cannot
        discover its MAC.
        """
        result = {}
        try:
            if platform.system().lower() == "windows":
                ps = (
                    "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
                    "ForEach-Object { "
                    "$a=Get-NetAdapter -InterfaceIndex $_.InterfaceIndex "
                    "-ErrorAction SilentlyContinue; "
                    "if($a){ '{0}|{1}' -f $_.IPAddress,$a.MacAddress } "
                    "}"
                )
                p = _run_hidden(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                     "-Command", ps],
                    capture_output=True, text=True, errors="ignore", timeout=5
                )
                for line in (p.stdout or "").splitlines():
                    parts = [x.strip() for x in line.split("|", 1)]
                    if len(parts) != 2:
                        continue
                    ip, mac = parts
                    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", ip) and re.search(
                        r"(?i)^[0-9a-f]{2}(?:-[0-9a-f]{2}){5}$", mac
                    ):
                        result[ip] = mac.upper()
            else:
                # Linux fallback: /sys/class/net/<iface>/address + ip command.
                p = _run_hidden(
                    ["ip", "-o", "-4", "addr", "show"],
                    capture_output=True, text=True, errors="ignore", timeout=3
                )
                for line in (p.stdout or "").splitlines():
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    iface = parts[1]
                    ip = parts[3].split("/", 1)[0]
                    mac_path = f"/sys/class/net/{iface}/address"
                    try:
                        mac = open(mac_path, "r", encoding="utf-8").read().strip()
                        if mac:
                            result[ip] = mac.replace(":", "-").upper()
                    except Exception:
                        pass
        except Exception:
            pass
        return result

    @staticmethod
    def ping(ip):
        if platform.system().lower() == "windows":
            cmd = ["ping", "-n", "1", "-w", "450", ip]
        else:
            cmd = ["ping", "-c", "1", "-W", "1", ip]
        started = time.perf_counter()
        p = _run_hidden(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elapsed = round((time.perf_counter() - started) * 1000)
        return p.returncode == 0, elapsed

    @staticmethod
    def tcp_open(ip, port, timeout=0.14):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            return sock.connect_ex((ip, port)) == 0
        except OSError:
            return False
        finally:
            sock.close()

    @staticmethod
    def get_mac(ip):
        """Resolve a host MAC from the local neighbor/ARP cache.

        The scan may report UP because of TCP even when ICMP is blocked.  In
        that case Windows can still have the L2 neighbor in its ARP cache.
        Parse the complete cache rather than relying on `arp -a <ip>`, which
        behaves differently across Windows builds/locales.
        """
        system = platform.system().lower()
        try:
            if system == "windows":
                mac_re = re.compile(r"(?i)\b[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}\b")
                ip_re = re.compile(r"(?<![0-9.])" + re.escape(ip) + r"(?![0-9.])")

                # First try the complete ARP table.
                p = _run_hidden(
                    ["arp", "-a"],
                    capture_output=True, text=True, errors="ignore",
                    timeout=2
                )
                for line in (p.stdout or "").splitlines():
                    if ip_re.search(line):
                        m = mac_re.search(line)
                        if m:
                            return m.group(0).upper()

                # Windows neighbor table is a useful fallback, especially on
                # newer systems where ARP output can be localized.
                ps = (
                    "Get-NetNeighbor -AddressFamily IPv4 -IPAddress '"
                    + ip.replace("'", "''")
                    + "' -ErrorAction SilentlyContinue | "
                      "Select-Object -ExpandProperty LinkLayerAddress"
                )
                p2 = _run_hidden(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                    capture_output=True, text=True, errors="ignore",
                    timeout=3
                )
                for line in (p2.stdout or "").splitlines():
                    m = re.search(r"(?i)\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b", line.strip())
                    if m:
                        return m.group(0).replace(":", "-").upper()

                # Legacy netsh neighbor table fallback.
                p3 = _run_hidden(
                    ["netsh", "interface", "ip", "show", "neighbors"],
                    capture_output=True, text=True, errors="ignore",
                    timeout=3
                )
                for line in (p3.stdout or "").splitlines():
                    if ip_re.search(line):
                        m = re.search(r"(?i)\b[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}\b", line)
                        if m:
                            return m.group(0).upper()

            else:
                p = _run_hidden(
                    ["ip", "neigh", "show", ip],
                    capture_output=True, text=True, errors="ignore",
                    timeout=2
                )
                m = re.search(r"(?i)lladdr\s+([0-9a-f]{2}(?::[0-9a-f]{2}){5})", p.stdout or "")
                if m:
                    return m.group(1).replace(":", "-").upper()

                p = _run_hidden(
                    ["arp", "-n", ip],
                    capture_output=True, text=True, errors="ignore",
                    timeout=2
                )
                for line in (p.stdout or "").splitlines():
                    if ip in line:
                        m = re.search(r"(?i)\\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\\b", line)
                        if m:
                            return m.group(0).replace(":", "-").upper()
        except Exception:
            pass
        return "-"

    @staticmethod
    def resolve_hostname(ip):
        """Resolve a useful LAN hostname with several Windows fallbacks."""
        # 1) Normal reverse DNS.
        try:
            name = socket.gethostbyaddr(ip)[0].strip().rstrip(".")
            if name and name.lower() != ip.lower():
                return name
        except Exception:
            pass

        if platform.system().lower() == "windows":
            # 2) ping -a often resolves local DNS/hosts/NetBIOS names.
            try:
                p = _run_hidden(
                    ["ping", "-a", "-n", "1", "-w", "350", ip],
                    capture_output=True, text=True, errors="ignore", timeout=1.2
                )
                for line in (p.stdout or "").splitlines():
                    m = re.search(
                        r"(?i)^\s*Pinging\s+([^\s\[]+)\s+\[" +
                        re.escape(ip) + r"\]",
                        line
                    )
                    if m:
                        name = m.group(1).strip()
                        if name and name.lower() != ip.lower():
                            return name
            except Exception:
                pass

            # 3) nbtstat -A can resolve Windows/NetBIOS hosts even without DNS.
            try:
                p = _run_hidden(
                    ["nbtstat", "-A", ip],
                    capture_output=True, text=True, errors="ignore", timeout=2
                )
                for line in (p.stdout or "").splitlines():
                    m = re.match(
                        r"^\s*([A-Za-z0-9._$-]{1,63})\s+<00>\s+UNIQUE",
                        line, re.I
                    )
                    if m:
                        return m.group(1)
            except Exception:
                pass

            # 4) PowerShell Resolve-DnsName fallback.
            try:
                ps = (
                    "Resolve-DnsName -Name '" + ip.replace("'", "''") +
                    "' -Type PTR -ErrorAction SilentlyContinue | "
                    "Select-Object -ExpandProperty NameHost"
                )
                p = _run_hidden(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                     "-Command", ps],
                    capture_output=True, text=True, errors="ignore", timeout=2
                )
                for line in (p.stdout or "").splitlines():
                    name = line.strip().rstrip(".")
                    if name and name.lower() != ip.lower():
                        return name
            except Exception:
                pass

        return "-"

    def common_scan(self, ip):
        found = []
        # Common scan is deliberately parallel so /24 scans finish quickly.
        with ThreadPoolExecutor(max_workers=24) as pool:
            futures = {pool.submit(self.tcp_open, ip, p, 0.16): p for p in self.COMMON_PORTS}
            for f in as_completed(futures):
                if self.cancelled:
                    return found
                port = futures[f]
                try:
                    if f.result():
                        found.append((port, self.COMMON_PORTS[port]))
                except Exception:
                    pass
        return sorted(found)

    def deep_scan_host(self, ip, already_found):
        found_ports = {p for p, _ in already_found}
        # Deep scan is intentionally bounded to 1-65535 but parallelized in chunks.
        # It runs only after the host is shown as reachable, and it is cancellable.
        ports = [p for p in range(1, 65536) if p not in found_ports]
        discovered = list(already_found)
        chunk_size = 1024
        for base in range(0, len(ports), chunk_size):
            if self.cancelled:
                break
            chunk = ports[base:base + chunk_size]
            with ThreadPoolExecutor(max_workers=64) as pool:
                futures = {pool.submit(self.tcp_open, ip, p, 0.055): p for p in chunk}
                for f in as_completed(futures):
                    if self.cancelled:
                        break
                    port = futures[f]
                    try:
                        if f.result():
                            discovered.append((port, self.COMMON_PORTS.get(port, "TCP")))
                    except Exception:
                        pass
        return sorted(set(discovered), key=lambda x: x[0])

    def check_host(self, ip):
        ping_up, latency = self.ping(ip)
        services = self.common_scan(ip)

        # IMPORTANT: TCP detection is independent of ICMP. A host that blocks ping
        # but has 3389/RDP open will still be reported as reachable.
        reachable = ping_up or bool(services)

        # Deep scanning every port on every /24 host is inherently expensive.
        # To keep the UI responsive and avoid wasting time on dead hosts, deep scan
        # only hosts that responded to ICMP or a common TCP service.
        if self.deep and reachable and not self.cancelled:
            services = self.deep_scan_host(ip, services)

        hostname = self.resolve_hostname(ip) if reachable else "-"

        # Give the OS a moment to commit the L2 neighbor learned during the
        # successful ping/TCP probe, then resolve the MAC. This is deliberately
        # tiny so a large CIDR scan remains responsive.
        if reachable:
            # Give Windows time to learn the L2 neighbor. For local Ethernet
            # targets, a fresh one-packet ping is a lightweight ARP refresh.
            try:
                if platform.system().lower() == "windows":
                    _run_hidden(
                        ["ping", "-n", "1", "-w", "250", ip],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=0.8
                    )
            except Exception:
                pass
            time.sleep(0.03)

        # The computer running N-Console is special: its own IP normally does
        # not appear in the ARP cache. Prefer the interface mapping collected
        # at scan start, then fall back to neighbor/ARP discovery for peers.
        mac = self._local_ip_mac.get(ip, "-")
        if mac == "-":
            mac = self.get_mac(ip)

        # A second neighbor lookup after the successful probe catches devices
        # whose ARP/neighbor entry is committed slightly later.
        if mac == "-" and reachable:
            try:
                if platform.system().lower() == "windows":
                    _run_hidden(
                        ["arp", "-d", ip],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=0.8
                    )
                    _run_hidden(
                        ["ping", "-n", "1", "-w", "500", ip],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=1.0
                    )
            except Exception:
                pass
            time.sleep(0.12)
            mac = self.get_mac(ip)

        return {
            "ip": ip,
            "hostname": hostname,
            "mac": mac,
            "status": "UP" if reachable else "DOWN",
            "latency": latency if ping_up else "-",
            "ports": [p for p, _ in services],
            "service_pairs": services,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def run(self):
        executor = None
        futures = {}
        try:
            total = len(self.hosts)
            done = 0
            executor = ThreadPoolExecutor(max_workers=self.workers)
            self._executor = executor
            futures = {
                executor.submit(self.check_host, ip): ip for ip in self.hosts
            }

            while futures and not self.cancelled:
                finished, _ = wait(
                    list(futures.keys()),
                    timeout=0.15,
                    return_when=FIRST_COMPLETED
                )
                if self.cancelled:
                    break
                if not finished:
                    continue

                for future in finished:
                    ip = futures.pop(future)
                    try:
                        data = future.result()
                        self.result.emit(data)
                    except Exception as exc:
                        self.result.emit({
                            "ip": ip, "hostname": "-", "mac": "-", "status": "DOWN",
                            "latency": "-", "ports": [], "service_pairs": [],
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "error": str(exc)
                        })
                    done += 1
                    self.progress.emit(done, total, f"Scanning {ip}...")

            if self.cancelled:
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    executor.shutdown(wait=False)
            else:
                executor.shutdown(wait=True)
                self.progress.emit(total, total, "Scan completed")
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self._executor = None
            self.finished.emit()


class ScannerPage(QWidget):
    def __init__(self):
        super().__init__()
        self.results = []
        self.result_by_ip = {}
        self.thread = None
        self.worker = None
        self.scanning = False
        self.scan_generation = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(10)

        title = QLabel("IP Scanner")
        title.setObjectName("pageTitle")
        sub = QLabel("CIDR discovery • MAC address • ICMP/TCP reachability • open ports • clickable services")
        sub.setObjectName("pageSub")
        root.addWidget(title)
        root.addWidget(sub)

        bar = QHBoxLayout()
        bar.setSpacing(7)
        self.cidr = QLineEdit("192.168.1.0/24")
        self.cidr.setMinimumWidth(230)
        self.workers = QSpinBox()
        self.workers.setRange(1, 64)
        self.workers.setValue(32)
        self.deep_scan = QCheckBox("Deep port scan (1–65535)")
        self.deep_scan.setToolTip("Deep scan is cancellable and runs only against reachable hosts.")
        self.start_btn = QPushButton("Start Scan")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.clicked.connect(self.start_scan)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("dangerButton")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_scan)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear)

        bar.addWidget(QLabel("CIDR:"))
        bar.addWidget(self.cidr)
        bar.addWidget(QLabel("Workers:"))
        bar.addWidget(self.workers)
        bar.addWidget(self.deep_scan)
        bar.addWidget(self.start_btn)
        bar.addWidget(self.cancel_btn)
        bar.addWidget(clear_btn)
        bar.addStretch()
        root.addLayout(bar)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.total = StatCard("TOTAL IPS", "0", "#2774e6")
        self.up = StatCard("ONLINE / REACHABLE", "0", "#13a673")
        self.down = StatCard("OFFLINE", "0", "#e55353")
        self.services = StatCard("OPEN SERVICES", "0", "#7b55e8")
        for card in (self.total, self.up, self.down, self.services):
            cards.addWidget(card)
        root.addLayout(cards)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        root.addWidget(self.progress)
        self.scan_status = QLabel("Ready")
        self.scan_status.setStyleSheet("color:#61798a;font-size:10px;")
        root.addWidget(self.scan_status)

        self.table = QTableWidget(0, 8)
        self.table.setObjectName("scannerTable")
        self.table.setHorizontalHeaderLabels([
            "IP Address", "Hostname", "MAC Address", "Status", "Latency (ms)",
            "Open Ports", "Services", "Checked At"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)
        header.setStretchLastSection(False)
        widths = [135, 185, 165, 125, 110, 145, 430, 160]
        for i, width in enumerate(widths):
            self.table.setColumnWidth(i, width)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        export = QPushButton("Generate Excel Report")
        export.setObjectName("primaryButton")
        export.clicked.connect(self.export_xlsx)
        bottom.addWidget(export)
        note = QLabel("Blue service buttons are clickable. RDP/SSH/Telnet/HTTP/HTTPS open directly when supported.")
        note.setStyleSheet("color:#5e7587;font-size:11px;")
        bottom.addWidget(note)
        bottom.addStretch()
        root.addLayout(bottom)

    def start_scan(self):
        if self.scanning:
            return
        self.scan_generation += 1
        active_generation = self.scan_generation
        try:
            net = ipaddress.ip_network(self.cidr.text().strip(), strict=False)
            if net.version != 4:
                raise ValueError
            hosts = [str(x) for x in net.hosts()]
            if not hosts:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Invalid CIDR", "Use a valid IPv4 CIDR such as 192.168.1.0/24.")
            return

        if self.deep_scan.isChecked() and len(hosts) > 64:
            answer = QMessageBox.question(
                self, "Deep Scan Warning",
                "Deep scanning 1–65535 ports on more than 64 hosts can take a long time.\n\n"
                "The scan is now cancellable and the interface will remain responsive.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if answer != QMessageBox.Yes:
                return

        self.results = []
        self.result_by_ip = {}
        self.table.setRowCount(0)
        self.progress.setMaximum(len(hosts))
        self.progress.setValue(0)
        self.total.set_value(len(hosts))
        self.up.set_value(0)
        self.down.set_value(0)
        self.services.set_value(0)

        self.scanning = True
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.cidr.setEnabled(False)
        self.workers.setEnabled(False)
        self.deep_scan.setEnabled(False)
        self.scan_status.setText("Starting scan...")

        self.thread = QThread(self)
        self.worker = ScanWorker(hosts, self.workers.value(), self.deep_scan.isChecked())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        # IMPORTANT: connect worker signals directly to QObject-bound slots.
        # A lambda has no QObject receiver context in PySide6 and can therefore
        # execute in the worker thread. That was causing cross-thread Qt
        # warnings and freezing/painting failures while rows were added.
        self.worker.result.connect(self.on_result)
        self.worker.progress.connect(self.on_progress)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.cleanup_thread)
        self.thread.start()

    def cancel_scan(self):
        if not self.scanning:
            return
        # Invalidate all queued result/progress signals from this scan.
        self.scan_generation += 1
        worker = self.worker
        if worker:
            worker.cancel()
        self.scanning = False

        # Release the controls immediately. The worker has been told not to
        # wait for queued hosts, so the user can enter a new CIDR right away.
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.cidr.setEnabled(True)
        self.workers.setEnabled(True)
        self.deep_scan.setEnabled(True)
        self.scan_status.setText("Scan cancelled — ready for a new CIDR")

    def on_result(self, result):
        # Ignore results from a previous cancelled scan. sender() is the
        # ScanWorker whose signal delivered this queued callback.
        if self.sender() is not self.worker or not self.scanning:
            return
        self.results.append(result)
        self.result_by_ip[result["ip"]] = result
        self.add_row(result)
        online = sum(1 for r in self.results if r["status"] == "UP")
        service_count = sum(len(r["service_pairs"]) for r in self.results)
        self.up.set_value(online)
        self.down.set_value(len(self.results) - online)
        self.services.set_value(service_count)

    def on_progress(self, done, total, status):
        if self.sender() is not self.worker or not self.scanning:
            return
        self.progress.setValue(done)
        self.scan_status.setText(status)

    def on_error(self, message):
        if self.sender() is not self.worker or not self.scanning:
            return
        QMessageBox.critical(self, "Scanner Error", message)

    def on_finished(self):
        # A cancelled worker can finish after a new worker has already started.
        # Never let the old worker reset the new scan's controls.
        worker = self.sender()
        if worker is not self.worker:
            return
        cancelled = bool(worker.cancelled)
        self.scanning = False
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.cidr.setEnabled(True)
        self.workers.setEnabled(True)
        self.deep_scan.setEnabled(True)
        if not cancelled:
            self.progress.setValue(self.progress.maximum())
        self.scan_status.setText("Scan completed" if not cancelled else "Scan cancelled")
        self.results.sort(key=lambda r: tuple(int(v) for v in r["ip"].split(".")))

    def cleanup_thread(self):
        finished_thread = self.sender()
        # A cancelled scan can finish after a new scan has already started.
        # Never clear references belonging to the newer scan.
        if finished_thread is not self.thread:
            try:
                finished_thread.deleteLater()
            except Exception:
                pass
            return

        if self.worker:
            self.worker.deleteLater()
        if self.thread:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None

    def make_service_button(self, ip, port, name):
        btn = QPushButton(f"✓ {name}:{port}")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(f"Open {name} on {ip}:{port}")
        btn.setFixedHeight(26)
        btn.setMinimumWidth(90)
        btn.setMaximumWidth(145)
        btn.setStyleSheet("""
            QPushButton {
                background:#1769d1;
                color:#ffffff;
                border:1px solid #0f5bbd;
                border-radius:7px;
                padding:3px 7px;
                font-size:9px;
                font-weight:700;
            }
            QPushButton:hover { background:#0d55ae; }
            QPushButton:pressed { background:#083f87; }
        """)
        btn.clicked.connect(lambda checked=False, p=port, n=name: self.launch_service(ip, p, n))
        return btn

    def make_service_widget(self, result):
        container = QWidget()
        flow = FlowLayout(container, margin=3, spacing=4)
        services = result["service_pairs"]
        if not services:
            label = QLabel("—")
            label.setStyleSheet("color:#8b9ba7;border:none;")
            flow.addWidget(label)
        else:
            for port, name in services:
                flow.addWidget(self.make_service_button(result["ip"], port, name))
        rows = max(1, (len(services) + 2) // 3)
        container.setMinimumHeight(min(220, 8 + rows * 30))
        return container

    @staticmethod
    def _ip_key(ip):
        try:
            return tuple(int(part) for part in str(ip).split("."))
        except Exception:
            return (999, 999, 999, 999)

    def _sorted_insert_row(self, ip):
        """Find the numeric IPv4 position for live ordered insertion."""
        key = self._ip_key(ip)
        lo, hi = 0, self.table.rowCount()
        while lo < hi:
            mid = (lo + hi) // 2
            existing = self.table.item(mid, 0)
            existing_key = self._ip_key(existing.text()) if existing else (999, 999, 999, 999)
            if existing_key < key:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def add_row(self, r):
        # Workers finish in arbitrary order. Keep the visible scanner strictly
        # numeric: .1, .2, .3 ... .254, then the next subnet.
        row = self._sorted_insert_row(r["ip"])
        self.table.insertRow(row)
        values = [
            r["ip"], r["hostname"], r["mac"], r["status"], str(r["latency"]),
            ", ".join(str(p) for p in r["ports"]) if r["ports"] else "—", "", r["time"]
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col == 3:
                item.setForeground(QColor("#078a62" if value == "UP" else "#df404b"))
                item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.table.setItem(row, col, item)
        service_widget = self.make_service_widget(r)
        self.table.setCellWidget(row, 6, service_widget)
        rows = max(1, (len(r["service_pairs"]) + 2) // 3)
        self.table.setRowHeight(row, min(220, 10 + rows * 30))

    def clear(self):
        if self.scanning:
            self.cancel_scan()
        else:
            self.scan_generation += 1
        self.results.clear()
        self.result_by_ip.clear()
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self.scan_status.setText("Ready")
        for card in (self.total, self.up, self.down, self.services):
            card.set_value("0")

    @staticmethod
    def launch_service(ip, port, name):
        try:
            import webbrowser
            n = name.upper()
            mw = self.window()
            if n in ("HTTP", "HTTP-ALT"):
                webbrowser.open(f"http://{ip}:{port}")
            elif n in ("HTTPS", "HTTPS-ALT", "WINRM-HTTPS"):
                webbrowser.open(f"https://{ip}:{port}")
            elif n == "RDP":
                mw.open_rdp(ip, port)
            elif n == "SSH":
                mw.open_ssh(ip, port)
            elif n == "TELNET":
                mw.open_telnet(ip, port)
            elif n in ("FTP", "FTP-DATA"):
                webbrowser.open(f"ftp://{ip}:{port}")
            elif n == "SMB":
                if platform.system().lower() == "windows":
                    subprocess.Popen(["explorer.exe", f"\\\\{ip}"])
                else:
                    webbrowser.open(f"smb://{ip}")
            elif n == "VNC":
                webbrowser.open(f"vnc://{ip}:{port}")
            elif n == "RTSP":
                webbrowser.open(f"rtsp://{ip}:{port}")
            else:
                QMessageBox.information(
                    self, "Service Detected",
                    f"{name} is open on {ip}:{port}."
                )
        except FileNotFoundError:
            QMessageBox.warning(
                self, "Client Not Available",
                "The required Windows client is not available."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Open Service", str(exc))

    def export_xlsx(self):
        if not self.results:
            QMessageBox.information(self, "No Scan Data", "Run a scan first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Excel Report", "N-Console-IP-Scan-Report.xlsx", "Excel Workbook (*.xlsx)"
        )
        if not path:
            return
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment
            from openpyxl.worksheet.table import Table, TableStyleInfo
            from openpyxl.utils import get_column_letter
            wb = Workbook()
            ws = wb.active
            ws.title = "IP Scan Report"
            ws.sheet_view.showGridLines = False
            ws.merge_cells("A1:H1")
            ws["A1"] = "N-CONSOLE NETWORK DISCOVERY REPORT"
            ws["A1"].font = Font(size=16, bold=True, color="FFFFFF")
            ws["A1"].fill = PatternFill("solid", fgColor="1769D1")
            ws["A1"].alignment = Alignment(horizontal="center")
            ws["A2"] = "Generated"; ws["B2"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ws["A3"] = "CIDR"; ws["B3"] = self.cidr.text().strip()
            ws["A4"] = "Developer"; ws["B4"] = DEVELOPER
            headers = ["IP Address","Hostname","MAC Address","Status","Latency (ms)","Open Ports","Services","Checked At"]
            for c, h in enumerate(headers, 1):
                cell = ws.cell(6, c, h); cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="2878B5"); cell.alignment = Alignment(horizontal="center")
            sorted_results = sorted(self.results, key=lambda r: tuple(int(v) for v in r["ip"].split(".")))
            for row_idx, r in enumerate(sorted_results, 7):
                vals = [r["ip"], r["hostname"], r["mac"], r["status"], r["latency"], ", ".join(str(p) for p in r["ports"]) or "—", ", ".join(f"{n}:{p}" for p,n in r["service_pairs"]) or "—", r["time"]]
                for col, value in enumerate(vals, 1):
                    ws.cell(row_idx, col, value).alignment = Alignment(vertical="top", wrap_text=True)
                ws.cell(row_idx, 4).fill = PatternFill("solid", fgColor="C6EFCE" if r["status"] == "UP" else "FFC7CE")
            end_row = 6 + len(sorted_results)
            if end_row >= 7:
                tab = Table(displayName="NConsoleIPScan", ref=f"A6:H{end_row}")
                tab.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False, showRowStripes=True, showColumnStripes=False)
                ws.add_table(tab)
            widths = [18, 28, 20, 16, 16, 24, 52, 22]
            for i, width in enumerate(widths, 1): ws.column_dimensions[get_column_letter(i)].width = width
            ws.freeze_panes = "A7"
            wb.save(path)
            QMessageBox.information(self, "Excel Generated", f"Professional report saved:\n{path}")
        except ImportError:
            QMessageBox.critical(self, "Missing Module", "Install openpyxl with:\npy -m pip install openpyxl")
        except Exception as exc:
            QMessageBox.critical(self, "Excel Error", str(exc))



class PingRoutePage(QWidget):
    """Single-host ping and traceroute diagnostics with live auto-scrolling output."""

    def __init__(self):
        super().__init__()
        self._ping_target = ""
        self._ping_sent = 0
        self._ping_received = 0
        self._user_stopped = False

        self._ping_process = QProcess(self)
        self._ping_process.setProcessChannelMode(QProcess.MergedChannels)
        self._ping_process.readyReadStandardOutput.connect(self._read_ping_output)
        self._ping_process.finished.connect(self._ping_finished)
        self._ping_process.errorOccurred.connect(self._ping_error)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(12)

        title = QLabel("Ping & Route Diagnostics")
        title.setObjectName("pageTitle")
        sub = QLabel(
            "Test one IP/hostname, watch live ping replies, measure latency and packet loss, and trace its network path."
        )
        sub.setObjectName("pageSub")
        root.addWidget(title)
        root.addWidget(sub)

        controls = QHBoxLayout()
        self.target = QLineEdit()
        self.target.setPlaceholderText("192.168.0.16 or hostname")
        self.target.setMinimumWidth(300)
        self.count = QSpinBox()
        self.count.setRange(1, 1000)
        self.count.setValue(4)
        self.continuous = QCheckBox("Continuous (-t)")
        self.continuous.setChecked(True)
        self.continuous.setToolTip("Keep pinging continuously like Windows ping -t until Stop is pressed.")

        for label, widget in [("Target:", self.target), ("Count:", self.count)]:
            controls.addWidget(QLabel(label))
            controls.addWidget(widget)
        controls.addWidget(self.continuous)

        ping = QPushButton("Ping")
        ping.setObjectName("primaryButton")
        ping.clicked.connect(self.start_ping)
        stop = QPushButton("Stop")
        stop.clicked.connect(self.stop_ping)
        trace = QPushButton("Trace Route")
        trace.setObjectName("primaryButton")
        trace.clicked.connect(self.trace_route)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_output)

        controls.addWidget(ping)
        controls.addWidget(stop)
        controls.addWidget(trace)
        controls.addWidget(clear)
        controls.addStretch()
        root.addLayout(controls)

        cards = QHBoxLayout()
        self.ping_status = StatCard("PING STATUS", "Ready", "#2774e6")
        self.latency = StatCard("LAST LATENCY", "—", "#13a673")
        self.loss = StatCard("PACKET LOSS", "—", "#e55353")
        self.hops = StatCard("ROUTE HOPS", "—", "#7b55e8")
        for c in (self.ping_status, self.latency, self.loss, self.hops):
            cards.addWidget(c)
        root.addLayout(cards)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("""
            QTextEdit {
                background:#0e2231;
                color:#d9edf7;
                border:1px solid #29485d;
                border-radius:12px;
                padding:10px;
                font-family:Consolas, "Courier New";
                font-size:10pt;
            }
        """)
        root.addWidget(self.output, 1)

        self.summary = QLabel("Ready.")
        self.summary.setStyleSheet("color:#61798a;font-size:11px;")
        root.addWidget(self.summary)

    def _target(self):
        value = self.target.text().strip()
        if not value:
            QMessageBox.warning(self, "Target Required", "Enter an IP address or hostname.")
            return None
        return value

    def _append_live_output(self, text):
        if not text:
            return
        self.output.moveCursor(QTextCursor.End)
        self.output.insertPlainText(text)
        self.output.moveCursor(QTextCursor.End)
        self.output.ensureCursorVisible()

    def start_ping(self):
        target = self._target()
        if not target:
            return
        self.stop_ping(silent=True)
        self.output.clear()
        self._ping_target = target
        self._ping_sent = 0
        self._ping_received = 0
        self._user_stopped = False
        self.ping_status.set_value("Running")
        self.latency.set_value("—")
        self.loss.set_value("0%")
        mode = "continuous" if self.continuous.isChecked() else f"{self.count.value()} packets"
        self.summary.setText(f"Pinging {target} ({mode}) — live output auto-scrolls.")

        if platform.system().lower() == "windows":
            args = (["-t", target] if self.continuous.isChecked()
                    else ["-n", str(self.count.value()), target])
        else:
            args = (["-c", "1000000", target] if self.continuous.isChecked()
                    else ["-c", str(self.count.value()), target])

        self._ping_process.start("ping", args)

    def _read_ping_output(self):
        data = bytes(self._ping_process.readAllStandardOutput())
        if not data:
            return
        text = data.decode(errors="replace")
        self._append_live_output(text)

        # Update counters from live reply/timeout lines without waiting for ping to finish.
        reply_matches = re.findall(r"(?im)^(?:Reply from|[0-9a-f:]+.*bytes from)\b", text)
        timeout_matches = re.findall(r"(?im)^(?:Request timed out|Destination host unreachable|.*100% packet loss)", text)
        self._ping_received += len(reply_matches)
        self._ping_sent += len(reply_matches) + len(timeout_matches)

        match = re.search(r"time\s*[=<]\s*(\d+(?:\.\d+)?)\s*ms", text, re.I)
        if match:
            self.latency.set_value(f"{match.group(1)} ms")
        elif re.search(r"time\s*<\s*1\s*ms", text, re.I):
            self.latency.set_value("<1 ms")

        if self._ping_sent:
            loss = 100 - round((self._ping_received / self._ping_sent) * 100)
            self.loss.set_value(f"{loss}%")
            self.summary.setText(
                f"Pinging {self._ping_target} — {self._ping_received}/{self._ping_sent} replies received."
            )
        if self._ping_received:
            self.ping_status.set_value("Reachable")

    def _ping_finished(self, exit_code, exit_status):
        if self._user_stopped:
            return
        self.ping_status.set_value("Complete")
        if self._ping_sent:
            loss = 100 - round((self._ping_received / self._ping_sent) * 100)
            self.loss.set_value(f"{loss}%")
        self.summary.setText(
            f"Ping complete: {self._ping_received}/{self._ping_sent} replies received."
        )

    def _ping_error(self, error):
        if not self._user_stopped:
            self.ping_status.set_value("Error")
            self.summary.setText("Ping process could not be started.")

    def stop_ping(self, silent=False):
        running = self._ping_process.state() != QProcess.NotRunning
        self._user_stopped = True
        if running:
            self._ping_process.kill()
            self._ping_process.waitForFinished(700)
        if not silent:
            self.ping_status.set_value("Stopped")
            self.summary.setText("Ping stopped.")

    def trace_route(self):
        target = self._target()
        if not target:
            return
        self.stop_ping(silent=True)
        self.output.clear()
        self.hops.set_value("Running")
        self.summary.setText(f"Tracing route to {target}...")

        cmd = ["tracert", "-d", target] if platform.system().lower() == "windows" \
              else ["traceroute", "-n", target]

        try:
            result = _run_hidden(
                cmd, capture_output=True, text=True,
                errors="replace", timeout=90
            )
            output = (result.stdout or "") + (result.stderr or "")
            self.output.setPlainText(output.strip() or "No traceroute output.")
            self.output.moveCursor(QTextCursor.End)
            self.output.ensureCursorVisible()
            hop_count = len(re.findall(r"^\s*\d+\s+", output, re.MULTILINE))
            self.hops.set_value(str(hop_count) if hop_count else "—")
            self.summary.setText(
                "Trace route completed."
                if result.returncode == 0
                else "Trace route completed with warnings. See output."
            )
        except FileNotFoundError:
            self.hops.set_value("Unavailable")
            self.output.setPlainText("Traceroute utility was not found on this system.")
            self.summary.setText("Windows uses built-in tracert.")
        except subprocess.TimeoutExpired:
            self.hops.set_value("Timeout")
            self.output.setPlainText("Trace route timed out after 90 seconds.")
            self.summary.setText("Trace route timed out.")
        except Exception as exc:
            self.hops.set_value("Error")
            self.output.setPlainText(f"Error: {exc}")
            self.summary.setText("Trace route failed.")

    def clear_output(self):
        self.stop_ping(silent=True)
        self.output.clear()
        self.ping_status.set_value("Ready")
        self.latency.set_value("—")
        self.loss.set_value("—")
        self.hops.set_value("—")
        self.summary.setText("Ready.")


class DiagnosticsPage(QWidget):
    """Professional predefined Windows network diagnostics."""

    def __init__(self):
        super().__init__()
        self.process = None
        self.current_command = ""
        self._queue = []
        self._queue_index = 0
        self._target_value = ""
        self._run_all = False

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(10)

        title = QLabel("Network Diagnostics")
        title.setObjectName("pageTitle")
        sub = QLabel(
            "Enter one IP/hostname and run individual diagnostics or a complete device information check."
        )
        sub.setObjectName("pageSub")
        root.addWidget(title)
        root.addWidget(sub)

        inputs = QHBoxLayout()
        self.target = QLineEdit()
        self.target.setPlaceholderText("Example: 192.168.0.16")
        self.target.setMinimumWidth(300)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(3389)
        inputs.addWidget(QLabel("Target:"))
        inputs.addWidget(self.target, 1)
        inputs.addWidget(QLabel("Port:"))
        inputs.addWidget(self.port)
        root.addLayout(inputs)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        buttons = [
            ("IP Configuration", self.ip_config),
            ("ARP / MAC", self.arp),
            ("Route Table", self.route_table),
            ("Network Connections", self.netstat),
            ("DNS Lookup", self.dns_lookup),
            ("Hostname / Reverse DNS", self.hostname_lookup),
            ("Wi-Fi Information", self.wifi),
            ("Firewall Status", self.firewall),
            ("TCP Port Test", self.tcp_test),
            ("Ping", self.open_ping_page),
            ("Trace Route", self.open_trace_page),
            ("Run ALL Diagnostics", self.run_all),
        ]

        for i, (label, slot) in enumerate(buttons):
            b = QPushButton(label)
            if label == "Run ALL Diagnostics":
                b.setObjectName("primaryButton")
            b.clicked.connect(slot)
            grid.addWidget(b, i // 3, i % 3)
        root.addLayout(grid)

        actions = QHBoxLayout()
        for label, slot, obj in [
            ("Flush DNS", self.flush_dns, ""),
            ("Release IP", self.release_ip, ""),
            ("Renew IP", self.renew_ip, ""),
            ("Stop", self.stop_command, "dangerButton"),
            ("Clear Output", self.clear_output, ""),
            ("Save Output", self.save_output, ""),
        ]:
            b = QPushButton(label)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(slot)
            actions.addWidget(b)
        actions.addStretch()
        root.addLayout(actions)

        self.status = QLabel("Ready")
        self.status.setStyleSheet("color:#4e6b7d;font-size:11px;font-weight:650;")
        root.addWidget(self.status)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("""
            QTextEdit {
                background:#0e2231;
                color:#d9edf7;
                border:1px solid #29485d;
                border-radius:12px;
                padding:10px;
                font-family:Consolas, "Courier New";
                font-size:10pt;
            }
        """)
        root.addWidget(self.output, 1)

        note = QLabel(
            "Results depend on device permissions, firewall rules, routing and services exposed by the target."
        )
        note.setStyleSheet("color:#718696;font-size:10px;")
        root.addWidget(note)

    def target_value(self):
        value = self.target.text().strip()
        if not value:
            QMessageBox.warning(self, "Target Required", "Enter an IP address or hostname.")
            return None
        return value

    def is_windows(self):
        if platform.system().lower() != "windows":
            QMessageBox.information(
                self, "Windows Feature",
                "This diagnostic module is designed for Windows 10/11."
            )
            return False
        return True

    def start_process(self, args, name, append=False, callback=None):
        self.stop_command()
        if not append:
            self.output.clear()
        self.current_command = " ".join(args)
        self.status.setText(f"Running: {name}")

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_process_output)
        self.process.finished.connect(
            lambda code, status, cb=callback: self.process_finished(code, status, cb)
        )
        self.process.errorOccurred.connect(self.process_error)
        self.process.start(args[0], args[1:])

    def read_process_output(self):
        if not self.process:
            return
        data = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        if data:
            cursor = self.output.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.output.setTextCursor(cursor)
            self.output.insertPlainText(data)
            self.output.ensureCursorVisible()

    def process_finished(self, exit_code, exit_status, callback=None):
        self.status.setText(f"Completed • Exit code {exit_code}")
        self.process = None
        if callback:
            callback()

    def process_error(self, error):
        self.status.setText(f"Command error: {error}")
        if self.process:
            msg = self.process.errorString()
            if msg:
                self.output.append(f"\n[Error] {msg}")

    def stop_command(self):
        self._queue = []
        self._run_all = False
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(500)
        self.process = None
        if hasattr(self, "status"):
            self.status.setText("Stopped")

    def clear_output(self):
        self.stop_command()
        self.output.clear()
        self.status.setText("Ready")

    def save_output(self):
        content = self.output.toPlainText().strip()
        if not content:
            QMessageBox.information(self, "No Output", "There is no output to save.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Diagnostic Output",
            "N-Console-Network-Diagnostics.txt",
            "Text File (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("N-CONSOLE NETWORK DIAGNOSTICS\n")
                f.write(f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                f.write(f"Target: {self.target.text().strip()}\n")
                f.write(f"Last command: {self.current_command}\n\n")
                f.write(content)
            QMessageBox.information(self, "Saved", f"Output saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    def run_cmd(self, command, name):
        if self.is_windows():
            self.start_process(["cmd.exe", "/d", "/c", command], name)

    def ip_config(self):
        self.run_cmd("ipconfig /all", "IP Configuration")

    def arp(self):
        self.run_cmd("arp -a", "ARP Table / MAC")

    def route_table(self):
        self.run_cmd("route print", "Route Table")

    def netstat(self):
        self.run_cmd("netstat -ano", "Network Connections")

    def hostname_lookup(self):
        target = self.target_value()
        if not target:
            return
        if self.is_windows():
            # Reverse DNS first, then local hostname fallback is not mixed with target.
            self.start_process(
                ["nslookup.exe", target],
                f"Reverse DNS / Hostname • {target}"
            )

    def dns_lookup(self):
        target = self.target_value()
        if target and self.is_windows():
            self.start_process(["nslookup.exe", target], f"DNS Lookup • {target}")

    def wifi(self):
        self.run_cmd(
            "netsh wlan show interfaces",
            "Wi-Fi Information"
        )

    def firewall(self):
        self.run_cmd(
            "netsh advfirewall show allprofiles",
            "Firewall Status"
        )

    def tcp_test(self):
        target = self.target_value()
        if not target or not self.is_windows():
            return
        port = self.port.value()
        safe = target.replace("'", "''")
        ps = (
            f"$r=Test-NetConnection -ComputerName '{safe}' "
            f"-Port {port} -WarningAction SilentlyContinue; "
            f"$r | Select-Object ComputerName,RemoteAddress,RemotePort,"
            f"TcpTestSucceeded,Latency | Format-List"
        )
        self.start_process(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            f"TCP Port Test • {target}:{port}"
        )

    def flush_dns(self):
        if not self.is_windows():
            return
        self.run_cmd("ipconfig /flushdns", "Flush DNS")

    def release_ip(self):
        if not self.is_windows():
            return
        reply = QMessageBox.question(
            self, "Release IP",
            "Release DHCP addresses on all adapters?\nConnectivity may temporarily stop.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.run_cmd("ipconfig /release", "Release IP")

    def renew_ip(self):
        if not self.is_windows():
            return
        reply = QMessageBox.question(
            self, "Renew IP",
            "Renew DHCP addresses on all adapters?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.run_cmd("ipconfig /renew", "Renew IP")

    def open_ping_page(self):
        self.target_value()
        # MainWindow owns navigation; this signal-like method is replaced by parent traversal.
        parent = self.window()
        if hasattr(parent, "navigate"):
            parent.navigate("ping")
            if hasattr(parent, "ping_route"):
                parent.ping_route.target.setText(self.target.text().strip())

    def open_trace_page(self):
        self.target_value()
        parent = self.window()
        if hasattr(parent, "navigate"):
            parent.navigate("ping")
            if hasattr(parent, "ping_route"):
                parent.ping_route.target.setText(self.target.text().strip())
                parent.ping_route.trace_route()

    def run_all(self):
        target = self.target_value()
        if not target or not self.is_windows():
            return

        # Target-independent commands plus target-specific commands.
        self._target_value = target
        self._queue = [
            ("IP CONFIGURATION", ["cmd.exe", "/d", "/c", "ipconfig /all"]),
            ("ARP / MAC TABLE", ["cmd.exe", "/d", "/c", "arp -a"]),
            ("ROUTE TABLE", ["cmd.exe", "/d", "/c", "route print"]),
            ("NETWORK CONNECTIONS", ["cmd.exe", "/d", "/c", "netstat -ano"]),
            ("HOSTNAME / REVERSE DNS", ["nslookup.exe", target]),
        ]
        self._run_all = True
        self._queue_index = 0
        self.output.clear()
        self.run_next_diagnostic()

    def run_next_diagnostic(self):
        if not self._run_all:
            return
        if self._queue_index >= len(self._queue):
            self._run_all = False
            self.status.setText("All diagnostics completed.")
            return

        name, args = self._queue[self._queue_index]
        self._queue_index += 1
        self.output.append(
            f"\n{'='*72}\n{name}\nCOMMAND: {' '.join(args)}\n{'='*72}\n"
        )
        self.current_command = " ".join(args)

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_process_output)
        self.process.finished.connect(
            lambda code, status: self.run_next_diagnostic()
        )
        self.process.errorOccurred.connect(self.process_error)
        self.status.setText(f"Running {name}...")
        self.process.start(args[0], args[1:])



class HomePage(QWidget):
    def __init__(self, history, navigator, refresh_callback):
        super().__init__()
        self.history = history
        self.navigator = navigator
        self.refresh_callback = refresh_callback
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 26)
        root.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("hero")
        h = QHBoxLayout(hero)
        h.setContentsMargins(28, 22, 20, 20)

        left = QVBoxLayout()
        title_row = QHBoxLayout()
        title = QLabel("Welcome to N-Console")
        title.setStyleSheet("font-size:30px;font-weight:800;color:#15364e;")
        title_row.addWidget(title)
        title_row.addStretch()

        refresh = QPushButton("↻  Refresh App")
        refresh.setObjectName("primaryButton")
        refresh.setToolTip("Refresh the N-Console workspace")
        refresh.clicked.connect(self.refresh_callback)
        title_row.addWidget(refresh)
        left.addLayout(title_row)

        version = QLabel(f"Version {APP_VERSION}")
        version.setStyleSheet("color:#1769c2;font-size:11px;font-weight:700;")
        left.addWidget(version)

        desc = QLabel(
            "Professional network connectivity, remote access, discovery and audit management."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:14px;color:#557184;")
        left.addWidget(desc)
        left.addStretch()
        h.addLayout(left, 2)

        art = QLabel()
        art.setAlignment(Qt.AlignCenter)
        art.setPixmap(QPixmap(ILLUSTRATION_PATH).scaled(
            470, 315, Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        h.addWidget(art, 1)
        root.addWidget(hero)

        cards = QHBoxLayout()
        self.logged = StatCard("Saved / Logged Connections", str(len(history.rows())), "#2774e6")
        self.scanner = AnimatedReadyCard("Network Scanner", "#13a673")
        self.remote = AnimatedReadyCard("Remote Access", "#8a56e8")
        self.reports = AnimatedReadyCard("Reports", "#e94f9a")
        for c in (self.logged, self.scanner, self.remote, self.reports):
            cards.addWidget(c)
        root.addLayout(cards)
        root.addStretch()

    def update_count(self):
        self.logged.set_value(len(self.history.rows()))



class SubnetCalculatorPage(QWidget):
    """Professional IPv4 subnet calculator with full IP inventory and gateway."""

    def __init__(self):
        super().__init__()
        self.current = None
        self.current_rows = []

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(9)

        title = QLabel("Subnet Calculator")
        title.setObjectName("pageTitle")
        sub = QLabel(
            "IPv4 CIDR calculation • complete IP range • gateway • host inventory • Excel export"
        )
        sub.setObjectName("pageSub")
        root.addWidget(title)
        root.addWidget(sub)

        bar = QHBoxLayout()
        bar.setSpacing(7)
        bar.addWidget(QLabel("IP / CIDR:"))

        self.cidr = QLineEdit()
        self.cidr.setPlaceholderText("Example: 172.17.64.1/23")
        bar.addWidget(self.cidr, 1)

        bar.addWidget(QLabel("Default Gateway:"))
        self.gateway = QLineEdit()
        self.gateway.setPlaceholderText("Auto: first usable")
        self.gateway.setMaximumWidth(190)
        bar.addWidget(self.gateway)

        self.calc = QPushButton("Calculate")
        self.calc.setObjectName("primaryButton")
        self.calc.clicked.connect(self.calculate)
        bar.addWidget(self.calc)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear)
        bar.addWidget(self.clear_btn)

        self.export_btn = QPushButton("Export Excel")
        self.export_btn.clicked.connect(self.export_excel)
        self.export_btn.setEnabled(False)
        bar.addWidget(self.export_btn)

        root.addLayout(bar)

        cards = QGridLayout()
        cards.setSpacing(8)
        self.v_network = self._stat(cards, 0, 0, "NETWORK ADDRESS")
        self.v_mask = self._stat(cards, 0, 1, "SUBNET MASK")
        self.v_wild = self._stat(cards, 0, 2, "WILDCARD MASK")
        self.v_broadcast = self._stat(cards, 0, 3, "BROADCAST")
        self.v_first = self._stat(cards, 1, 0, "FIRST USABLE")
        self.v_last = self._stat(cards, 1, 1, "LAST USABLE")
        self.v_total = self._stat(cards, 1, 2, "TOTAL ADDRESSES")
        self.v_usable = self._stat(cards, 1, 3, "USABLE HOSTS")
        root.addLayout(cards)

        self.gateway_info = QLabel("Default Gateway: Auto = first usable IP")
        self.gateway_info.setStyleSheet("color:#1769c2;font-size:11px;font-weight:600;")
        root.addWidget(self.gateway_info)

        self.info = QLabel("Enter an IPv4 CIDR and click Calculate.")
        self.info.setStyleSheet("color:#61798a;font-size:10px;")
        root.addWidget(self.info)

        # Complete address inventory. Large ranges are loaded in chunks so the
        # interface remains responsive.
        self.table = QTableWidget(0, 5)
        self.table.setObjectName("scannerTable")
        self.table.setHorizontalHeaderLabels([
            "No.", "IP Address", "Type", "Usable", "Default Gateway"
        ])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        for i, w in enumerate([80, 180, 150, 100, 180]):
            self.table.setColumnWidth(i, w)

        root.addWidget(self.table, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

    def _stat(self, grid, row, col, label):
        frame = QFrame()
        frame.setObjectName("statCard")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 8, 12, 8)

        a = QLabel(label)
        a.setStyleSheet("color:#607789;font-size:10px;border:none;")

        b = QLabel("-")
        b.setStyleSheet(
            "color:#1769c2;font-size:18px;font-weight:800;border:none;"
        )

        lay.addWidget(a)
        lay.addWidget(b)
        grid.addWidget(frame, row, col)
        return b

    @staticmethod
    def address_class(ip):
        first = int(str(ip).split(".")[0])
        if 1 <= first <= 126:
            return "Class A"
        if 128 <= first <= 191:
            return "Class B"
        if 192 <= first <= 223:
            return "Class C"
        if 224 <= first <= 239:
            return "Class D (Multicast)"
        if 240 <= first <= 255:
            return "Class E (Reserved)"
        return "Special"

    @staticmethod
    def host_values(net):
        total = net.num_addresses
        if net.prefixlen <= 30:
            usable = max(total - 2, 0)
            first = str(net.network_address + 1)
            last = str(net.broadcast_address - 1)
        elif net.prefixlen == 31:
            usable = 2
            first = str(net.network_address)
            last = str(net.broadcast_address)
        else:
            usable = 1
            first = str(net.network_address)
            last = str(net.network_address)
        return total, usable, first, last

    def _gateway_for(self, net, first, last):
        """Validate custom gateway; otherwise use first usable."""
        requested = self.gateway.text().strip()
        if not requested:
            return first

        try:
            gw = ipaddress.ip_address(requested)
        except ValueError:
            QMessageBox.warning(
                self, "Invalid Gateway",
                "Default Gateway must be a valid IPv4 address."
            )
            return None

        if gw.version != 4 or gw not in net:
            QMessageBox.warning(
                self, "Gateway Outside Network",
                f"{gw} is not inside {net}."
            )
            return None

        # Network/broadcast are not valid ordinary host gateway addresses.
        if net.prefixlen <= 30 and gw in (net.network_address, net.broadcast_address):
            QMessageBox.warning(
                self, "Invalid Gateway",
                "Gateway cannot be the network or broadcast address."
            )
            return None

        return str(gw)

    def calculate(self):
        raw = self.cidr.text().strip()
        if not raw:
            return

        try:
            net = ipaddress.ip_network(raw, strict=False)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid CIDR", str(exc))
            return

        if net.version != 4:
            QMessageBox.warning(self, "IPv4 Only", "Please enter an IPv4 network.")
            return

        total, usable, first, last = self.host_values(net)
        gateway = self._gateway_for(net, first, last)
        if gateway is None:
            return

        cls = self.address_class(net.network_address)

        self.v_network.setText(str(net.network_address))
        self.v_mask.setText(str(net.netmask))
        self.v_wild.setText(str(net.hostmask))
        self.v_broadcast.setText(str(net.broadcast_address))
        self.v_first.setText(first)
        self.v_last.setText(last)
        self.v_total.setText(f"{total:,}")
        self.v_usable.setText(f"{usable:,}")

        self.gateway_info.setText(
            f"Default Gateway: {gateway}  •  "
            f"{'Auto (first usable)' if not self.gateway.text().strip() else 'Custom'}"
        )

        self.table.setRowCount(0)
        self.current_rows = []
        self.current = (net, gateway)

        # /0 contains over 4 billion addresses and should not be materialized
        # into a GUI table. We still provide exact summary data and Excel
        # export, while complete lists are safely shown for practical ranges.
        max_gui_rows = 100000
        show_count = min(total, max_gui_rows)

        self.progress.setVisible(total > 5000)
        self.progress.setValue(0)

        self.table.setUpdatesEnabled(False)
        try:
            for idx in range(show_count):
                ip = net.network_address + idx

                if net.prefixlen <= 30:
                    if ip == net.network_address:
                        kind = "Network"
                        usable_text = "No"
                    elif ip == net.broadcast_address:
                        kind = "Broadcast"
                        usable_text = "No"
                    else:
                        kind = "Host"
                        usable_text = "Yes"
                elif net.prefixlen == 31:
                    kind = "Point-to-Point"
                    usable_text = "Yes"
                else:
                    kind = "Host"
                    usable_text = "Yes"

                is_gateway = str(ip) == gateway
                gateway_text = "YES" if is_gateway else gateway

                r = self.table.rowCount()
                self.table.insertRow(r)
                values = [
                    str(idx + 1),
                    str(ip),
                    kind,
                    usable_text,
                    gateway_text,
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if is_gateway and col in (1, 2, 4):
                        item.setForeground(QColor("#1769c2"))
                        item.setFont(QFont("", -1, QFont.Bold))
                    self.table.setItem(r, col, item)

                self.current_rows.append(
                    [idx + 1, str(ip), kind, usable_text, gateway]
                )

                if total > 5000 and idx % 500 == 0:
                    self.progress.setValue(int((idx + 1) * 100 / total))
                    QApplication.processEvents()
        finally:
            self.table.setUpdatesEnabled(True)

        self.progress.setValue(100)
        self.progress.setVisible(total > 5000)

        if total > max_gui_rows:
            self.info.setText(
                f"{cls} • CIDR /{net.prefixlen} • {total:,} total addresses • "
                f"{usable:,} usable hosts • Gateway {gateway} • "
                f"GUI list limited to first {max_gui_rows:,} addresses for performance; "
                f"Excel export can contain the full range."
            )
        else:
            self.info.setText(
                f"{cls} • CIDR /{net.prefixlen} • "
                f"Range {net.network_address} – {net.broadcast_address} • "
                f"{total:,} total addresses • {usable:,} usable hosts • "
                f"Gateway {gateway}"
            )

        self.export_btn.setEnabled(True)

    def clear(self):
        self.cidr.clear()
        self.gateway.clear()
        self.table.setRowCount(0)
        self.current = None
        self.current_rows = []
        self.export_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setVisible(False)

        for x in (
            self.v_network, self.v_mask, self.v_wild, self.v_broadcast,
            self.v_first, self.v_last, self.v_total, self.v_usable
        ):
            x.setText("-")

        self.gateway_info.setText("Default Gateway: Auto = first usable IP")
        self.info.setText("Enter an IPv4 CIDR and click Calculate.")

    def export_excel(self):
        if not self.current:
            return

        net, gateway = self.current

        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
            from datetime import datetime

            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Complete Subnet Report",
                f"N-Console-Subnet-{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                "Excel Workbook (*.xlsx)"
            )
            if not path:
                return

            wb = Workbook()

            # Summary sheet
            ws = wb.active
            ws.title = "Subnet Summary"
            ws.sheet_view.showGridLines = False

            ws.merge_cells("A1:K1")
            ws["A1"] = "N-CONSOLE SUBNET CALCULATION REPORT"
            ws["A1"].font = Font(size=16, bold=True, color="FFFFFF")
            ws["A1"].fill = PatternFill("solid", fgColor="1769D1")
            ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[1].height = 28

            summary = [
                ("Input", self.cidr.text().strip()),
                ("Network Address", str(net.network_address)),
                ("CIDR", f"/{net.prefixlen}"),
                ("Subnet Mask", str(net.netmask)),
                ("Wildcard Mask", str(net.hostmask)),
                ("Broadcast", str(net.broadcast_address)),
                ("First Usable", self.v_first.text()),
                ("Last Usable", self.v_last.text()),
                ("Total Addresses", net.num_addresses),
                ("Usable Hosts", self.v_usable.text()),
                ("Address Class", self.address_class(net.network_address)),
                ("Default Gateway", gateway),
                ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ]

            for r, (key, value) in enumerate(summary, start=3):
                ws.cell(r, 1, key)
                ws.cell(r, 2, value)
                ws.cell(r, 1).font = Font(bold=True)
                ws.cell(r, 1).fill = PatternFill("solid", fgColor="EAF3FA")

            # Complete IP inventory sheet.
            inv = wb.create_sheet("Complete IP List")
            inv.sheet_view.showGridLines = False

            headers = ["No.", "IP Address", "Type", "Usable", "Default Gateway"]
            for col, value in enumerate(headers, 1):
                cell = inv.cell(1, col, value)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="2878B5")
                cell.alignment = Alignment(horizontal="center", vertical="center")

            # Write the entire range to Excel, including large networks.
            # For extremely large /0-/8 networks, Excel's row limit applies;
            # stop safely at the Excel maximum rather than crashing.
            max_excel_data_rows = 1048575
            count = min(net.num_addresses, max_excel_data_rows)

            inv.freeze_panes = "A2"
            inv.auto_filter.ref = f"A1:E{count + 1}"

            for idx in range(count):
                ip = net.network_address + idx

                if net.prefixlen <= 30:
                    if ip == net.network_address:
                        kind = "Network"
                        usable_text = "No"
                    elif ip == net.broadcast_address:
                        kind = "Broadcast"
                        usable_text = "No"
                    else:
                        kind = "Host"
                        usable_text = "Yes"
                elif net.prefixlen == 31:
                    kind = "Point-to-Point"
                    usable_text = "Yes"
                else:
                    kind = "Host"
                    usable_text = "Yes"

                row = idx + 2
                inv.cell(row, 1, idx + 1)
                inv.cell(row, 2, str(ip))
                inv.cell(row, 3, kind)
                inv.cell(row, 4, usable_text)
                inv.cell(row, 5, gateway)

                if str(ip) == gateway:
                    for col in range(1, 6):
                        inv.cell(row, col).font = Font(bold=True, color="1769C2")

                if idx % 5000 == 0:
                    QApplication.processEvents()

            thin = Side(style="thin", color="D9E2EC")
            for sheet in (ws, inv):
                for row_cells in sheet.iter_rows():
                    for cell in row_cells:
                        cell.border = Border(bottom=thin)
                        cell.alignment = Alignment(vertical="center", wrap_text=False)

            # Auto-fit widths based on actual content, bounded for readability.
            for sheet in (ws, inv):
                for col in range(1, sheet.max_column + 1):
                    letter = get_column_letter(col)
                    max_len = 0
                    for cell in sheet[letter]:
                        max_len = max(max_len, len(str(cell.value or "")))
                    sheet.column_dimensions[letter].width = min(
                        max(max_len + 3, 12), 34
                    )

            wb.save(path)

            QMessageBox.information(
                self,
                "Excel Generated",
                f"Complete subnet report saved successfully:\n{path}"
            )

        except ImportError:
            QMessageBox.warning(
                self,
                "Excel Support Missing",
                "Install Excel support with:\npy -m pip install openpyxl"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Excel Error", str(exc))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setWindowIcon(QIcon(ICON_PATH))
        self.history = HistoryDB()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(245)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(18,22,18,20)

        row = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(QPixmap(ICON_PATH).scaled(48,48,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        row.addWidget(ico)
        name = QLabel(APP_NAME)
        name.setStyleSheet("font-size:21px;font-weight:900;color:#fff;")
        row.addWidget(name)
        row.addStretch()
        sl.addLayout(row)

        dev = QLabel(DEVELOPER)
        dev.setWordWrap(True)
        dev.setStyleSheet("color:#c5d9e5;font-size:10px;")
        sl.addWidget(dev)
        sl.addSpacing(18)

        self.stack = QStackedWidget()
        self.home = HomePage(self.history, self.navigate, self.refresh_app)
        self.scanner = ScannerPage()
        self.ping_route = PingRoutePage()
        self.telnet_page = TelnetPage()
        self.serial_page = SerialPage()
        self.subnet_page = SubnetCalculatorPage()
        self.ssh_page = SSHPage()
        self.diagnostics = DiagnosticsPage()
        self.history_page = HistoryPage(self.history)
        self.pages = {
            "home": self.home,
            "scanner": self.scanner,
            "ping": self.ping_route,
            "telnet": self.telnet_page,
            "serial": self.serial_page,
            "subnet": self.subnet_page,
            "ssh": self.ssh_page,
            "diagnostics": self.diagnostics,
            "history": self.history_page
        }
        for p in self.pages.values():
            self.stack.addWidget(p)

        self.history_page.history_changed.connect(self.home.update_count)

        for text, key in [
            ("Dashboard","home"), ("SSH / Terminal","SSH"), ("Telnet","telnet"), ("Serial Console","serial"),
            ("Remote Access","RDP"), ("IP Scanner","scanner"), ("Subnet Calculator","subnet"),
            ("Ping & Route","ping"), ("Network Diagnostics","diagnostics"),
            ("Connection History","history")
        ]:
            b = QPushButton(text)
            b.setObjectName("navButton")
            b.clicked.connect(lambda checked=False, k=key: self.navigate(k))
            sl.addWidget(b)

        sl.addStretch()
        foot = QLabel(f"{APP_NAME} {APP_VERSION}\n{DEVELOPER}")
        foot.setStyleSheet("color:#91aebe;font-size:9px;")
        sl.addWidget(foot)

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        self.navigate("home")

    def refresh_app(self):
        """Refresh the whole N-Console workspace without restarting the process."""
        try:
            # Stop active scanner work and clear its visible state.
            if getattr(self.scanner, "scanning", False):
                self.scanner.cancel_scan()
            self.scanner.clear()

            # Reset diagnostics/ping state where supported.
            if hasattr(self.ping_route, "stop_ping"):
                self.ping_route.stop_ping()
            if hasattr(self.ping_route, "clear_output"):
                self.ping_route.clear_output()

            # Refresh history and dashboard counters.
            self.history_page.load()
            self.home.update_count()

            # Return to the dashboard after the refresh.
            self.stack.setCurrentWidget(self.home)
            QApplication.processEvents()
        except Exception as exc:
            QMessageBox.warning(self, "Refresh App", f"Refresh completed with a warning:\n{exc}")

    def navigate(self, key):
        if key in ("SSH", "Telnet", "RDP"):
            ConnectionDialog(key, self.history, self).exec()
            self.home.update_count()
            self.history_page.load()
            return
        self.stack.setCurrentWidget(self.pages[key])
        if key == "history":
            self.history_page.load()

    def open_telnet(self, host, port=23):
        self.stack.setCurrentWidget(self.telnet_page)
        self.telnet_page.host_edit.setText(str(host))
        self.telnet_page.port_edit.setValue(int(port))
        self.telnet_page.connect_to_target(str(host), int(port))

    def open_ssh(self, host, port=22, username="", password=""):
        self.stack.setCurrentWidget(self.ssh_page)
        self.ssh_page.configure_target(host, port, username, password)
        self.ssh_page.connect_ssh()

    def open_rdp(self, host, port=3389):
        if platform.system().lower() != "windows":
            raise RuntimeError("Windows Remote Desktop is available only on Windows.")
        if not shutil.which("mstsc.exe"):
            raise RuntimeError("mstsc.exe is not available on this Windows installation.")
        subprocess.Popen(["mstsc.exe", f"/v:{host}:{port}"])


def theme(app):
    app.setStyleSheet("""
        QWidget {
            font-family:"Segoe UI";
            font-size:10pt;
            color:#18384d;
        }
        QMainWindow, QStackedWidget {
            background:#f4f9fd;
        }

        QFrame#sidebar {
            background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 #102f46,stop:.55 #155a83,stop:1 #2476aa);
        }

        QFrame#hero {
            background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #e9f8ff,stop:.48 #f4efff,stop:1 #fff0f7);
            border:1px solid #d8e6ef;
            border-radius:22px;
        }

        QFrame#statCard {
            background:#ffffff;
            border:1px solid #d9e7f1;
            border-radius:16px;
        }
        QLabel#statTitle {
            color:#607789;
            font-size:11px;
            font-weight:650;
            border:none;
            background:transparent;
        }
        QLabel#statValue {
            border:none;
            background:transparent;
        }

        QPushButton {
            background:#ffffff;
            border:1px solid #d2e1eb;
            border-radius:10px;
            color:#23455b;
            padding:8px 13px;
            font-weight:650;
        }
        QPushButton:hover {
            background:#edf7ff;
            border-color:#8ec9ec;
        }

        QPushButton#primaryButton {
            border:none;
            color:#ffffff;
            padding:9px 15px;
            border-radius:10px;
            font-weight:750;
            background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #087fca,stop:.45 #4169e8,stop:1 #8a56e8);
        }
        QPushButton#primaryButton:hover {
            background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #076da9,stop:.45 #3659d1,stop:1 #7746cf);
        }

        QPushButton#secondaryButton {
            background:#ffffff;
            color:#31556b;
        }

        QPushButton#dangerButton {
            color:#b52f3a;
            border-color:#efb6bc;
        }

        QPushButton#navButton {
            text-align:left;
            border:none;
            background:transparent;
            color:#e5f2fa;
            padding:12px 14px;
            border-radius:9px;
            font-weight:650;
        }
        QPushButton#navButton:hover {
            background:rgba(255,255,255,.13);
            color:#ffffff;
        }

        QLabel#pageTitle {
            font-size:27px;
            font-weight:850;
            color:#173b53;
            background:transparent;
            border:none;
        }
        QLabel#pageSub {
            color:#668092;
            font-size:12px;
            background:transparent;
            border:none;
        }

        QLineEdit,QSpinBox {
            background:#ffffff;
            border:1px solid #cddde8;
            border-radius:9px;
            padding:8px;
        }

        QCheckBox {
            color:#476477;
            spacing:5px;
        }

        QTableWidget#scannerTable {
            background:#ffffff;
            border:1px solid #d5e3ed;
            border-radius:12px;
            gridline-color:#e3edf3;
            alternate-background-color:#f7fbfe;
            selection-background-color:#dceeff;
            selection-color:#173b53;
        }
        QTableWidget#scannerTable::item {
            padding:5px;
        }

        QHeaderView::section {
            background:#eaf4fa;
            color:#274d63;
            border:none;
            border-bottom:1px solid #d6e4ed;
            padding:9px 7px;
            font-weight:750;
        }

        QProgressBar {
            border:none;
            border-radius:7px;
            background:#deebf3;
            text-align:center;
            color:#21445b;
            font-weight:650;
        }
        QProgressBar::chunk {
            border-radius:7px;
            background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #00a6e8,stop:.35 #2f7df6,
                stop:.68 #7b5cff,stop:1 #ef4fa8);
        }
    """)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("N-Console")
    app.setWindowIcon(QIcon(ICON_PATH))
    theme(app)

    splash = SplashScreen()
    window = MainWindow()

    def start():
        splash.close()
        window.showMaximized()
        window.raise_()
        window.activateWindow()

    splash.finished.connect(start)
    splash.show()
    sys.exit(app.exec())

    def open_telnet(self, host, port=23):
        """Open the built-in Telnet terminal for an IP/port."""
        if hasattr(self, "navigate"):
            self.navigate("telnet")
        page = getattr(self, "telnet_page", None)
        if page is not None:
            page.configure_target(host, port)
            page.connect_to_target()


if __name__ == "__main__":
    main()
