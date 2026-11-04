from PyQt6.QtWidgets import QTableWidget, QTextEdit, QWidget, QApplication
from PyQt6.QtCore import Qt, pyqtSignal
import sys
from PyQt6.QtGui import QFontDatabase, QWheelEvent, QKeyEvent, QTextCursor

# On macOS Qt swaps the keys: the physical Ctrl key is reported as MetaModifier.
TERM_CTRL = Qt.KeyboardModifier.MetaModifier if sys.platform == "darwin" else Qt.KeyboardModifier.ControlModifier

class DeselectableTableWidget(QTableWidget):
    def mousePressEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        item = self.itemAt(pos)
        if item is None:
            self.clearSelection()
            self.setCurrentCell(-1, -1)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.clearSelection()
            self.setCurrentCell(-1, -1)
            event.accept()
            return
        super().keyPressEvent(event)

class ClickablePanel(QWidget):
    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = table

    def mousePressEvent(self, event):
        if self.table:
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
        super().mousePressEvent(event)

class ZoomableConsole(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.default_font_size = 10
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(self.default_font_size)
        self.setFont(font)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoomIn(1)
            elif delta < 0:
                self.zoomOut(1)
            event.accept()
        else:
            super().wheelEvent(event)

    def reset_zoom(self):
        font = self.font()
        font.setPointSize(self.default_font_size)
        self.setFont(font)

class TerminalConsole(ZoomableConsole):
    send_input_signal = pyqtSignal(bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.manual_input_enabled = True
        self._pending_cr = ""

    def focusNextPrevChild(self, next):
        return False

    def insert_terminal_text(self, text: str):
        # A trailing '\r' may be the first half of a '\r\n' split across chunks;
        # hold it back so it doesn't wipe the current line.
        text = self._pending_cr + text
        self._pending_cr = ""
        if text.endswith('\r'):
            text = text[:-1]
            self._pending_cr = '\r'
        text = text.replace('\r\n', '\n')

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if text.startswith('\x08 \x08', i):
                cursor.deletePreviousChar()
                i += 3
            elif ch == '\x08':
                cursor.deletePreviousChar()
                i += 1
            elif ch == '\r':
                cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
                i += 1
            else:
                j = i
                while j < n and text[j] not in '\x08\r':
                    j += 1
                cursor.insertText(text[i:j])
                i = j
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def keyPressEvent(self, event: QKeyEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.zoomIn(1)
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Minus:
                self.zoomOut(1)
                event.accept()
                return
            elif event.key() == Qt.Key.Key_0:
                self.reset_zoom()
                event.accept()
                return

        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            if event.key() == Qt.Key.Key_C:
                self.copy()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_V:
                clip = QApplication.clipboard().text()
                if clip and self.manual_input_enabled:
                    self.send_input_signal.emit(clip.encode('utf-8'))
                event.accept()
                return

        if not self.manual_input_enabled:
            super().keyPressEvent(event)
            return

        key = event.key()
        payload = None

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            payload = b'\r'
        elif key == Qt.Key.Key_Backspace:
            payload = b'\x7f'
        elif key == Qt.Key.Key_Tab:
            payload = b'\t'
        elif key == Qt.Key.Key_Escape:
            payload = b'\x1b'
        elif key == Qt.Key.Key_Up:
            payload = b'\x1b[A'
        elif key == Qt.Key.Key_Down:
            payload = b'\x1b[B'
        elif key == Qt.Key.Key_Right:
            payload = b'\x1b[C'
        elif key == Qt.Key.Key_Left:
            payload = b'\x1b[D'
        elif key == Qt.Key.Key_Home:
            payload = b'\x1b[H'
        elif key == Qt.Key.Key_End:
            payload = b'\x1b[F'
        elif key == Qt.Key.Key_Delete:
            payload = b'\x1b[3~'
        elif event.modifiers() & TERM_CTRL:
            if key == Qt.Key.Key_BracketRight:
                payload = b'\x1d'
            elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
                payload = bytes([int(key) - int(Qt.Key.Key_A) + 1])
        else:
            txt = event.text()
            if txt:
                payload = txt.encode('utf-8')

        if payload:
            self.send_input_signal.emit(payload)
            event.accept()
        else:
            super().keyPressEvent(event)
