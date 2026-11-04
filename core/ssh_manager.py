import time
import paramiko
from PyQt6.QtCore import QObject, QThread, pyqtSignal

class ChannelReaderThread(QThread):
    raw_data_received = pyqtSignal(str)

    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self.is_running = True

    def run(self):
        while self.is_running and self.channel and not self.channel.closed:
            try:
                if self.channel.recv_ready():
                    data = self.channel.recv(4096).decode('utf-8', errors='replace')
                    if data:
                        self.raw_data_received.emit(data)
                else:
                    time.sleep(0.01)
            except Exception:
                if not self.channel or self.channel.closed:
                    break
                time.sleep(0.01)

    def stop(self):
        self.is_running = False

class SSHManager(QObject):
    data_received = pyqtSignal(str)
    connection_status = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.client = None
        self.channel = None
        self.reader_thread = None

    def is_connected(self) -> bool:
        return self.channel is not None and not self.channel.closed

    def connect_ssh(self, host: str, port: int, user: str, password: str):
        self.disconnect_ssh()
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname=host,
                port=port,
                username=user,
                password=password,
                timeout=10,
                look_for_keys=False,
                allow_agent=False
            )
            self.channel = self.client.invoke_shell(term='xterm', width=160, height=50)
            self.channel.settimeout(0.0)

            self.reader_thread = ChannelReaderThread(self.channel)
            self.reader_thread.raw_data_received.connect(self.data_received.emit)
            self.reader_thread.start()

            self.connection_status.emit(True, "Connected")
        except Exception as e:
            self.disconnect_ssh()
            self.connection_status.emit(False, str(e))

    def disconnect_ssh(self):
        if self.reader_thread:
            self.reader_thread.stop()
            self.reader_thread.wait()
            self.reader_thread = None
        if self.channel:
            try:
                self.channel.close()
            except Exception:
                pass
            self.channel = None
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
        self.connection_status.emit(False, "Disconnected")

    def send_data(self, data: bytes):
        if self.is_connected():
            self.channel.send(data)

    def send_line(self, line: str):
        if self.is_connected():
            self.channel.send(line + '\n')
