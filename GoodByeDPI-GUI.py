import sys
import json
import subprocess
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLabel, QLineEdit, QCheckBox, QPushButton, QScrollArea,
    QSpinBox, QComboBox, QTextEdit, QSystemTrayIcon,
    QMenu, QMessageBox
)
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QIcon, QAction, QCloseEvent
import ctypes
import time
import winsound


CONFIG_FILE = "profile.json"

# noinspection SpellCheckingInspection
MODES = {
    "-1": {"-p": True, "-r": True, "-s": True, "-f": 2, "-k": 2, "-n": True, "-e": 2},
    "-2": {"-p": True, "-r": True, "-s": True, "-f": 2, "-k": 2, "-n": True, "-e": 40},
    "-3": {"-p": True, "-r": True, "-s": True, "-e": 40},
    "-4": {"-p": True, "-r": True, "-s": True},
    "-5": {"-f": 2, "-e": 2, "--auto-ttl": "1-4-10", "--reverse-frag": True, "--max-payload": 1200},
    "-6": {"-f": 2, "-e": 2, "--wrong-seq": True, "--reverse-frag": True, "--max-payload": 1200},
}

class GoodbyeDPIGUI(QWidget):
    output_signal = Signal(str)
    def __init__(self):
        super().__init__()
        self.mode_combo = QComboBox()
        self.output_connected = False
        self.command = None
        self.exiting = False
        self.exception_msg = None
        self.icon_update_thread = QThread()
        self.command_runner = QThread()
        self.message_box = QMessageBox()

        self.icon_update_thread.run = self.update_tray_icon
        self.setWindowTitle("GoodbyeDPI-GUI v1.0")
        self.setWindowIcon(QIcon(r"Resources\Icon1.ico"))
        self.setMinimumSize(800, 800)
        self.checkbox_flags = {}
        self.spin_values = {}
        self.line_values = {}

        self.tray = None
        self.runner = None

        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.scroll_layout = QVBoxLayout(content)

        self.create_menu_buttons()
        self.add_groups()

        run_box = QHBoxLayout()
        self.run_button = QPushButton("✅Run GoodByeDPI")
        self.run_button.clicked.connect(self.run_goodbyedpi)
        self.stop_button = QPushButton("❌Stop GoodByeDPI")
        self.stop_button.clicked.connect(self.manual_stop)
        run_box.addWidget(self.run_button)
        run_box.addWidget(self.stop_button)

        self.output_box = QTextEdit()
        self.output_box.setStyleSheet("""
    QTextEdit {
        border: 1px solid gray;
        outline: none;
    }

    QTextEdit:focus {
        border: 1px solid gray;
        outline: none;
    }
""")
        self.output_box.setMinimumHeight(200)
        self.output_box.setReadOnly(True)

        self.scroll_layout.addLayout(run_box)
        self.scroll_layout.addWidget(QLabel("Output:"))
        self.scroll_layout.addWidget(self.output_box)

        scroll.setWidget(content)
        layout.addWidget(scroll)
        # Tray Icon Setup
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon(r"Resources/Icon1.ico"))
        self.tray_menu = QMenu()
        self.start = QAction(QIcon(r"Resources/Icon1.ico"), "Start GoodByeDPI")
        self.start.triggered.connect(self.run_goodbyedpi)
        self.stop = QAction(QIcon(r"Resources/forbidden.ico"), "Stop GoodByeDPI")
        self.stop.triggered.connect(self.manual_stop)
        self.tray_menu.addSeparator()
        self.quit_app = QAction(QIcon(r"Resources/exit.ico"), "Quit")
        self.quit_app.triggered.connect(self.shutting_down)
        self.tray_menu.addAction(self.start)
        self.tray_menu.addAction(self.stop)
        self.tray_menu.addAction(self.quit_app)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.setToolTip("GoodByeDPI-GUI")
        (self.tray.activated.
         connect(lambda reason: self.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None))
        self.tray.show()
        self.auto_load_last_profile()
        self.run_goodbyedpi()
        self.icon_update_thread.start()

    def exception_show_msg(self):
        warning_message_box = QMessageBox()
        warning_message_box.setWindowTitle("GoodByeDPI-GUI Error")
        warning_message_box.setWindowIcon(QIcon(r"Resources\Icon1.ico"))
        warning_message_box.setFixedSize(400, 200)
        warning_message_box.setIcon(QMessageBox.Icon.Critical)
        warning_message_box.setText(f"{self.exception_msg}")
        winsound.MessageBeep()
        warning_message_box.exec()

    # noinspection SpellCheckingInspection
    def manual_stop(self):
        self.command_runner.terminate()
        subprocess.call(["taskkill", "/f", "/im", "goodbyedpi.exe"],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        shell=True)
        self.output_box.clear()
        self.output_box.append("GoodByeDPI Stopped...")

    def closeEvent(self, event: QCloseEvent):
        self.on_close()
        event.ignore()

    def on_close(self):
        self.hide()

    # noinspection SpellCheckingInspection
    def shutting_down(self):
        self.exiting = True
        self.tray.setToolTip("Shutting Down")
        subprocess.call(["taskkill", "/f", "/im", "goodbyedpi.exe"],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        shell=True)
        time.sleep(3)
        QApplication.instance().quit()

    def create_menu_buttons(self):
        menu = QHBoxLayout()
        save_btn = QPushButton("💾 Save Profile")
        load_btn = QPushButton("📂 Load Profile")
        save_btn.clicked.connect(self.save_profile)
        load_btn.clicked.connect(self.load_profile)
        menu.addWidget(save_btn)
        menu.addWidget(load_btn)
        self.scroll_layout.addLayout(menu)

    def add_groups(self):
        self.scroll_layout.addWidget(self.create_basic_options())
        self.scroll_layout.addWidget(self.create_http_options())
        self.scroll_layout.addWidget(self.create_https_options())
        self.scroll_layout.addWidget(self.create_dns_options())
        self.scroll_layout.addWidget(self.create_fake_request_options())
        self.scroll_layout.addWidget(self.create_legacy_modeset_group())

    # noinspection SpellCheckingInspection
    def create_basic_options(self):
        return self.create_checkbox_group("Basic Options", {
            "-p": "Block passive DPI",
            "-q": "Block QUIC/HTTP3",
            "-r": "Replace Host with hoSt",
            "-s": "Remove space after host header",
            "-m": "Mix Host header case"
        })

    def create_http_options(self):
        group = QGroupBox("HTTP Fragmentation")
        layout = QFormLayout()
        self.spin_values["-f"] = self.add_spin(layout, "-f")
        self.spin_values["-f"].setToolTip("<value>  set HTTP fragmentation to value")
        self.spin_values["-k"] = self.add_spin(layout, "-k")
        self.spin_values["-k"].setToolTip("<value> enable HTTP persistent (keep-alive) fragmentation"
                                          " and set it to value")
        self.checkbox_flags["-n"] = self.add_checkbox(layout, "-n")
        self.checkbox_flags["-n"].setToolTip("do not wait for first segment ACK when -k is enabled")
        self.checkbox_flags["-a"] = self.add_checkbox(layout, "-a")
        self.checkbox_flags["-a"].setToolTip("additional space between Method and Request-URI"
                                             " (enables -s, may break sites)")
        self.checkbox_flags["-w"] = self.add_checkbox(layout, "-w")
        self.checkbox_flags["-w"].setToolTip("try to find and parse HTTP traffic on all processed ports"
                                             " (not only on port 80)")
        group.setLayout(layout)
        return group

    # noinspection SpellCheckingInspection
    def create_https_options(self):
        group = QGroupBox("HTTPS Options")
        layout = QFormLayout()
        self.spin_values["-e"] = self.add_spin(layout, "-e")
        self.spin_values["-e"].setToolTip("<value>  set HTTPS fragmentation to value")
        self.line_values["--port"] = self.add_line(layout, "--port")
        self.line_values["--port"].setToolTip("<value> additional TCP port to perform fragmentation"
                                              " on (and HTTP tricks with -w)")
        self.line_values["--ip-id"] = self.add_line(layout, "--ip-id")
        self.line_values["--ip-id"].setToolTip("<value> handle additional IP ID (decimal, drop redirects and TCP RSTs"
                                               " with this ID) This option can be supplied multiple times.")
        self.line_values["--set-ttl"] = self.add_line(layout, "--set-ttl")
        self.line_values["--set-ttl"].setToolTip("<value> activate Fake Request Mode and send it with supplied TTL"
                                                 " value. DANGEROUS! May break websites in unexpected ways."
                                                 " Use with care (or --blacklist).")
        self.line_values["--auto-ttl"] = self.add_line(layout, "--auto-ttl")
        self.line_values["--auto-ttl"].setToolTip("[a1-a2-m]  activate Fake Request Mode, automatically detect TTL"
                                                  " and decrease it based on a distance. If the distance is shorter"
                                                  " than a2, TTL is decreased by a2. If it's longer, (a1; a2) scale is"
                                                  " used with the distance as a weight. If the resulting TTL is more"
                                                  " than m(ax), set it to m. Default (if set): --auto-ttl 1-4-10."
                                                  " Also sets --min-ttl 3. DANGEROUS! May break websites in unexpected"
                                                  " ways. Use with care (or --blacklist).")
        self.spin_values["--min-ttl"] = self.add_spin(layout, "--min-ttl")
        self.spin_values["--min-ttl"].setToolTip("<value>    minimum TTL distance (128/64 - TTL) for which to send Fake"
                                                 " Request in --set-ttl and --auto-ttl modes.")
        self.spin_values["--max-payload"] = self.add_spin(layout, "--max-payload")
        self.spin_values["--max-payload"].setToolTip("[value]    packets with TCP payload data more than [value] won't"
                                                     " be processed. Use this option to reduce CPU usage by skipping"
                                                     " huge amount of data (like file transfers) in already established"
                                                     " sessions. May skip some huge HTTP requests from being processed."
                                                     " Default (if set): --max-payload 1200.")
        self.line_values["--blacklist"] = self.add_line(layout, "--blacklist")
        self.line_values["--blacklist"].setToolTip("<txtfile> perform circumvention tricks only to host names and"
                                                   " subdomains from supplied text file (HTTP Host/TLS SNI)."
                                                   " This option can be supplied multiple times.")
        self.checkbox_flags["--frag-by-sni"] = self.add_checkbox(layout, "--frag-by-sni")
        self.checkbox_flags["--frag-by-sni"].setToolTip("if SNI is detected in TLS packet, fragment the packet right"
                                                        " before SNI value.")
        self.checkbox_flags["--native-frag"] = self.add_checkbox(layout, "--native-frag")
        self.checkbox_flags["--native-frag"].setToolTip("fragment (split) the packets by sending them in smaller"
                                                        " packets, without shrinking the Window Size. Works faster"
                                                        " (does not slow down the connection) and better.")
        self.checkbox_flags["--reverse-frag"] = self.add_checkbox(layout, "--reverse-frag")
        self.checkbox_flags["--reverse-frag"].setToolTip("fragment (split) the packets just as --native-frag,"
                                                         " but send them in the reversed order. Works with the websites"
                                                         " which could not handle segmented HTTPS TLS ClientHello"
                                                         " (because they receive the TCP flow 'combined'")
        group.setLayout(layout)
        return group

    # noinspection SpellCheckingInspection
    def create_dns_options(self):
        group = QGroupBox("DNS Redirection")
        layout = QFormLayout()
        self.line_values["--dns-addr"] = self.add_line(layout, "--dns-addr")
        self.line_values["--dns-addr"].setToolTip("<value> redirect UDP DNS requests to the supplied IP address"
                                                  " (experimental)")
        self.spin_values["--dns-port"] = self.add_spin(layout, "--dns-port")
        self.spin_values["--dns-port"].setToolTip("<value> redirect UDP DNS requests to the supplied port"
                                                  " (53 by default)")
        self.line_values["--dnsv6-addr"] = self.add_line(layout, "--dnsv6-addr")
        self.line_values["--dnsv6-addr"].setToolTip("<value> redirect UDPv6 DNS requests to the supplied IPv6 address"
                                                    " (experimental)")
        self.spin_values["--dnsv6-port"] = self.add_spin(layout, "--dnsv6-port")
        self.spin_values["--dnsv6-port"].setToolTip("<value> redirect UDPv6 DNS requests to the supplied port"
                                                    " (53 by default)")
        self.checkbox_flags["--dns-verb"] = self.add_checkbox(layout, "--dns-verb")
        self.checkbox_flags["--dns-verb"].setToolTip("print verbose DNS redirection messages")
        group.setLayout(layout)
        return group

    # noinspection SpellCheckingInspection
    def create_fake_request_options(self):
        group = QGroupBox("Fake Request Options")
        layout = QFormLayout()
        self.line_values["--fake-from-hex"] = self.add_line(layout, "--fake-from-hex")
        self.line_values["--fake-from-hex"].setToolTip("<value> Load fake packets for Fake Request Mode from HEX values"
                                                       " (like 1234abcDEF). This option can be supplied multiple times,"
                                                       " in this case each fake packet would be sent on every request"
                                                       " in the command line argument order.")
        self.line_values["--fake-with-sni"] = self.add_line(layout, "--fake-with-sni")
        self.line_values["--fake-with-sni"].setToolTip("<value>  Generate fake packets for Fake Request Mode with given"
                                                       " SNI domain name. The packets mimic Mozilla Firefox 130 TLS"
                                                       " ClientHello packet (with random generated fake SessionID, key"
                                                       " shares and ECH grease). Can be supplied multiple times for"
                                                       " multiple fake packets.")
        self.spin_values["--fake-gen"] = self.add_spin(layout, "--fake-gen")
        self.spin_values["--fake-gen"].setToolTip("<value> Generate random-filled fake packets for Fake Request Mode,"
                                                  " value of them (up to 30).")
        self.spin_values["--fake-resend"] = self.add_spin(layout, "--fake-resend")
        self.spin_values["--fake-resend"].setToolTip("<value> Send each fake packet value number of times."
                                                     " Default: 1 (send each packet once).")
        self.checkbox_flags["--wrong-chksum"] = self.add_checkbox(layout, "--wrong-chksum")
        self.checkbox_flags["--wrong-chksum"].setToolTip("activate Fake Request Mode and send it with incorrect TCP"
                                                         " checksum. May not work in a VM or with some routers,"
                                                         " but is safer than set-ttl.")
        self.checkbox_flags["--wrong-seq"] = self.add_checkbox(layout, "--wrong-seq")
        self.checkbox_flags["--wrong-seq"].setToolTip("activate Fake Request Mode and send it with TCP SEQ/ACK"
                                                      " in the past.")
        group.setLayout(layout)
        return group

    # noinspection SpellCheckingInspection
    def create_legacy_modeset_group(self):
        group = QGroupBox("Preset Modes")
        layout = QHBoxLayout()
        self.mode_combo.addItems([""] + list(MODES.keys()))
        self.mode_combo.currentTextChanged.connect(self.update_tooltip)
        self.mode_combo.currentTextChanged.connect(self.apply_modeset)
        layout.addWidget(QLabel("Select Modeset:"))
        layout.addWidget(self.mode_combo)
        group.setLayout(layout)
        return group

    def update_tooltip(self):
        selected_mode = self.mode_combo.currentText()

        # If a valid mode is selected
        if selected_mode in MODES:
            mode_details = MODES[selected_mode]

            # Build a string representation of the key-value pairs for the tooltip
            tooltip_text = "\n".join([f"{key}: {value}" for key, value in mode_details.items()])

            # Set the tooltip with the formatted key-value pairs
            self.mode_combo.setToolTip(f"Command details:\n{tooltip_text}")
        else:
            self.mode_combo.setToolTip("")  # Clear tooltip if no valid mode is selected

    # noinspection SpellCheckingInspection
    def apply_modeset(self, mode):
        for box in self.checkbox_flags.values():
            box.setChecked(False)
        for box in self.spin_values.values():
            box.setValue(0)
        for line in self.line_values.values():
            line.setText("")

        config = MODES.get(mode, {})
        for key, value in config.items():
            if key in self.checkbox_flags and value is True:
                self.checkbox_flags[key].setChecked(True)
            elif key in self.spin_values and isinstance(value, int):
                self.spin_values[key].setValue(value)
            elif key in self.line_values and isinstance(value, str):
                self.line_values[key].setText(value)

    @staticmethod
    def add_checkbox(layout, flag):
        cb = QCheckBox(flag)
        layout.addRow(cb)
        return cb

    @staticmethod
    def add_line(layout, label):
        le = QLineEdit()
        layout.addRow(label, le)
        return le

    def add_spin(self, layout, label):
        spin = QSpinBox()
        spin.wheelEvent = self.ignore_wheel_event
        spin.setMaximum(9999)
        layout.addRow(label, spin)
        return spin

    @staticmethod
    def ignore_wheel_event(event):
        # Prevent the wheel event from affecting the spin box value
        event.ignore()

    def create_checkbox_group(self, title, options):
        group = QGroupBox(title)
        layout = QVBoxLayout()
        for flag, label in options.items():
            cb = QCheckBox(label)
            layout.addWidget(cb)
            self.checkbox_flags[flag] = cb
        group.setLayout(layout)
        return group

    # noinspection PyTypeChecker,SpellCheckingInspection
    def save_profile(self):
        if CONFIG_FILE:
            profile = {
                "modeset": self.mode_combo.currentText(),
                "checkbox_flags": {k: v.isChecked() for k, v in self.checkbox_flags.items()},
                "spin_values": {k: v.value() for k, v in self.spin_values.items()},
                "line_values": {k: v.text() for k, v in self.line_values.items()}
            }
            with open(CONFIG_FILE, "w") as f:
                json.dump(profile, f, indent=2)

    # noinspection SpellCheckingInspection
    def load_profile(self):
        if CONFIG_FILE and os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    profile = json.load(f)
                self.mode_combo.setCurrentText(profile.get("modeset", ""))
                for k, v in profile.get("checkbox_flags", {}).items():
                    if k in self.checkbox_flags:
                        self.checkbox_flags[k].setChecked(v)
                for k, v in profile.get("spin_values", {}).items():
                    if k in self.spin_values:
                        self.spin_values[k].setValue(v)
                for k, v in profile.get("line_values", {}).items():
                    if k in self.line_values:
                        self.line_values[k].setText(v)
            except Exception as e:
                self.exception_msg = f"Failed to load profile: {e}"
                self.exception_show_msg()

    def auto_load_last_profile(self):
        if os.path.exists(CONFIG_FILE):
            try:
                self.load_profile()
            except Exception as e:
                self.exception_msg = f"Failed to auto-load last profile: {e}"
                self.exception_show_msg()

    # noinspection PyTypeChecker
    def save_last_profile_path(self, path):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"last_profile": path}, f)

            self.output_box.append("Settings Saved and Will Be Loaded Automatically on Application Start.")
        except Exception as e:
            self.exception_msg = f"Failed to save config: {e}"
            self.exception_show_msg()

    # noinspection SpellCheckingInspection
    def run_goodbyedpi(self):
        if self.is_process_running("goodbyedpi.exe"):
            self.output_box.append("\n> GoodByeDPI Already Running Won't Start a New Instance.\n")
            return
        else:
            self.output_box.clear()
            cmd = [r"bin/goodbyedpi.exe"]
            mode = self.mode_combo.currentText()
            if mode:
                cmd.append(mode)  # Preset mode like "-9"
            else:
                # Only append flags manually if no preset mode is selected
                for flag, cb in self.checkbox_flags.items():
                    if cb.isChecked():
                        cmd.append(flag)

                for flag, spin in self.spin_values.items():
                    if spin.value() > 0:
                        cmd.extend([flag, str(spin.value())])

                for flag, le in self.line_values.items():
                    text = le.text().strip()
                    if text:
                        cmd.extend([flag, text])

            self.output_box.append(f"\n> {' '.join(cmd)}\n")
            if not self.output_connected:
                self.output_signal.connect(self.output_box.append)
                self.output_connected = True
            self.command = " ".join(cmd)
            self.run()

    def process_output(self, process):
        for line in process.stdout:
            self.output_signal.emit(line)

    # noinspection SpellCheckingInspection
    def run(self):
        try:
            process = subprocess.Popen(
                self.command,
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                shell=False
            )

            self.command_runner.run = lambda: self.process_output(process)
            self.command_runner.start()

            status = self.is_process_running("goodbyedpi.exe")
            if status:
                self.output_box.append("GoodByeDPI Is Running...")
            else:
                self.output_box.append("GoodByeDPI Is Failed to Start...")

        except Exception as e:
            self.output_signal.emit(f"Error: {e}")

    # noinspection SpellCheckingInspection
    def update_tray_icon(self):
        while not self.exiting:
            status = self.is_process_running("goodbyedpi.exe")
            if status:
                self.tray.setToolTip("GoodByeDPI Running")
                self.tray.setIcon(QIcon(r"Resources\Icon1.ico"))
                time.sleep(3)
            else:
                self.tray.setToolTip("GoodByeDPI Stopped")
                self.tray.setIcon(QIcon(r"Resources\forbidden.ico"))
                time.sleep(3)

    @staticmethod
    def is_process_running(process_name):
        process_query_limited_information = 0x1000
        try:
            processes = (ctypes.c_ulong * 2048)()  # noqa
            cb = ctypes.c_ulong(ctypes.sizeof(processes))
            ctypes.windll.psapi.EnumProcesses(ctypes.byref(processes), cb, ctypes.byref(cb))

            process_count = cb.value // ctypes.sizeof(ctypes.c_ulong)
            for i in range(process_count):
                process_id = processes[i]
                process_handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False,
                                                                    process_id)

                if process_handle:
                    buffer_size = 260
                    buffer = ctypes.create_unicode_buffer(buffer_size)
                    success = ctypes.windll.kernel32.QueryFullProcessImageNameW(process_handle, 0, buffer,
                                                                                ctypes.byref(
                                                                                    ctypes.c_ulong(buffer_size)))
                    ctypes.windll.kernel32.CloseHandle(process_handle)

                    if success:
                        process_name_actual = os.path.basename(buffer.value)
                        if process_name_actual == process_name:
                            return True
            return False

        except (ctypes.ArgumentError, OSError, ValueError):
            return False

if __name__ == "__main__":
    import os
    os.environ["QT_SCALE_FACTOR"] = "0.9"
    app = QApplication(sys.argv)
    gui = GoodbyeDPIGUI()
    gui.hide()
    sys.exit(app.exec())
