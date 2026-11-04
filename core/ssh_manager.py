import codecs
import time
import paramiko
from PyQt6.QtCore import QObject, QThread, pyqtSignal


class ChannelReaderThread(QThread):
    raw_data_received = pyqtSignal(str)
    channel_closed = pyqtSignal()

    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self.is_running = True
        # Incremental decoder so multi-byte characters split across recv() calls survive.
        self._decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')

    def run(self):
        while self.is_running and self.channel is not None:
            try:
                if self.channel.recv_ready():
                    raw = self.channel.recv(4096)
                    if not raw:
                        break
                    data = self._decoder.decode(raw)
                    if data:
                        self.raw_data_received.emit(data)
                elif self.channel.closed or self.channel.eof_received:
                    break
                else:
                    time.sleep(0.01)
            except Exception:
                break
        if self.is_running:
            # Ended on its own (remote closed / connection lost), not via stop().
            self.channel_closed.emit()

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
        self.disconnect_ssh(notify=False)
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname=host,
                port=port,
                username=user,
                password=password,
                timeout=10,
                banner_timeout=10,
                auth_timeout=10,
                look_for_keys=False,
                allow_agent=False
            )
            self.channel = self.client.invoke_shell(term='xterm', width=160, height=50)
            # Reads are guarded by recv_ready(); sends must be able to block briefly
            # instead of raising on a full window or sending partial data.
            self.channel.settimeout(10.0)

            self.reader_thread = ChannelReaderThread(self.channel)
            self.reader_thread.raw_data_received.connect(self.data_received.emit)
            self.reader_thread.channel_closed.connect(self._on_remote_closed)
            self.reader_thread.start()

            self.connection_status.emit(True, "Connected")
        except Exception as e:
            self.disconnect_ssh(notify=False)
            self.connection_status.emit(False, str(e) or e.__class__.__name__)

    def _on_remote_closed(self):
        if self.channel is not None:
            self.disconnect_ssh()

    def disconnect_ssh(self, notify: bool = True):
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
        if notify:
            self.connection_status.emit(False, "Disconnected")

    def send_data(self, data: bytes):
        if self.is_connected():
            self.channel.sendall(data)

    def send_line(self, line: str):
        self.send_data((line + '\n').encode('utf-8'))
