import os
import csv
import time
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QLabel, QLineEdit,
    QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from utils.ansi_cleaner import clean_terminal_output


# --- Drag & Drop Table Widget ---
class DropTableWidget(QTableWidget):
    files_dropped = pyqtSignal(list)

    def __init__(self, rows, cols, parent=None):
        super().__init__(rows, cols, parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QTableWidget.DragDropMode.DropOnly)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            file_paths = []
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path.lower().endswith(".csv"):
                    file_paths.append(path)
            if file_paths:
                self.files_dropped.emit(file_paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


# --- Auto Batch Execution Thread ---
class AutoBatchWorker(QThread):
    file_started = pyqtSignal(int)
    file_finished = pyqtSignal(int, str, str, str, str)  # row, status, elapsed, c1_log, c2_log
    batch_finished = pyqtSignal()

    def __init__(self, ssh_manager, csv_files, stop_on_fail=True):
        super().__init__()
        self.ssh_manager = ssh_manager
        self.csv_files = csv_files
        self.stop_on_fail = stop_on_fail
        self.is_running = True
        self.is_paused = False
        self.terminal_buffer = ""
        self.active_c2_stream = ""

    def append_terminal_data(self, text):
        self.terminal_buffer += text
        self.active_c2_stream += text

    def run(self):
        for idx, file_path in enumerate(self.csv_files):
            if not self.is_running:
                break

            while self.is_paused and self.is_running:
                time.sleep(0.1)
            if not self.is_running:
                break

            self.file_started.emit(idx)
            start_time = time.time()
            file_basename = os.path.basename(file_path)

            c1_log_entries = [
                f"=================================================================",
                f"Test Execution Log: {file_basename}",
                f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"=================================================================\n"
            ]
            self.active_c2_stream = ""
            file_passed = True

            # Parse CSV (utf-8-sig safely handles both standard UTF-8 and Excel BOM)
            commands = []
            try:
                with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                    for r in csv.reader(f):
                        if not r:
                            continue
                        if r[0].strip().lower() in ("command", "cmd"):
                            continue  # Skip table header row
                        cmd = r[0] if len(r) > 0 else ""
                        try:
                            t_out = float(r[1]) if len(r) > 1 and r[1].strip() else 10.0
                        except ValueError:
                            t_out = 10.0
                        exp = r[2] if len(r) > 2 else ""
                        commands.append((cmd, t_out, exp))
            except Exception as e:
                elapsed = f"{time.time() - start_time:.2f}s"
                c1_log_entries.append(f"[FATAL] : Failed to read CSV file: {str(e)}")
                self.file_finished.emit(idx, "FAIL", elapsed, "\n".join(c1_log_entries), self.active_c2_stream)
                if self.stop_on_fail:
                    break
                continue

            # Execute Commands
            for cmd, timeout, expect_str in commands:
                if not self.is_running:
                    file_passed = False
                    break

                while self.is_paused and self.is_running:
                    time.sleep(0.1)

                self.terminal_buffer = ""
                ts = time.strftime('%Y-%m-%d %H:%M:%S')
                c1_log_entries.append(f"{ts} : [INFO] : Sending command \"{cmd}\"")

                try:
                    if cmd == "'Ctrl+]'":
                        self.ssh_manager.send_data(b'\x1d')
                    elif cmd == "":
                        self.ssh_manager.send_data(b'\n')
                    else:
                        self.ssh_manager.send_line(cmd)
                except Exception as e:
                    c1_log_entries.append(f"{ts} : [ERROR] : Channel send failure: {str(e)}")
                    file_passed = False
                    break

                if expect_str.strip():
                    try:
                        regex = re.compile(expect_str, re.IGNORECASE)
                    except re.error as e:
                        c1_log_entries.append(f"{ts} : [ERROR] : Invalid regex '{expect_str}': {e} ---> FAIL")
                        file_passed = False
                        if self.stop_on_fail:
                            break
                        continue

                    step_start = time.time()
                    matched = False

                    while (time.time() - step_start) < timeout:
                        if not self.is_running:
                            break
                        if regex.search(self.terminal_buffer):
                            matched = True
                            break
                        time.sleep(0.05)

                    if not matched and not self.is_running:
                        c1_log_entries.append(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [WARNING] : Stopped by user while waiting for '{expect_str}'")
                        file_passed = False
                        break

                    ts_res = time.strftime('%Y-%m-%d %H:%M:%S')
                    if matched:
                        c1_log_entries.append(f"{ts_res} : [INFO] : \tExpect matched: '{expect_str}' ---> PASS")
                    else:
                        c1_log_entries.append(f"{ts_res} : [DEBUG] : Timeout ({timeout}s) waiting for '{expect_str}' ---> FAIL")
                        file_passed = False
                        if self.stop_on_fail:
                            break
                else:
                    time.sleep(0.5)

                if not file_passed and self.stop_on_fail:
                    break

            # Buffer flush: Allow trailing output from SSH to settle into the stream
            time.sleep(0.3)

            elapsed_str = f"{time.time() - start_time:.2f}s"
            status = "PASS" if file_passed else "FAIL"

            c1_log_entries.append(f"\n=================================================================")
            c1_log_entries.append(f"Result: {status} | Elapsed Time: {elapsed_str}")
            c1_log_entries.append(f"Finished at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            c1_log_entries.append(f"=================================================================")

            full_c1_log = "\n".join(c1_log_entries)
            self.file_finished.emit(idx, status, elapsed_str, full_c1_log, self.active_c2_stream)

            if not file_passed and self.stop_on_fail:
                break

        self.batch_finished.emit()

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def stop(self):
        self.is_running = False
        self.is_paused = False


# --- Auto Window Dialog ---
class AutoRunnerDialog(QDialog):
    def __init__(self, parent, ssh_manager):
        super().__init__(parent)
        self.parent_window = parent
        self.ssh_manager = ssh_manager
        self.worker = None
        self.file_paths = []

        self.setWindowTitle("Auto Batch CSV Runner")
        self.resize(780, 520)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        self.btn_load_csv = QPushButton("Load CSV(s)")
        self.btn_clear_list = QPushButton("Clear All")
        top_bar.addWidget(self.btn_load_csv)
        top_bar.addWidget(self.btn_clear_list)

        top_bar.addSpacing(15)
        top_bar.addWidget(QLabel("Save Logs To:"))
        self.txt_log_dir = QLineEdit(os.path.abspath("test_logs"))
        self.btn_browse_dir = QPushButton("Browse...")
        top_bar.addWidget(self.txt_log_dir)
        top_bar.addWidget(self.btn_browse_dir)
        layout.addLayout(top_bar)

        cfg_bar = QHBoxLayout()
        self.chk_stop_on_fail = QCheckBox("Stop execution on failure (Fail at stop)")
        self.chk_stop_on_fail.setChecked(True)
        cfg_bar.addWidget(self.chk_stop_on_fail)
        cfg_bar.addStretch()
        layout.addLayout(cfg_bar)

        self.table = DropTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Load File Name", "Status (Pass/Fail)", "Timer"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

        bottom_bar = QHBoxLayout()
        self.btn_start_stop = QPushButton("Start")
        self.btn_start_stop.setStyleSheet("background-color: #2ea44f; color: white; font-weight: bold; padding: 6px 16px;")

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setEnabled(False)

        bottom_bar.addWidget(self.btn_start_stop)
        bottom_bar.addWidget(self.btn_pause)
        bottom_bar.addStretch()

        self.lbl_overall = QLabel("Ready")
        bottom_bar.addWidget(self.lbl_overall)
        layout.addLayout(bottom_bar)

        self.btn_load_csv.clicked.connect(self.browse_csv_files)
        self.btn_clear_list.clicked.connect(self.clear_files)
        self.btn_browse_dir.clicked.connect(self.browse_log_directory)
        self.table.files_dropped.connect(self.add_files)
        self.btn_start_stop.clicked.connect(self.toggle_start_stop)
        self.btn_pause.clicked.connect(self.toggle_pause)

    def browse_csv_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select CSV Files", "", "CSV Files (*.csv)")
        if files:
            self.add_files(files)

    def add_files(self, paths):
        for path in paths:
            if path not in self.file_paths:
                self.file_paths.append(path)
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(os.path.basename(path)))
                self.table.setItem(row, 1, QTableWidgetItem("Pending"))
                self.table.setItem(row, 2, QTableWidgetItem("--"))

    def clear_files(self):
        if self.worker and self.worker.isRunning():
            return
        self.table.setRowCount(0)
        self.file_paths.clear()

    def browse_log_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Log Save Folder", self.txt_log_dir.text())
        if folder:
            self.txt_log_dir.setText(folder)

    def handle_worker_data(self, text):
        if self.worker and self.worker.isRunning():
            # Strip ANSI sequences so regexes like '\$' match the visible prompt.
            cleaned, _ = clean_terminal_output(text)
            if cleaned:
                self.worker.append_terminal_data(cleaned)

    def toggle_start_stop(self):
        if self.worker and self.worker.isRunning():
            # Keep the button locked until the worker really exits, so a new
            # batch can't start while the old one is still sending commands.
            self.worker.stop()
            self.btn_start_stop.setEnabled(False)
            self.btn_pause.setEnabled(False)
            self.btn_pause.setText("Pause")
            self.lbl_overall.setText("Stopping...")
        else:
            if not self.file_paths:
                QMessageBox.warning(self, "Warning", "Please add at least one CSV template file.")
                return

            if not self.ssh_manager.is_connected():
                self.parent_window.connect_ssh()
                if not self.ssh_manager.is_connected():
                    QMessageBox.critical(self, "Error", "SSH is not connected. Connect SSH first.")
                    return

            for r in range(self.table.rowCount()):
                self.table.setItem(r, 1, QTableWidgetItem("Queued"))
                self.table.setItem(r, 2, QTableWidgetItem("--"))

            self.worker = AutoBatchWorker(
                self.ssh_manager,
                self.file_paths,
                stop_on_fail=self.chk_stop_on_fail.isChecked()
            )

            # Prevent duplicate signal connections
            try:
                self.ssh_manager.data_received.disconnect(self.handle_worker_data)
            except Exception:
                pass
            self.ssh_manager.data_received.connect(self.handle_worker_data)

            self.worker.file_started.connect(self.on_file_started)
            self.worker.file_finished.connect(self.on_file_finished)
            self.worker.batch_finished.connect(self.on_batch_finished)

            self.worker.start()
            self.btn_start_stop.setText("Stop")
            self.btn_start_stop.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 6px 16px;")
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("Pause")
            self.lbl_overall.setText("Running batch...")

    def toggle_pause(self):
        if not self.worker or not self.worker.isRunning():
            return

        if self.worker.is_paused:
            self.worker.resume()
            self.btn_pause.setText("Pause")
            self.btn_pause.setStyleSheet("")
            self.lbl_overall.setText("Running batch...")
        else:
            self.worker.pause()
            self.btn_pause.setText("Resume")
            self.btn_pause.setStyleSheet("background-color: #f0ad4e; color: black;")
            self.lbl_overall.setText("Execution paused")

    def on_file_started(self, row):
        self.table.setItem(row, 1, QTableWidgetItem("Running..."))

    def on_file_finished(self, row, status, elapsed, c1_log, c2_log):
        # Update UI Table
        status_item = QTableWidgetItem(status)
        if status == "PASS":
            status_item.setForeground(Qt.GlobalColor.green)
        else:
            status_item.setForeground(Qt.GlobalColor.red)

        self.table.setItem(row, 1, status_item)
        self.table.setItem(row, 2, QTableWidgetItem(elapsed))

        # Save Output Files
        log_dir = self.txt_log_dir.text().strip() or "test_logs"
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError as e:
            self.lbl_overall.setText(f"Cannot create log folder: {e}")
            return
        raw_name = os.path.splitext(os.path.basename(self.file_paths[row]))[0]

        # Target file names dynamically appended with pass/fail status
        stat_tag = status.lower()  # creates 'pass' or 'fail' (use status.upper() for 'PASS' or 'FAIL')
        c1_filename = os.path.join(log_dir, f"{raw_name}_console_1_{stat_tag}.txt")
        c2_filename = os.path.join(log_dir, f"{raw_name}_console_2_{stat_tag}.txt")

        try:
            # Write Console 1 Log
            with open(c1_filename, "w", encoding="utf-8") as f1:
                f1.write(c1_log if c1_log.strip() else f"Execution finished with status: {status}\n")

            # Write Console 2 Log (already ANSI-cleaned as it was captured)
            with open(c2_filename, "w", encoding="utf-8") as f2:
                f2.write(c2_log if c2_log.strip() else "[No terminal output captured for this sequence]")
        except OSError as e:
            self.lbl_overall.setText(f"Could not write logs: {e}")

    def on_batch_finished(self):
        stopped = bool(self.worker and not self.worker.is_running)
        self.btn_start_stop.setEnabled(True)
        self.btn_start_stop.setText("Start")
        self.btn_start_stop.setStyleSheet("background-color: #2ea44f; color: white; font-weight: bold; padding: 6px 16px;")
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Pause")
        self.btn_pause.setStyleSheet("")
        self.lbl_overall.setText("Stopped by user" if stopped else "Batch Completed")

    def done(self, result):
        # done() runs for close button, Esc and window-close alike (closeEvent does not).
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
        try:
            self.ssh_manager.data_received.disconnect(self.handle_worker_data)
        except (TypeError, RuntimeError):
            pass
        super().done(result)