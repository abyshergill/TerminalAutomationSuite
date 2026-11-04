import time
import re
from PyQt6.QtCore import QThread, pyqtSignal


def _ts() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S')


class SequenceRunner(QThread):
    log_c1 = pyqtSignal(str)
    status_update = pyqtSignal(int, str)
    sequence_finished = pyqtSignal()

    def __init__(self, channel, command_list: list, stop_on_failure: bool = True):
        super().__init__()
        self.channel = channel
        self.command_list = command_list
        self.stop_on_failure = stop_on_failure
        self.is_running = True
        self.accumulated_buffer = ""

    def append_buffer(self, text: str):
        self.accumulated_buffer += text

    def run(self):
        for row_idx, cmd, timeout_str, expect_str in self.command_list:
            if not self.is_running:
                break

            try:
                timeout = float(timeout_str) if str(timeout_str).strip() else 10.0
            except ValueError:
                timeout = 10.0

            regex = None
            if expect_str.strip():
                try:
                    regex = re.compile(expect_str, re.IGNORECASE)
                except re.error as e:
                    self.log_c1.emit(f"{_ts()} : [ERROR] : Invalid regex '{expect_str}': {e}")
                    self.status_update.emit(row_idx, "ERROR")
                    if self.stop_on_failure:
                        break
                    continue

            self.accumulated_buffer = ""
            self.log_c1.emit(f"{_ts()} : [INFO] : Sending command \"{cmd}\"")

            try:
                if cmd == "'Ctrl+]'":
                    self.channel.sendall(b'\x1d')
                elif cmd == "":
                    self.channel.sendall(b'\n')
                else:
                    self.channel.sendall((cmd + '\n').encode('utf-8'))
            except Exception as e:
                self.log_c1.emit(f"{_ts()} : [ERROR] : Channel send failure: {str(e)}")
                self.status_update.emit(row_idx, "ERROR")
                break

            if regex is not None:
                start_time = time.time()
                matched = False

                while (time.time() - start_time) < timeout:
                    if not self.is_running:
                        break
                    if regex.search(self.accumulated_buffer):
                        matched = True
                        break
                    time.sleep(0.05)

                if not matched and not self.is_running:
                    self.status_update.emit(row_idx, "STOPPED")
                    break

                if matched:
                    self.log_c1.emit(f"{_ts()} : [INFO] : -----------------------------------------------------------------")
                    self.log_c1.emit(f"{_ts()} : [INFO] : \tMatched Expect: '{expect_str}'")
                    self.log_c1.emit(f"{_ts()} : [INFO] : \t---> PASS")
                    self.status_update.emit(row_idx, "PASS")
                else:
                    self.log_c1.emit(f"{_ts()} : [DEBUG] : Timeout... {timeout}s waiting for '{expect_str}'")
                    self.log_c1.emit(f"{_ts()} : [INFO] : \t---> FAIL")
                    self.status_update.emit(row_idx, "FAIL")
                    if self.stop_on_failure:
                        self.log_c1.emit(f"{_ts()} : [WARNING] : Execution stopped due to failure.")
                        break
            else:
                time.sleep(0.5)
                self.status_update.emit(row_idx, "PASS (No Expect)")

        self.log_c1.emit(f"{_ts()} : [INFO] : Sequence completed.")
        self.sequence_finished.emit()

    def stop(self):
        self.is_running = False
