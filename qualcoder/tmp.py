import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QProgressBar, QPushButton, QLabel, QStyleFactory
from PyQt6.QtGui import QPalette

styles = ['Fusion', 'Windows', 'Basic', 'Universal']
style_idx = -1

class AppDemo(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Progress Bar Busy Indicator Demo')
        self.setGeometry(300, 300, 300, 200)
        
        layout = QVBoxLayout()

        # Create a progress bar
        self.progress_bar = QProgressBar()
        
        #styleStr = "QProgressBar::chunk {"
        #styleStr += "width: 1px;"
        #styleStr += "background-color: qlineargradient(spread:reflect, x1:0, y1:0, x2:0.5, y2:0, stop:0 white, stop:1 #aaaaaa); "
        #styleStr += "}"
        #print(styleStr)
        #self.progress_bar.setStyleSheet(styleStr)
        
        # Set it to 'busy' state
        self.progress_bar.setRange(0, 0)

        layout.addWidget(self.progress_bar)
        
        self.label_style = QLabel()
        #self.label_style.setText(styles[style_idx])
        layout.addWidget(self.label_style)
        
        # Add a button to switch styles
        self.toggle_style_button = QPushButton("Toggle Style")
        self.toggle_style_button.clicked.connect(self.toggle_style)
        layout.addWidget(self.toggle_style_button)

        self.setLayout(layout)
        self.toggle_style()
        
    def toggle_style(self):
        global style_idx
        style_idx += 1
        if style_idx > 3:
            style_idx = 0
        QApplication.instance().setStyle(styles[style_idx])
        #self.progress_bar.setStyle(QStyleFactory.create(styles[style_idx]))
        palette = self.palette()
        default_color = palette.color(QPalette.ColorRole.Highlight)
        
        # Apply this color to the progress bar chunk
        self.progress_bar.setStyleSheet(f"""
            QProgressBar::chunk {{
                background-color: {default_color.name()};
            }}
        """)

        self.label_style.setText(styles[style_idx])

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Set the style to 'Fusion'
    app.setStyle("fusion")
    
    demo = AppDemo()
    demo.show()
    
    sys.exit(app.exec())
