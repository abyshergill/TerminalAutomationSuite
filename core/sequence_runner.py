import time
import re
from PyQt6.QtCore import QThread, pyqtSignal

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
                timeout = float(timeout_str) if timeout_str else 10.0
            except ValueError:
                timeout = 10.0

            self.accumulated_buffer = ""
            self.log_c1.emit(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [INFO] : Sending command \"{cmd}\"")

            try:
                if cmd == "'Ctrl+]'":
                    self.channel.send('\x1d')
                elif cmd == "":
                    self.channel.send('\n')
                else:
                    self.channel.send(cmd + '\n')
            except Exception as e:
                self.log_c1.emit(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [ERROR] : Channel send failure: {str(e)}")
                self.status_update.emit(row_idx, "ERROR")
                break

            if expect_str.strip():
                start_time = time.time()
                regex = re.compile(expect_str, re.IGNORECASE)
                matched = False

                while (time.time() - start_time) < timeout:
                    if not self.is_running:
                        break
                    if regex.search(self.accumulated_buffer):
                        matched = True
                        break
                    time.sleep(0.05)

                if matched:
                    self.log_c1.emit(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [INFO] : -----------------------------------------------------------------")
                    self.log_c1.emit(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [INFO] : \tMatched Expect: '{expect_str}'")
                    self.log_c1.emit(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [INFO] : \t---> PASS")
                    self.status_update.emit(row_idx, "PASS")
                else:
                    self.log_c1.emit(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [DEBUG] : Timeout... {timeout}s waiting for '{expect_str}'")
                    self.log_c1.emit(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [INFO] : \t---> FAIL")
                    self.status_update.emit(row_idx, "FAIL")
                    if self.stop_on_failure:
                        self.log_c1.emit(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [WARNING] : Execution stopped due to failure.")
                        break
            else:
                time.sleep(0.5)
                self.status_update.emit(row_idx, "PASS (No Expect)")

        self.log_c1.emit(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : [INFO] : Sequence completed.")
        self.sequence_finished.emit()

    def stop(self):
        self.is_running = False
