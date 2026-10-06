from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QFrame, QStackedWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from views.responsive import fit_window
from utils.paths import resource_path

FIELD_LABEL_STYLE = "font-size: 12px; font-weight: 600; color: #8A8074; border: none; background: transparent;"


def field_group(label_text, widget, spacing=6):
    """
    A small caption sitting tight above its input, as one column - instead
    of adding the label and the field as two separate items directly into
    the card's main layout (which is what made them drift apart with
    whatever spacing the outer layout happened to use).
    """
    box = QVBoxLayout()
    box.setSpacing(spacing)
    lbl = QLabel(label_text)
    lbl.setStyleSheet(FIELD_LABEL_STYLE)
    box.addWidget(lbl)
    box.addWidget(widget)
    return box


class LoginView(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AE Trends - Login")
        fit_window(self, 1100, 700, min_w=720, min_h=560)

        self.setObjectName("loginWindow")
        self.setStyleSheet("#loginWindow { background-color: #F6F2E9; }")

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- LOGO ---
        logo_label = QLabel()
        pixmap = QPixmap(resource_path("ae-logo.jpg"))
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(220, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
        else:
            logo_label.setText("AE Trends System")
            logo_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #2A2421;")

        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub_title = QLabel("Point-of-Sale & Inventory Management")
        sub_title.setStyleSheet("font-size: 14px; color: #666666; margin-bottom: 20px;")

        # --- SHARED STYLES ---
        # Scoped to #authCard (an objectName selector), never a bare
        # "QFrame { ... }" type selector - a type selector would match every
        # QFrame-type descendant inside the card, and QLabel inherits QFrame
        # in Qt, so plain captions would pick up the card's border too.
        card_style = """
            QFrame#authCard {
                background-color: #FFFFFF;
                border-radius: 12px;
                border: 1px solid #E5E0D5;
            }
        """
        self.input_style = """
            QLineEdit {
                padding: 10px 12px;
                border: 1px solid #CCCCCC;
                border-radius: 6px;
                background-color: #FFFFFF;
                color: #333333;
            }
            QLineEdit:focus {
                border: 1px solid #C09E3B;
            }
        """
        self.btn_style = """
            QPushButton {
                background-color: #C09E3B;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover { background-color: #A9872E; }
        """

        # --- STACKED CARDS ---
        self.stacked_cards = QStackedWidget()
        self.stacked_cards.setFixedWidth(400)

        # 1. Login Card
        self.login_card = QFrame()
        self.login_card.setObjectName("authCard")
        self.login_card.setStyleSheet(card_style)
        l_layout = QVBoxLayout(self.login_card)
        l_layout.setContentsMargins(30, 28, 30, 28)
        l_layout.setSpacing(16)   # even rhythm between each field group / section

        l_title = QLabel("System Sign In")
        l_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2A2421; border: none;")
        l_layout.addWidget(l_title)

        self.username_input = QLineEdit()
        self.username_input.setMaxLength(30)
        self.username_input.setPlaceholderText("e.g. sarah_trends")
        self.username_input.setText("admin")
        self.username_input.setStyleSheet(self.input_style)
        l_layout.addLayout(field_group("Username", self.username_input))

        pass_layout = QHBoxLayout()
        pass_layout.setSpacing(8)
        self.password_input = QLineEdit()
        self.password_input.setMaxLength(128)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setText("admin123")
        self.password_input.setStyleSheet(self.input_style)

        self.show_pass_btn = QPushButton("Show")
        self.show_pass_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.show_pass_btn.setFixedHeight(38)
        self.show_pass_btn.setStyleSheet(
            "background-color: #E8E2D5; color: #2A2421; font-weight: bold; "
            "font-size: 11px; padding: 0 14px; border-radius: 6px; border: none;"
        )
        self.show_pass_btn.clicked.connect(self.toggle_password)

        pass_layout.addWidget(self.password_input, stretch=1)
        pass_layout.addWidget(self.show_pass_btn)

        pass_group = QVBoxLayout()
        pass_group.setSpacing(6)
        pass_label = QLabel("Password")
        pass_label.setStyleSheet(FIELD_LABEL_STYLE)
        pass_group.addWidget(pass_label)
        pass_group.addLayout(pass_layout)
        l_layout.addLayout(pass_group)

        self.remember_box = QCheckBox("Remember this Password")
        self.remember_box.setStyleSheet("color: #666666; font-size: 12px; border: none;")
        l_layout.addWidget(self.remember_box)

        self.login_button = QPushButton("Log In to Terminal")
        self.login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_button.setStyleSheet(self.btn_style)
        l_layout.addWidget(self.login_button)

        self.btn_go_to_signup = QPushButton("Don't have an account? Sign Up")
        self.btn_go_to_signup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_go_to_signup.setStyleSheet(
            "color: #C09E3B; background: transparent; border: none; font-weight: bold; font-size: 12px;"
        )
        l_layout.addWidget(self.btn_go_to_signup, alignment=Qt.AlignmentFlag.AlignCenter)

        # 2. Sign Up Card
        self.signup_card = QFrame()
        self.signup_card.setObjectName("authCard")
        self.signup_card.setStyleSheet(card_style)
        s_layout = QVBoxLayout(self.signup_card)
        s_layout.setContentsMargins(30, 28, 30, 28)
        s_layout.setSpacing(16)

        s_title = QLabel("Create Account")
        s_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2A2421; border: none;")
        s_layout.addWidget(s_title)

        self.reg_name_input = QLineEdit()
        self.reg_name_input.setMaxLength(100)
        self.reg_name_input.setPlaceholderText("Full Name")
        self.reg_name_input.setStyleSheet(self.input_style)
        s_layout.addLayout(field_group("Full Name", self.reg_name_input))

        self.reg_username_input = QLineEdit()
        self.reg_username_input.setMaxLength(30)
        self.reg_username_input.setPlaceholderText("Desired Username")
        self.reg_username_input.setStyleSheet(self.input_style)
        s_layout.addLayout(field_group("Username", self.reg_username_input))

        self.reg_password_input = QLineEdit()
        self.reg_password_input.setMaxLength(128)
        self.reg_password_input.setPlaceholderText("Password")
        self.reg_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_password_input.setStyleSheet(self.input_style)
        s_layout.addLayout(field_group("Password", self.reg_password_input))

        self.btn_submit_signup = QPushButton("Create Account")
        self.btn_submit_signup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_submit_signup.setStyleSheet(self.btn_style)
        s_layout.addWidget(self.btn_submit_signup)

        self.btn_back_to_login = QPushButton("Back to Sign In")
        self.btn_back_to_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back_to_login.setStyleSheet(
            "color: #666666; background: transparent; border: none; font-weight: bold; font-size: 12px;"
        )
        s_layout.addWidget(self.btn_back_to_login, alignment=Qt.AlignmentFlag.AlignCenter)

        # Add cards to stack
        self.stacked_cards.addWidget(self.login_card)
        self.stacked_cards.addWidget(self.signup_card)

        main_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(sub_title, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.stacked_cards, alignment=Qt.AlignmentFlag.AlignCenter)

    def toggle_password(self):
        if self.password_input.echoMode() == QLineEdit.EchoMode.Password:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_pass_btn.setText("Hide")
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_pass_btn.setText("Show")