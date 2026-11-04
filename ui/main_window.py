import csv
import time
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QSplitter, QLabel, QHeaderView,
    QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from config import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASS, CREATORS, APP_TITLE
from utils.ansi_cleaner import clean_terminal_output
from utils.logger import ConsoleLogger
from core.ssh_manager import SSHManager
from core.sequence_runner import SequenceRunner
from ui.dialogs import SSHDialog, CreatorsDialog
from ui.auto_dialog import AutoRunnerDialog
from ui.terminal_widgets import DeselectableTableWidget, ClickablePanel, ZoomableConsole, TerminalConsole

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon("icon.svg"))
        self.resize(1380, 850)

        self.ssh_host = DEFAULT_HOST
        self.ssh_port = DEFAULT_PORT
        self.ssh_user = DEFAULT_USER
        self.ssh_pass = DEFAULT_PASS

        self.ssh_manager = SSHManager()
        self.ssh_manager.data_received.connect(self.handle_incoming_terminal_data)
        self.ssh_manager.connection_status.connect(self.handle_ssh_status)
        self.runner_thread = None

        self.logger_c1 = ConsoleLogger()
        self.logger_c2 = ConsoleLogger()

        self.initUI()

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        self.table = DeselectableTableWidget(0, 4)
        left_panel = ClickablePanel(self.table)
        left_layout = QVBoxLayout(left_panel)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add Row")
        self.btn_remove = QPushButton("Remove Row")
        self.btn_load = QPushButton("Load CSV")
        self.btn_save = QPushButton("Save CSV")
        self.btn_deselect = QPushButton("Deselect")
        self.btn_run = QPushButton("Run (Selected / All)")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)

        for b in [self.btn_add, self.btn_remove, self.btn_load, self.btn_save, self.btn_deselect, self.btn_run, self.btn_stop]:
            btn_layout.addWidget(b)

        self.btn_add.clicked.connect(self.add_row)
        self.btn_remove.clicked.connect(self.remove_row)
        self.btn_load.clicked.connect(self.load_csv)
        self.btn_save.clicked.connect(self.save_csv)
        self.btn_deselect.clicked.connect(self.clear_table_selection)
        self.btn_run.clicked.connect(self.run_sequence)
        self.btn_stop.clicked.connect(self.stop_sequence)
        left_layout.addLayout(btn_layout)

        opts_layout = QHBoxLayout()
        self.chk_stop_on_fail = QCheckBox("Stop execution on failure")
        self.chk_stop_on_fail.setChecked(True)
        opts_layout.addWidget(self.chk_stop_on_fail)

        self.chk_reuse_ssh = QCheckBox("Use active SSH session (do not reconnect)")
        self.chk_reuse_ssh.setChecked(True)
        opts_layout.addWidget(self.chk_reuse_ssh)

        opts_layout.addStretch()

        self.btn_auto = QPushButton("Auto")
        self.btn_auto.setStyleSheet("font-weight: bold; background-color: #0969da; color: white;")
        self.btn_auto.clicked.connect(self.open_auto_dialog)
        opts_layout.addWidget(self.btn_auto)

        self.btn_creators = QPushButton("Creator Info")
        self.btn_creators.setStyleSheet("font-weight: bold;")
        self.btn_creators.clicked.connect(self.show_creators_dialog)
        opts_layout.addWidget(self.btn_creators)

        left_layout.addLayout(opts_layout)

        self.table.setHorizontalHeaderLabels(["Command", "Timeout (s)", "Expect (Regex)", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        left_layout.addWidget(self.table)

        c1_header = QHBoxLayout()
        c1_header.addWidget(QLabel("<b>Console 1: Execution Logs</b>"))

        self.btn_c1_log_toggle = QPushButton("Start Log")
        self.btn_c1_log_pause = QPushButton("Pause Log")
        self.btn_c1_log_pause.setEnabled(False)

        btn_c1_in = QPushButton("+")
        btn_c1_in.setFixedWidth(32)
        btn_c1_out = QPushButton("-")
        btn_c1_out.setFixedWidth(32)
        btn_c1_res = QPushButton("Reset")
        btn_c1_res.setFixedWidth(60)

        c1_header.addWidget(self.btn_c1_log_toggle)
        c1_header.addWidget(self.btn_c1_log_pause)
        c1_header.addWidget(btn_c1_in)
        c1_header.addWidget(btn_c1_out)
        c1_header.addWidget(btn_c1_res)
        left_layout.addLayout(c1_header)

        self.console1_log = ZoomableConsole()
        self.console1_log.setReadOnly(True)
        btn_c1_in.clicked.connect(self.console1_log.zoomIn)
        btn_c1_out.clicked.connect(self.console1_log.zoomOut)
        btn_c1_res.clicked.connect(self.console1_log.reset_zoom)
        self.btn_c1_log_toggle.clicked.connect(self.toggle_c1_logging)
        self.btn_c1_log_pause.clicked.connect(self.pause_c1_logging)
        left_layout.addWidget(self.console1_log)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        c2_header = QHBoxLayout()
        c2_header.addWidget(QLabel("<b>Console 2: Terminal</b>"))

        self.btn_ssh_connect = QPushButton("SSH Connect")
        self.btn_ssh_disconnect = QPushButton("Disconnect")
        self.btn_ssh_disconnect.setEnabled(False)

        self.lbl_ssh_status = QLabel("Disconnected")
        self.lbl_ssh_status.setStyleSheet("color: red; font-weight: bold;")

        self.chk_manual_input = QCheckBox("Enable keyboard input")
        self.chk_manual_input.setChecked(True)

        self.btn_c2_log_toggle = QPushButton("Start Log")
        self.btn_c2_log_pause = QPushButton("Pause Log")
        self.btn_c2_log_pause.setEnabled(False)

        btn_c2_in = QPushButton("+")
        btn_c2_in.setFixedWidth(32)
        btn_c2_out = QPushButton("-")
        btn_c2_out.setFixedWidth(32)
        btn_c2_res = QPushButton("Reset")
        btn_c2_res.setFixedWidth(60)

        c2_header.addWidget(self.btn_ssh_connect)
        c2_header.addWidget(self.btn_ssh_disconnect)
        c2_header.addWidget(self.lbl_ssh_status)
        c2_header.addSpacing(10)
        c2_header.addWidget(self.chk_manual_input)
        c2_header.addStretch()
        c2_header.addWidget(self.btn_c2_log_toggle)
        c2_header.addWidget(self.btn_c2_log_pause)
        c2_header.addWidget(btn_c2_in)
        c2_header.addWidget(btn_c2_out)
        c2_header.addWidget(btn_c2_res)
        right_layout.addLayout(c2_header)

        self.console2_log = TerminalConsole()
        self.console2_log.setStyleSheet(
            "QTextEdit { background-color: #0c1017; color: #f0f6fc; selection-background-color: #388bfd; border: 1px solid #30363d; }"
            "QTextEdit:focus { border: 2px solid #58a6ff; }"
        )
        self.console2_log.setPlaceholderText("Click here to interact directly with the terminal using your keyboard...")
        btn_c2_in.clicked.connect(self.console2_log.zoomIn)
        btn_c2_out.clicked.connect(self.console2_log.zoomOut)
        btn_c2_res.clicked.connect(self.console2_log.reset_zoom)

        self.btn_ssh_connect.clicked.connect(self.open_ssh_dialog)
        self.btn_ssh_disconnect.clicked.connect(self.disconnect_ssh)
        self.btn_c2_log_toggle.clicked.connect(self.toggle_c2_logging)
        self.btn_c2_log_pause.clicked.connect(self.pause_c2_logging)

        self.console2_log.send_input_signal.connect(self.send_manual_input_to_ssh)
        self.chk_manual_input.toggled.connect(self.toggle_manual_input_state)
        right_layout.addWidget(self.console2_log)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([680, 680])

    def open_auto_dialog(self):
        dialog = AutoRunnerDialog(self, self.ssh_manager)
        dialog.exec()

    def show_creators_dialog(self):
        dialog = CreatorsDialog(self, CREATORS)
        dialog.exec()

    def toggle_manual_input_state(self, enabled: bool):
        self.console2_log.manual_input_enabled = enabled
        if enabled:
            self.console2_log.setPlaceholderText("Click here to interact directly with the terminal using your keyboard...")
        else:
            self.console2_log.setPlaceholderText("[Manual input disabled by checkbox above]")

    def clear_table_selection(self):
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)

    def send_manual_input_to_ssh(self, data: bytes):
        if self.ssh_manager.is_connected():
            self.ssh_manager.send_data(data)
        else:
            self.append_c1("[WARNING] : SSH is not connected. Connect SSH before typing.")

    def open_ssh_dialog(self):
        dialog = SSHDialog(self, self.ssh_host, self.ssh_port, self.ssh_user, self.ssh_pass)
        if dialog.exec():
            self.ssh_host, self.ssh_port, self.ssh_user, self.ssh_pass = dialog.get_details()
            self.connect_ssh()

    def connect_ssh(self):
        self.append_c1(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [INFO] : Connecting to SSH {self.ssh_user}@{self.ssh_host}:{self.ssh_port}...")
        self.ssh_manager.connect_ssh(self.ssh_host, self.ssh_port, self.ssh_user, self.ssh_pass)

    def disconnect_ssh(self):
        self.ssh_manager.disconnect_ssh()
        self.append_c1(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [INFO] : SSH Session disconnected by user.")

    def handle_ssh_status(self, connected: bool, message: str):
        if connected:
            self.lbl_ssh_status.setText("Connected")
            self.lbl_ssh_status.setStyleSheet("color: #00FF00; font-weight: bold;")
            self.btn_ssh_disconnect.setEnabled(True)
            self.btn_ssh_connect.setEnabled(False)
            self.append_c1(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [INFO] : SSH Session Established.")
        else:
            self.lbl_ssh_status.setText("Disconnected")
            self.lbl_ssh_status.setStyleSheet("color: red; font-weight: bold;")
            self.btn_ssh_disconnect.setEnabled(False)
            self.btn_ssh_connect.setEnabled(True)
            if message not in ("Disconnected", ""):
                self.append_c1(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [FATAL] : SSH Error: {message}")
                QMessageBox.critical(self, "SSH Error", f"Unable to establish SSH connection:\n{message}")

    def handle_incoming_terminal_data(self, raw_data: str):
        cleaned_text, should_clear = clean_terminal_output(raw_data)
        if should_clear:
            self.console2_log.clear()

        if cleaned_text:
            self.console2_log.insert_terminal_text(cleaned_text)
            self.logger_c2.write(cleaned_text)

        if self.runner_thread and self.runner_thread.isRunning():
            self.runner_thread.append_buffer(cleaned_text)

    def append_c1(self, text: str):
        self.console1_log.append(text)
        self.logger_c1.write(text + "\n")

    def toggle_c1_logging(self):
        if not self.logger_c1.is_logging:
            path, _ = QFileDialog.getSaveFileName(self, "Save Console 1 Log", "", "Text Files (*.txt);;All Files (*)")
            if path:
                self.logger_c1.start(path)
                self.btn_c1_log_toggle.setText("Stop Log")
                self.btn_c1_log_toggle.setStyleSheet("background-color: #d9534f; color: white;")
                self.btn_c1_log_pause.setEnabled(True)
                self.append_c1(f"[INFO] : Console 1 logging started -> {path}")
        else:
            self.logger_c1.stop()
            self.btn_c1_log_toggle.setText("Start Log")
            self.btn_c1_log_toggle.setStyleSheet("")
            self.btn_c1_log_pause.setText("Pause Log")
            self.btn_c1_log_pause.setEnabled(False)
            self.append_c1("[INFO] : Console 1 logging stopped.")

    def pause_c1_logging(self):
        is_paused = self.logger_c1.toggle_pause()
        if is_paused:
            self.btn_c1_log_pause.setText("Resume Log")
            self.btn_c1_log_pause.setStyleSheet("background-color: #f0ad4e; color: black;")
        else:
            self.btn_c1_log_pause.setText("Pause Log")
            self.btn_c1_log_pause.setStyleSheet("")

    def toggle_c2_logging(self):
        if not self.logger_c2.is_logging:
            path, _ = QFileDialog.getSaveFileName(self, "Save Console 2 Log", "", "Text Files (*.txt);;All Files (*)")
            if path:
                self.logger_c2.start(path)
                self.btn_c2_log_toggle.setText("Stop Log")
                self.btn_c2_log_toggle.setStyleSheet("background-color: #d9534f; color: white;")
                self.btn_c2_log_pause.setEnabled(True)
                self.append_c1(f"[INFO] : Console 2 terminal logging started -> {path}")
        else:
            self.logger_c2.stop()
            self.btn_c2_log_toggle.setText("Start Log")
            self.btn_c2_log_toggle.setStyleSheet("")
            self.btn_c2_log_pause.setText("Pause Log")
            self.btn_c2_log_pause.setEnabled(False)
            self.append_c1("[INFO] : Console 2 terminal logging stopped.")

    def pause_c2_logging(self):
        is_paused = self.logger_c2.toggle_pause()
        if is_paused:
            self.btn_c2_log_pause.setText("Resume Log")
            self.btn_c2_log_pause.setStyleSheet("background-color: #f0ad4e; color: black;")
        else:
            self.btn_c2_log_pause.setText("Pause Log")
            self.btn_c2_log_pause.setStyleSheet("")

    def run_sequence(self):
        if not self.ssh_manager.is_connected() or not self.chk_reuse_ssh.isChecked():
            self.connect_ssh()
            if not self.ssh_manager.is_connected():
                return

        selected_items = self.table.selectedItems()
        rows_to_run = sorted(list(set(i.row() for i in selected_items))) if selected_items else range(self.table.rowCount())

        command_list = []
        for r in rows_to_run:
            cmd = self.table.item(r, 0).text() if self.table.item(r, 0) else ""
            t_out = self.table.item(r, 1).text() if self.table.item(r, 1) else "10"
            exp = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
            self.table.setItem(r, 3, QTableWidgetItem("Queued"))
            command_list.append((r, cmd, t_out, exp))

        if not command_list:
            return

        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self.runner_thread = SequenceRunner(
            self.ssh_manager.channel,
            command_list,
            stop_on_failure=self.chk_stop_on_fail.isChecked()
        )
        self.runner_thread.log_c1.connect(self.append_c1)
        self.runner_thread.status_update.connect(lambda row, stat: self.table.setItem(row, 3, QTableWidgetItem(stat)))
        self.runner_thread.sequence_finished.connect(self.on_sequence_finished)
        self.runner_thread.start()

    def stop_sequence(self):
        if self.runner_thread and self.runner_thread.isRunning():
            self.runner_thread.stop()
            self.append_c1(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [WARNING] : Execution interrupted by operator.")

    def on_sequence_finished(self):
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def add_row(self):
        pos = self.table.rowCount()
        self.table.insertRow(pos)
        self.table.setItem(pos, 3, QTableWidgetItem("Ready"))

    def remove_row(self):
        selected_rows = sorted(list(set(item.row() for item in self.table.selectedItems())), reverse=True)
        if selected_rows:
            for row in selected_rows:
                self.table.removeRow(row)
        elif self.table.currentRow() >= 0:
            self.table.removeRow(self.table.currentRow())

    def load_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Template", "", "CSV Files (*.csv)")
        if path:
            self.table.setRowCount(0)
            with open(path, 'r', newline='', encoding='utf-8') as f:
                for row_data in csv.reader(f):
                    if not row_data:
                        continue
                    pos = self.table.rowCount()
                    self.table.insertRow(pos)
                    for col, val in enumerate(row_data[:4]):
                        self.table.setItem(pos, col, QTableWidgetItem(val))

    def save_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Template", "", "CSV Files (*.csv)")
        if path:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                for r in range(self.table.rowCount()):
                    writer.writerow([self.table.item(r, c).text() if self.table.item(r, c) else "" for c in range(self.table.columnCount())])

    def closeEvent(self, event):
        self.disconnect_ssh()
        self.logger_c1.stop()
        self.logger_c2.stop()
        super().closeEvent(event)
