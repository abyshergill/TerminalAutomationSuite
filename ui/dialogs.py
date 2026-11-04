from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QHBoxLayout,
    QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt

class SSHDialog(QDialog):
    def __init__(self, parent, host: str, port: int, user: str, password: str):
        super().__init__(parent)
        self.setWindowTitle("SSH Configuration")
        self.resize(360, 200)

        layout = QFormLayout(self)
        self.txt_host = QLineEdit(host)
        self.txt_port = QLineEdit(str(port))
        self.txt_user = QLineEdit(user)
        self.txt_pass = QLineEdit(password)
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)

        layout.addRow("Host IP / Name:", self.txt_host)
        layout.addRow("SSH Port:", self.txt_port)
        layout.addRow("Username:", self.txt_user)
        layout.addRow("Password:", self.txt_pass)

        btn_box = QHBoxLayout()
        self.btn_save = QPushButton("Save & Connect")
        self.btn_cancel = QPushButton("Cancel")
        btn_box.addWidget(self.btn_save)
        btn_box.addWidget(self.btn_cancel)
        layout.addRow(btn_box)

        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def get_details(self) -> tuple[str, int, str, str]:
        port_text = self.txt_port.text().strip()
        try:
            port = int(port_text) if port_text else 22
            if not 1 <= port <= 65535:
                port = 22
        except ValueError:
            port = 22
        return (
            self.txt_host.text().strip(),
            port,
            self.txt_user.text().strip(),
            self.txt_pass.text()
        )

class CreatorsDialog(QDialog):
    def __init__(self, parent, creators_list: list):
        super().__init__(parent)
        self.setWindowTitle("Creator Information")
        self.resize(460, 240)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Application Development & Support Team</b>"))

        table = QTableWidget(len(creators_list), 2)
        table.setHorizontalHeaderLabels(["Name", "Email Address"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for row, info in enumerate(creators_list):
            table.setItem(row, 0, QTableWidgetItem(info.get("name", "")))
            table.setItem(row, 1, QTableWidgetItem(info.get("email", "")))

        layout.addWidget(table)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)
