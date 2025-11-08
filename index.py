
"""
Utilifi — минималистичный диспетчер + мини-браузер + сетевые утилиты
Файл: utilifi.py
Зависимости:
    pip install PyQt5 PyQtWebEngine psutil

Особенности:
 - Собственная рамка (frameless) с перетаскиванием
 - Слева: диспетчер процессов (просмотр + убить процесс)
 - Справа: мини-браузер (QWebEngineView) с адресной строкой
 - Снизу: сетевая панель (IP, ping)
 - Кнопка "Перезагрузить видеокарту" — эмулирует Win+Ctrl+Shift+B (Windows only)
 - Кнопка "Поддержка" — открывает https://dev.itrypro.ru/utilifi
 - Трей-иконка
"""

import sys
import platform
import socket
import subprocess
import webbrowser
import psutil
import time

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QFrame, QSystemTrayIcon,
    QMenu, QAction, QMessageBox, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QIcon, QColor, QFont

# Web engine
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False

# Windows-specific imports
if platform.system().lower() == 'windows':
    try:
        import ctypes
        WINDOWS_AVAILABLE = True
    except ImportError:
        WINDOWS_AVAILABLE = False
else:
    WINDOWS_AVAILABLE = False

APP_NAME = "Utilifi"
SUPPORT_URL = "https://dev.itrypro.ru/utilifi"

# Modern color palette
COLORS = {
    'bg_dark': '#0a0a0a',
    'bg_medium': '#141414',
    'bg_light': '#1a1a1a',
    'accent_primary': '#00d4ff',
    'accent_secondary': '#00ff88',
    'text_primary': '#ffffff',
    'text_secondary': '#b0b0b0',
    'border': '#2a2a2a',
    'danger': '#ff4757',
    'success': '#2ed573',
}


class TitleBar(QFrame):
    """Custom title bar with drag functionality and window controls"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName('titlebar')
        self.setFixedHeight(50)
        self.setStyleSheet(f'''
            #titlebar {{ 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 {COLORS['bg_dark']}, 
                    stop:1 {COLORS['bg_medium']}
                );
                border-bottom: 1px solid {COLORS['border']};
            }}
            QLabel {{ 
                color: {COLORS['text_primary']}; 
                font-size: 16px;
                font-weight: 600;
                letter-spacing: 1px;
            }}
            QPushButton {{ 
                background: transparent; 
                border: none; 
                color: {COLORS['text_secondary']};
                font-size: 14px;
                padding: 8px 16px;
                border-radius: 6px;
            }}
            QPushButton:hover {{ 
                background: {COLORS['bg_light']};
                color: {COLORS['accent_primary']};
            }}
            QPushButton#closeBtn:hover {{
                background: {COLORS['danger']};
                color: white;
            }}
        ''')
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 10, 0)
        layout.setSpacing(10)
        
        # Title with icon
        self.title = QLabel(f"⚡ {APP_NAME}")
        layout.addWidget(self.title)
        layout.addStretch()
        
        # Support button
        self.btn_support = QPushButton('💬 Поддержка')
        self.btn_support.clicked.connect(self.open_support)
        self.btn_support.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.btn_support)
        
        # Window controls
        self.btn_min = QPushButton('─')
        self.btn_min.setFixedSize(40, 40)
        self.btn_min.clicked.connect(self.minimize)
        self.btn_min.setCursor(Qt.PointingHandCursor)
        
        self.btn_close = QPushButton('✕')
        self.btn_close.setObjectName('closeBtn')
        self.btn_close.setFixedSize(40, 40)
        self.btn_close.clicked.connect(self.close)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_close)
        
        self.startPos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.startPos = event.globalPos()
            self.clickPos = self.mapToParent(event.pos())

    def mouseMoveEvent(self, event):
        if self.startPos:
            delta = event.globalPos() - self.startPos
            self.parent.move(self.parent.pos() + delta)
            self.startPos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self.startPos = None

    def minimize(self):
        self.parent.showMinimized()

    def close(self):
        self.parent.close()

    def open_support(self):
        webbrowser.open(SUPPORT_URL)


class ProcessTable(QTableWidget):
    """Enhanced process table with better styling"""
    
    def __init__(self):
        super().__init__(0, 4)
        self.setHorizontalHeaderLabels(['PID', 'Имя процесса', 'CPU %', 'Память %'])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setSelectionBehavior(self.SelectRows)
        self.setSelectionMode(self.SingleSelection)
        self.setAlternatingRowColors(True)
        
        self.setStyleSheet(f'''
            QTableWidget {{
                background: {COLORS['bg_medium']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                gridline-color: {COLORS['border']};
            }}
            QTableWidget::item {{
                padding: 8px;
            }}
            QTableWidget::item:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLORS['accent_primary']}, 
                    stop:1 {COLORS['accent_secondary']}
                );
                color: {COLORS['bg_dark']};
            }}
            QHeaderView::section {{
                background: {COLORS['bg_light']};
                color: {COLORS['text_secondary']};
                padding: 10px;
                border: none;
                border-bottom: 2px solid {COLORS['accent_primary']};
                font-weight: 600;
            }}
        ''')
        
        self.refresh()

    def refresh(self):
        """Refresh process list with error handling"""
        try:
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    info = p.info
                    if info:
                        procs.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            procs.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
            self.setRowCount(len(procs))
            
            for row, p in enumerate(procs):
                self.setItem(row, 0, QTableWidgetItem(str(p.get('pid', ''))))
                self.setItem(row, 1, QTableWidgetItem(str(p.get('name', ''))))
                self.setItem(row, 2, QTableWidgetItem(f"{p.get('cpu_percent', 0):.1f}"))
                self.setItem(row, 3, QTableWidgetItem(f"{p.get('memory_percent', 0):.1f}"))
        except Exception as e:
            print(f"Error refreshing process list: {e}")

    def get_selected_pid(self):
        """Get PID of selected process"""
        rows = sorted(set(i.row() for i in self.selectedIndexes()))
        if not rows:
            return None
        pid_item = self.item(rows[0], 0)
        return int(pid_item.text()) if pid_item else None


class UtilifiWindow(QWidget):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1200, 700)
        
        # Add drop shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)
        
        self.init_ui()
        self.setup_timers()
        self.create_tray()

    def init_ui(self):
        """Initialize the user interface"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Main container
        container = QFrame()
        container.setStyleSheet(f'''
            QFrame {{ 
                background: {COLORS['bg_dark']}; 
                border-radius: 12px; 
            }}
            QPushButton {{ 
                padding: 10px 20px; 
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
                border: none;
            }}
            QPushButton#primaryBtn {{ 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 {COLORS['accent_primary']}, 
                    stop:1 {COLORS['accent_secondary']}
                );
                color: {COLORS['bg_dark']};
                font-weight: 600;
            }}
            QPushButton#primaryBtn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 {COLORS['accent_secondary']}, 
                    stop:1 {COLORS['accent_primary']}
                );
            }}
            QPushButton#secondaryBtn {{
                background: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
            }}
            QPushButton#secondaryBtn:hover {{
                background: {COLORS['bg_medium']};
                border-color: {COLORS['accent_primary']};
            }}
            QPushButton#dangerBtn {{
                background: {COLORS['danger']};
                color: white;
            }}
            QPushButton#dangerBtn:hover {{
                background: #ff6b81;
            }}
            QLabel {{ 
                color: {COLORS['text_primary']}; 
                font-size: 13px;
            }}
            QLineEdit {{ 
                background: {COLORS['bg_medium']}; 
                color: {COLORS['text_primary']}; 
                border: 1px solid {COLORS['border']}; 
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['accent_primary']};
            }}
        ''')
        
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        
        # Title bar
        self.titlebar = TitleBar(self)
        v.addWidget(self.titlebar)
        
        # Content area
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(20)
        
        # Splitter for left/right panels
        splitter = QSplitter()
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(f'''
            QSplitter::handle {{
                background: {COLORS['border']};
            }}
        ''')
        
        # LEFT PANEL: Process Manager
        left = self.create_process_panel()
        splitter.addWidget(left)
        
        # RIGHT PANEL: Browser
        right = self.create_browser_panel()
        splitter.addWidget(right)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        content_layout.addWidget(splitter)
        
        # BOTTOM PANEL: Network utilities
        net_panel = self.create_network_panel()
        content_layout.addWidget(net_panel)
        
        v.addWidget(content)
        main_layout.addWidget(container)

    def create_process_panel(self):
        """Create the process manager panel"""
        panel = QFrame()
        panel.setStyleSheet(f'''
            QFrame {{
                background: {COLORS['bg_medium']};
                border-radius: 10px;
                border: 1px solid {COLORS['border']};
            }}
        ''')
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Header
        header = QLabel('🖥️ Диспетчер процессов')
        header.setStyleSheet(f'''
            font-size: 16px; 
            font-weight: 600; 
            color: {COLORS['text_primary']};
            padding-bottom: 10px;
        ''')
        layout.addWidget(header)
        
        # Process table
        self.proc_table = ProcessTable()
        layout.addWidget(self.proc_table)
        
        # Action buttons
        btns = QHBoxLayout()
        btns.setSpacing(10)
        
        self.btn_kill = QPushButton('🗑️ Убить процесс')
        self.btn_kill.setObjectName('dangerBtn')
        self.btn_kill.clicked.connect(self.kill_selected)
        self.btn_kill.setCursor(Qt.PointingHandCursor)
        
        self.btn_refresh = QPushButton('🔄 Обновить')
        self.btn_refresh.setObjectName('secondaryBtn')
        self.btn_refresh.clicked.connect(self.proc_table.refresh)
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        
        btns.addWidget(self.btn_kill)
        btns.addWidget(self.btn_refresh)
        layout.addLayout(btns)
        
        # GPU reset button (Windows only)
        if WINDOWS_AVAILABLE:
            self.btn_gpu = QPushButton('🎮 Перезагрузить видеокарту')
            self.btn_gpu.setObjectName('primaryBtn')
            self.btn_gpu.clicked.connect(self.reset_gpu)
            self.btn_gpu.setCursor(Qt.PointingHandCursor)
            layout.addWidget(self.btn_gpu)
        
        return panel

    def create_browser_panel(self):
        """Create the browser panel"""
        panel = QFrame()
        panel.setStyleSheet(f'''
            QFrame {{
                background: {COLORS['bg_medium']};
                border-radius: 10px;
                border: 1px solid {COLORS['border']};
            }}
        ''')
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Header
        header = QLabel('Utrifi браузер')
        header.setStyleSheet(f'''
            font-size: 16px; 
            font-weight: 600; 
            color: {COLORS['text_primary']};
            padding-bottom: 10px;
        ''')
        layout.addWidget(header)
        
        # Browser controls
        br_bar = QHBoxLayout()
        br_bar.setSpacing(10)
        
        self.btn_back = QPushButton('◀')
        self.btn_back.setObjectName('secondaryBtn')
        self.btn_back.setFixedWidth(50)
        self.btn_back.clicked.connect(self.browser_back)
        self.btn_back.setCursor(Qt.PointingHandCursor)
        
        self.btn_forward = QPushButton('▶')
        self.btn_forward.setObjectName('secondaryBtn')
        self.btn_forward.setFixedWidth(50)
        self.btn_forward.clicked.connect(self.browser_forward)
        self.btn_forward.setCursor(Qt.PointingHandCursor)
        
        self.url_edit = QLineEdit('https://www.google.com')
        self.url_edit.returnPressed.connect(self.browser_go)
        
        self.btn_go = QPushButton('Перейти')
        self.btn_go.setObjectName('primaryBtn')
        self.btn_go.clicked.connect(self.browser_go)
        self.btn_go.setCursor(Qt.PointingHandCursor)
        
        br_bar.addWidget(self.btn_back)
        br_bar.addWidget(self.btn_forward)
        br_bar.addWidget(self.url_edit)
        br_bar.addWidget(self.btn_go)
        
        layout.addLayout(br_bar)
        
        # Browser view
        if WEB_AVAILABLE:
            self.browser = QWebEngineView()
            self.browser.setUrl(QUrl(self.url_edit.text()))
            self.browser.setStyleSheet(f'''
                QWebEngineView {{
                    background: white;
                    border-radius: 8px;
                }}
            ''')
            layout.addWidget(self.browser)
        else:
            warning = QLabel('⚠️ PyQtWebEngine не установлен.\nУстановите: pip install PyQtWebEngine')
            warning.setStyleSheet(f'''
                color: {COLORS['text_secondary']};
                font-size: 14px;
                padding: 40px;
            ''')
            warning.setAlignment(Qt.AlignCenter)
            layout.addWidget(warning)
        
        return panel

    def create_network_panel(self):
        """Create the network utilities panel"""
        panel = QFrame()
        panel.setStyleSheet(f'''
            QFrame {{
                background: {COLORS['bg_medium']};
                border-radius: 10px;
                border: 1px solid {COLORS['border']};
            }}
        ''')
        
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(20)
        
        # IP display
        self.ip_label = QLabel('🌍 IP: загрузка...')
        self.ip_label.setStyleSheet(f'''
            font-size: 14px;
            font-weight: 500;
            color: {COLORS['text_primary']};
        ''')
        layout.addWidget(self.ip_label)
        
        layout.addStretch()
        
        # Ping utility
        ping_label = QLabel('📡 Ping:')
        ping_label.setStyleSheet('font-weight: 500;')
        layout.addWidget(ping_label)
        
        self.ping_edit = QLineEdit('8.8.8.8')
        self.ping_edit.setFixedWidth(150)
        self.ping_edit.returnPressed.connect(self.do_ping)
        layout.addWidget(self.ping_edit)
        
        self.btn_ping = QPushButton('Проверить')
        self.btn_ping.setObjectName('secondaryBtn')
        self.btn_ping.clicked.connect(self.do_ping)
        self.btn_ping.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.btn_ping)
        
        self.ping_result = QLabel('—')
        self.ping_result.setStyleSheet(f'''
            font-weight: 600;
            color: {COLORS['accent_primary']};
            min-width: 80px;
        ''')
        layout.addWidget(self.ping_result)
        
        return panel

    def setup_timers(self):
        """Setup periodic update timers"""
        # Process table refresh
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.proc_table.refresh)
        self.timer.start(3000)
        
        # IP update
        self.ip_timer = QTimer(self)
        self.ip_timer.timeout.connect(self.update_ip)
        self.ip_timer.start(5000)
        self.update_ip()

    def update_ip(self):
        """Update local IP address display"""
        ip = self.get_local_ip()
        self.ip_label.setText(f'🌍 IP: {ip}')

    def get_local_ip(self):
        """Get local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return 'недоступен'

    def do_ping(self):
        """Perform ping test"""
        host = self.ping_edit.text().strip()
        if not host:
            self.ping_result.setText('Введите хост')
            return
        
        self.ping_result.setText('⏳')
        QApplication.processEvents()
        
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        cmd = ['ping', param, '1', host]
        
        try:
            out = subprocess.check_output(
                cmd, 
                stderr=subprocess.STDOUT, 
                timeout=5, 
                universal_newlines=True
            )
            
            # Parse response time
            ms = 'OK'
            for line in out.splitlines():
                if 'time=' in line.lower() or 'время=' in line.lower():
                    import re
                    # Try different patterns
                    patterns = [
                        r'time[=<]\s*(\d+\.?\d*)\s*ms',
                        r'время[=<]\s*(\d+\.?\d*)\s*мс',
                        r'time[=<]\s*(\d+)ms'
                    ]
                    for pattern in patterns:
                        m = re.search(pattern, line, re.IGNORECASE)
                        if m:
                            ms = f'{m.group(1)} ms'
                            break
                    if ms != 'OK':
                        break
            
            self.ping_result.setText(f'✅ {ms}')
            self.ping_result.setStyleSheet(f'color: {COLORS["success"]}; font-weight: 600;')
            
        except subprocess.CalledProcessError:
            self.ping_result.setText('❌ Нет ответа')
            self.ping_result.setStyleSheet(f'color: {COLORS["danger"]}; font-weight: 600;')
        except subprocess.TimeoutExpired:
            self.ping_result.setText('⏱️ Таймаут')
            self.ping_result.setStyleSheet(f'color: {COLORS["danger"]}; font-weight: 600;')
        except Exception as e:
            self.ping_result.setText('⚠️ Ошибка')
            self.ping_result.setStyleSheet(f'color: {COLORS["danger"]}; font-weight: 600;')
            print(f"Ping error: {e}")

    def kill_selected(self):
        """Kill selected process"""
        pid = self.proc_table.get_selected_pid()
        if not pid:
            QMessageBox.information(
                self, 
                'Информация', 
                'Пожалуйста, выберите процесс из списка'
            )
            return
        
        reply = QMessageBox.question(
            self,
            'Подтверждение',
            f'Вы уверены, что хотите завершить процесс {pid}?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.No:
            return
        
        try:
            p = psutil.Process(pid)
            name = p.name()
            p.terminate()
            gone, alive = psutil.wait_procs([p], timeout=3)
            
            if alive:
                p.kill()
            
            QMessageBox.information(
                self, 
                'Успешно', 
                f'Процесс "{name}" (PID: {pid}) завершён'
            )
        except psutil.NoSuchProcess:
            QMessageBox.warning(
                self, 
                'Ошибка', 
                'Процесс уже не существует'
            )
        except psutil.AccessDenied:
            QMessageBox.warning(
                self, 
                'Ошибка', 
                'Недостаточно прав для завершения процесса'
            )
        except Exception as e:
            QMessageBox.warning(
                self, 
                'Ошибка', 
                f'Не удалось завершить процесс: {str(e)}'
            )
        finally:
            self.proc_table.refresh()

    def browser_go(self):
        """Navigate to URL"""
        url = self.url_edit.text().strip()
        if not url:
            return
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        if WEB_AVAILABLE:
            self.browser.setUrl(QUrl(url))
        else:
            webbrowser.open(url)

    def browser_back(self):
        """Navigate back in browser"""
        if WEB_AVAILABLE and hasattr(self, 'browser'):
            self.browser.back()

    def browser_forward(self):
        """Navigate forward in browser"""
        if WEB_AVAILABLE and hasattr(self, 'browser'):
            self.browser.forward()

    def create_tray(self):
        """Create system tray icon"""
        self.tray = QSystemTrayIcon(self)
        
        # Try to set an icon (you can replace with actual icon file)
        try:
            icon = QIcon.fromTheme('utilities-system-monitor')
            if icon.isNull():
                # Create a simple colored icon as fallback
                from PyQt5.QtGui import QPixmap, QPainter
                pixmap = QPixmap(64, 64)
                pixmap.fill(QColor(COLORS['accent_primary']))
                icon = QIcon(pixmap)
            self.tray.setIcon(icon)
        except Exception:
            pass
        
        self.tray.setToolTip(APP_NAME)
        
        # Tray menu
        menu = QMenu()
        
        show_act = QAction('Показать', self)
        show_act.triggered.connect(self.show_window)
        
        quit_act = QAction('Выход', self)
        quit_act.triggered.connect(QApplication.instance().quit)
        
        menu.addAction(show_act)
        menu.addSeparator()
        menu.addAction(quit_act)
        
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()

    def tray_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    def show_window(self):
        """Show and activate window"""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def reset_gpu(self):
        """Reset GPU driver (Windows only - Win+Ctrl+Shift+B)"""
        if not WINDOWS_AVAILABLE:
            QMessageBox.warning(
                self,
                'Недоступно',
                'Эта функция доступна только в Windows'
            )
            return
        
        try:
            user32 = ctypes.windll.user32
            
            # Virtual key codes
            VK_LWIN = 0x5B
            VK_CONTROL = 0x11
            VK_SHIFT = 0x10
            VK_B = 0x42
            
            def keybd(vk, down=True):
                """Helper function for keyboard events"""
                flags = 0 if down else 2  # KEYEVENTF_KEYUP = 2
                user32.keybd_event(vk, 0, flags, 0)
            
            # Press keys
            keybd(VK_LWIN, True)
            keybd(VK_CONTROL, True)
            keybd(VK_SHIFT, True)
            keybd(VK_B, True)
            time.sleep(0.1)
            
            # Release keys
            keybd(VK_B, False)
            keybd(VK_SHIFT, False)
            keybd(VK_CONTROL, False)
            keybd(VK_LWIN, False)
            
            QMessageBox.information(
                self,
                'Успешно',
                'Команда перезагрузки видеокарты отправлена'
            )
            
        except Exception as e:
            QMessageBox.warning(
                self,
                'Ошибка',
                f'Не удалось выполнить команду: {str(e)}'
            )

    def closeEvent(self, event):
        """Handle window close event"""
        reply = QMessageBox.question(
            self,
            'Подтверждение',
            'Свернуть в трей или выйти из приложения?',
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Cancel
        )
        
        if reply == QMessageBox.Yes:
            # Minimize to tray
            event.ignore()
            self.hide()
        elif reply == QMessageBox.No:
            # Exit application
            self.tray.hide()
            event.accept()
        else:
            # Cancel
            event.ignore()


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle('Fusion')  # Modern cross-platform style
    
    # Set application font
    font = QFont('Segoe UI', 10)
    app.setFont(font)
    
    w = UtilifiWindow()
    w.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
