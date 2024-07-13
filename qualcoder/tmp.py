from PyQt6.QtWidgets import QApplication, QMainWindow, QProgressBar, QPushButton, QVBoxLayout, QWidget
from PyQt6.QtCore import QTimer

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.progressBar = QProgressBar(self)
        self.progressBar.setRange(0, 0)  # Set the progress bar to indeterminate mode
        self.progressBar.setTextVisible(False)

        self.startButton = QPushButton("Start", self)
        self.startButton.clicked.connect(self.start_progress)

        self.stopButton = QPushButton("Stop", self)
        self.stopButton.clicked.connect(self.stop_progress)

        layout = QVBoxLayout()
        layout.addWidget(self.progressBar)
        layout.addWidget(self.startButton)
        layout.addWidget(self.stopButton)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def start_progress(self):
        self.progressBar.setRange(0, 0)  # Set the progress bar to indeterminate mode

    def stop_progress(self):
        self.progressBar.setRange(0, 100)  # Set the progress bar back to determinate mode

if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()