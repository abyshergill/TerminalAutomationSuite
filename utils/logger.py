class ConsoleLogger:
    def __init__(self):
        self.file_path = None
        self.file_handle = None
        self.is_logging = False
        self.is_paused = False

    def start(self, file_path: str):
        self.file_path = file_path
        self.file_handle = open(file_path, 'a', encoding='utf-8')
        self.is_logging = True
        self.is_paused = False

    def stop(self):
        if self.file_handle:
            try:
                self.file_handle.flush()
                self.file_handle.close()
            except Exception:
                pass
        self.file_handle = None
        self.file_path = None
        self.is_logging = False
        self.is_paused = False

    def toggle_pause(self) -> bool:
        if self.is_logging:
            self.is_paused = not self.is_paused
            return self.is_paused
        return False

    def write(self, text: str):
        if self.is_logging and not self.is_paused and self.file_handle:
            try:
                self.file_handle.write(text)
                self.file_handle.flush()
            except Exception:
                pass
