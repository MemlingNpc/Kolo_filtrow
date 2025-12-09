import sys
import json
import time
import os
import numpy as np
import cv2
import tifffile

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton,
    QGridLayout, QLabel, QDoubleSpinBox, QGroupBox,
    QMessageBox, QFileDialog, QComboBox
)
from PySide6.QtGui import QPixmap, QImage, QFont
from PySide6.QtCore import Qt, Slot, QThread, QThreadPool, QTimer

# Import tylko prawdziwych klas obsługi sprzętu
from workers import RealCameraService, RealSerialWorker


class FilterWheelApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # --- Konfiguracja i zmienne ---
        self.filter_config = {}
        self.current_filter_pos = 0
        self.current_science_frame = None  # Przechowuje surowe dane 16-bit

        self.load_config()

        # Zmienne dla Trybu Automatycznego
        self.auto_mode_active = False
        self.auto_mode_steps = []
        self.auto_mode_current_step = 0

        self.setWindowTitle("Sterownik Koła Filtrów i Kamery Thorlabs (16-bit TIFF)")
        self.setGeometry(100, 100, 1100, 750)

        # Inicjalizacja wątków
        self.thread_pool = QThreadPool()
        self.camera_thread = QThread()
        self.camera_worker = None

        self.is_filter_wheel_busy = False
        self.serial_port = "COM3"
        self.serial_baud = 115200

        # --- Budowa Interfejsu (GUI) ---
        main_widget = QWidget()
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # 1. Kolumna Lewa (Podgląd i Zapis)
        left_column_layout = QVBoxLayout()

        self.image_label = QLabel("Łączenie z kamerą...")
        self.image_label.setFont(QFont("Arial", 16))
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("border: 1px solid gray; background-color: #000;")
        self.image_label.setMinimumSize(640, 480)
        left_column_layout.addWidget(self.image_label, stretch=1)

        self.save_image_button = QPushButton("Zapisz obraz (TIFF)")
        self.save_image_button.setMinimumHeight(40)
        self.save_image_button.clicked.connect(self.prompt_for_save_image)
        left_column_layout.addWidget(self.save_image_button)

        main_layout.addLayout(left_column_layout, stretch=1)

        # 2. Kolumna Prawa (Sterowanie)
        right_column_layout = QVBoxLayout()

        # --- Panel Kamery ---
        camera_group_box = QGroupBox("Kontrola Kamery")
        camera_layout = QVBoxLayout()

        # Ekspozycja Bazowa
        base_exp_layout = QHBoxLayout()
        base_exp_label = QLabel("Ekspozycja Bazowa (ms):")
        self.base_exposure_spinbox = QDoubleSpinBox()
        self.base_exposure_spinbox.setRange(0.1, 10000.0)
        self.base_exposure_spinbox.setValue(10.0)
        self.base_exposure_spinbox.setSuffix(" ms")
        self.base_exposure_spinbox.valueChanged.connect(self.recalculate_current_exposure)
        base_exp_layout.addWidget(base_exp_label)
        base_exp_layout.addWidget(self.base_exposure_spinbox)
        camera_layout.addLayout(base_exp_layout)

        # Ekspozycja Aktualna (Wynikowa)
        exposure_layout = QHBoxLayout()
        exposure_label = QLabel("Aktualna Eksp. (Wynik):")
        self.exposure_spinbox = QDoubleSpinBox()
        self.exposure_spinbox.setRange(0.1, 60000.0)
        self.exposure_spinbox.setValue(10.0)
        self.exposure_spinbox.setSuffix(" ms")
        exposure_layout.addWidget(exposure_label)
        exposure_layout.addWidget(self.exposure_spinbox)
        camera_layout.addLayout(exposure_layout)

        # Wzmocnienie (Gain)
        gain_layout = QHBoxLayout()
        gain_label = QLabel("Gain (dB):")
        self.gain_spinbox = QDoubleSpinBox()
        self.gain_spinbox.setRange(0.0, 48.0)
        self.gain_spinbox.setValue(0.0)
        self.gain_spinbox.setSingleStep(0.1)
        self.gain_spinbox.setSuffix(" dB")
        gain_layout.addWidget(gain_label)
        gain_layout.addWidget(self.gain_spinbox)
        camera_layout.addLayout(gain_layout)

        # Przycisk Trybu Auto
        self.auto_mode_button = QPushButton("Uruchom Tryb Automatyczny")
        self.auto_mode_button.setMinimumHeight(40)
        self.auto_mode_button.setCheckable(True)
        self.auto_mode_button.clicked.connect(self.toggle_auto_mode)
        camera_layout.addWidget(self.auto_mode_button)

        # Wybór formatu zapisu
        format_layout = QHBoxLayout()
        format_label = QLabel("Format zapisu:")
        self.save_format_combo = QComboBox()
        self.save_format_combo.addItems(["TIFF 16-bit", "PNG 8-bit", "TIFF 8-bit"])
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.save_format_combo)
        camera_layout.addLayout(format_layout)

        camera_group_box.setLayout(camera_layout)

        # --- Panel Koła Filtrów ---
        filter_group_box = QGroupBox("Kontrola Koła Filtrów")
        filter_layout = QGridLayout()
        self.filter_buttons = []
        positions_grid = [(i, j) for i in range(4) for j in range(2)]

        # Generowanie przycisków na podstawie configu
        for i in range(1, 9):
            config_data = self.filter_config.get(i, {})
            button_name = config_data.get('name', f'Filtr {i}')
            button = QPushButton(button_name)
            button.setMinimumHeight(40)
            button.clicked.connect(lambda checked=False, num=i: self.request_filter_change(num))
            self.filter_buttons.append(button)
            pos = positions_grid[i - 1]
            filter_layout.addWidget(button, pos[0], pos[1])

        # Nawigacja Poprzedni/Następny
        nav_layout = QHBoxLayout()
        self.prev_filter_button = QPushButton("Poprzedni")
        self.prev_filter_button.clicked.connect(self.request_prev_filter)
        self.next_filter_button = QPushButton("Następny")
        self.next_filter_button.clicked.connect(self.request_next_filter)
        nav_layout.addWidget(self.prev_filter_button)
        nav_layout.addWidget(self.next_filter_button)

        main_filter_layout = QVBoxLayout()
        main_filter_layout.addLayout(filter_layout)
        main_filter_layout.addLayout(nav_layout)
        filter_group_box.setLayout(main_filter_layout)

        # --- Panel Statusu ---
        status_group_box = QGroupBox("Status Systemu")
        status_layout = QVBoxLayout()
        self.status_camera_label = QLabel("Kamera: 🟡 Inicjalizacja...")
        self.status_filter_label = QLabel("Koło filtrów: ⚪ Oczekuje")
        self.status_current_filter_label = QLabel("Aktualny filtr: ?")
        self.status_auto_mode_label = QLabel("Tryb Auto: ⚪ Nieaktywny")
        self.status_auto_mode_label.setStyleSheet("font-weight: bold;")

        status_layout.addWidget(self.status_camera_label)
        status_layout.addWidget(self.status_filter_label)
        status_layout.addWidget(self.status_current_filter_label)
        status_layout.addWidget(self.status_auto_mode_label)
        status_group_box.setLayout(status_layout)

        # Dodanie paneli do prawej kolumny
        right_column_layout.addWidget(camera_group_box)
        right_column_layout.addWidget(filter_group_box)
        right_column_layout.addWidget(status_group_box)
        right_column_layout.addStretch(1)
        main_layout.addLayout(right_column_layout, stretch=0)

        # Start systemu
        self.start_camera_service()

    # ---------------------------------------------------
    # Metody Konfiguracji
    # ---------------------------------------------------
    def load_config(self):
        try:
            with open("config.json", "r") as f:
                data = json.load(f)
                for item in data['filters']:
                    self.filter_config[item['position']] = item
            print("Wczytano konfigurację.")
        except Exception as e:
            print(f"Błąd konfiguracji: {e}")
            self.filter_config = {}

    def start_camera_service(self):
        """Uruchamia dedykowany wątek obsługi kamery."""
        self.camera_thread = QThread()
        self.camera_worker = RealCameraService()

        self.camera_worker.moveToThread(self.camera_thread)

        # Podłączenie sygnałów
        self.camera_worker.new_image.connect(self.update_image_label)
        self.camera_worker.error.connect(self.show_error_message)
        self.camera_worker.status.connect(self.update_camera_status)
        self.camera_worker.gain_supported.connect(self.on_gain_supported)

        # Sterowanie (GUI -> Worker)
        self.exposure_spinbox.valueChanged.connect(self.camera_worker.set_exposure)
        self.gain_spinbox.valueChanged.connect(self.camera_worker.set_gain)

        self.camera_thread.started.connect(self.camera_worker.start_streaming)
        self.camera_thread.start()

    # ---------------------------------------------------
    # Obsługa Koła Filtrów
    # ---------------------------------------------------
    @Slot(int)
    def request_filter_change(self, filter_number):
        if self.is_filter_wheel_busy:
            if not self.auto_mode_active:
                self.show_error_message("Koło filtrów jest zajęte. Poczekaj.")
            return

        print(f"Zmiana na filtr: {filter_number}")
        self.is_filter_wheel_busy = True
        self.status_filter_label.setText("Koło: 🟡 Wysyłam polecenie...")

        # Uruchomienie workera w puli wątków
        command = f"GOTO:{filter_number}\n"
        worker = RealSerialWorker(self.serial_port, self.serial_baud, command)

        worker.signals.serial_response.connect(self.handle_filter_response)
        worker.signals.error.connect(self.handle_filter_error)
        worker.signals.finished.connect(self.on_filter_task_finished)
        worker.signals.status.connect(self.update_filter_status)

        self.thread_pool.start(worker)

    @Slot(str)
    def handle_filter_response(self, response):
        print(f"Odpowiedź koła: {response}")
        if response.startswith("OK:"):
            filter_num = int(response.split(":")[-1])
            self.current_filter_pos = filter_num
            self.status_filter_label.setText("Koło filtrów: ✅ Gotowe")

            # Aktualizacja GUI
            config_name = self.filter_config.get(filter_num, {}).get('name', f'Pozycja {filter_num}')
            self.status_current_filter_label.setText(f"Aktualny filtr: {config_name}")

            # Przeliczenie ekspozycji na podstawie mnożnika
            multiplier = self.filter_config.get(filter_num, {}).get('exposure_multiplier')
            if multiplier is not None:
                base_val = self.base_exposure_spinbox.value()
                calculated_exposure = base_val * multiplier
                if not self.auto_mode_active:
                    self.exposure_spinbox.setValue(calculated_exposure)

            # Kontynuacja trybu automatycznego
            if self.auto_mode_active:
                self._auto_mode_set_exposure_and_wait()

        elif response.startswith("ERROR:"):
            self.handle_filter_error(response)
            if self.auto_mode_active:
                self.stop_auto_mode(error=True)

    @Slot(str)
    def handle_filter_error(self, error_message):
        self.status_filter_label.setText("Koło filtrów: ❌ Błąd")
        self.show_error_message(error_message)

    @Slot()
    def on_filter_task_finished(self):
        self.is_filter_wheel_busy = False

    @Slot(str)
    def update_filter_status(self, message):
        self.status_filter_label.setText(message)

    @Slot()
    def recalculate_current_exposure(self):
        """Przelicza ekspozycję, gdy użytkownik zmieni wartość bazową."""
        multiplier = self.filter_config.get(self.current_filter_pos, {}).get('exposure_multiplier', 1.0)
        base_value = self.base_exposure_spinbox.value()
        new_exposure = base_value * multiplier
        self.exposure_spinbox.setValue(new_exposure)

    # ---------------------------------------------------
    # Obsługa Kamery i Obrazu
    # ---------------------------------------------------
    @Slot(np.ndarray)
    def update_image_label(self, cv_img_16bit):
        """
        Odbiera i wyświetla obraz.
        1. Zapisuje surowe dane 16-bit.
        2. Normalizuje i konwertuje do 8-bit dla podglądu.
        """
        try:
            self.current_science_frame = cv_img_16bit.copy()

            if cv_img_16bit.ndim == 2:
                # Normalizacja (Auto-Contrast) dla podglądu
                display_img_8bit = cv2.normalize(
                    cv_img_16bit, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U
                )
                height, width = display_img_8bit.shape
                bytes_per_line = width
                q_img = QImage(display_img_8bit.data, width, height, bytes_per_line, QImage.Format.Format_Grayscale8)
            else:
                self.image_label.clear()
                return

            pixmap = QPixmap.fromImage(q_img)
            self.image_label.setPixmap(pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        except Exception as e:
            print(f"Błąd wyświetlania: {e}")

    @Slot(str)
    def update_camera_status(self, message):
        self.status_camera_label.setText(message)

    @Slot(bool)
    def on_gain_supported(self, is_supported):
        """Blokuje suwak Gain, jeśli kamera go nie obsługuje."""
        self.gain_spinbox.setEnabled(is_supported)
        if not is_supported:
            self.gain_spinbox.setSuffix(" (N/A)")
        else:
            self.gain_spinbox.setSuffix(" dB")

    # ---------------------------------------------------
    # Zapis Obrazu
    # ---------------------------------------------------
    @Slot()
    def prompt_for_save_image(self):
        if self.current_science_frame is None:
            self.show_error_message("Brak obrazu do zapisu.")
            return

        filter_name = self.filter_config.get(self.current_filter_pos, {}).get('name', 'filtr')
        current_setting = self.save_format_combo.currentText()

        # Ustalenie domyślnego rozszerzenia na podstawie wyboru w GUI
        if "PNG" in current_setting:
            default_ext = ".png"
            selected_filter_str = "PNG 8-bit (*.png)"
        elif "16-bit" in current_setting:
            default_ext = ".tif"
            selected_filter_str = "TIFF 16-bit (*.tif)"
        else:
            default_ext = ".tif"
            selected_filter_str = "TIFF 8-bit (*.tif)"

        suggestion = f"obraz_{filter_name.replace(' ', '_')}{default_ext}"
        filters = "TIFF 16-bit(*.tif);;PNG 8-bit(*.png);;TIFF 8-bit(*.tif)"

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Zapisz obraz", suggestion, filters, selected_filter_str
        )

        if file_path:
            self._save_image_to_path(file_path, force_format_str=selected_filter)

    def _save_image_to_path(self, file_path, force_format_str=""):
        """Logika zapisu obrazu z obsługą formatów 16-bit i 8-bit."""
        if self.current_science_frame is None:
            return False

        try:
            save_as_16bit = True

            # Decyzja o formacie na podstawie wyboru użytkownika i rozszerzenia
            if "PNG" in force_format_str or "8-bit" in force_format_str:
                save_as_16bit = False
            if file_path.lower().endswith('.png') or file_path.lower().endswith('.jpg'):
                save_as_16bit = False

            if save_as_16bit:
                # Zapis naukowy (16-bit TIFF)
                tifffile.imwrite(file_path, self.current_science_frame)
                print(f"Zapisano (16-bit): {file_path}")
            else:
                # Zapis podglądu (8-bit z auto-kontrastem)
                img_8bit = cv2.normalize(
                    self.current_science_frame, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U
                )
                cv2.imwrite(file_path, img_8bit)
                print(f"Zapisano (8-bit): {file_path}")

            return True
        except Exception as e:
            self.show_error_message(f"Błąd zapisu: {e}")
            return False

    # ---------------------------------------------------
    # Tryb Automatyczny
    # ---------------------------------------------------
    @Slot(bool)
    def toggle_auto_mode(self, checked):
        if checked:
            self.start_auto_mode()
        else:
            self.stop_auto_mode()

    def start_auto_mode(self):
        print("--- START TRYBU AUTO ---")
        self.auto_mode_active = True
        self.auto_mode_button.setText("Zatrzymaj Tryb Automatyczny")

        self.auto_mode_steps = [
            self.filter_config[key] for key in sorted(self.filter_config.keys())
        ]
        self.auto_mode_current_step = 0
        self.status_auto_mode_label.setText("Tryb Auto: 🟡 Uruchamianie...")
        self.set_ui_enabled(False)
        self._run_auto_mode_step()

    def stop_auto_mode(self, error=False):
        print("--- STOP TRYBU AUTO ---")
        self.auto_mode_active = False
        self.auto_mode_button.setChecked(False)
        self.auto_mode_button.setText("Uruchom Tryb Automatyczny")

        status_text = "Tryb Auto: ❌ Błąd" if error else "Tryb Auto: ⚪ Zakończono"
        self.status_auto_mode_label.setText(status_text)
        self.set_ui_enabled(True)

    def set_ui_enabled(self, enabled):
        """Blokuje/odblokowuje interfejs podczas pracy automatycznej."""
        for button in self.filter_buttons:
            button.setEnabled(enabled)
        self.prev_filter_button.setEnabled(enabled)
        self.next_filter_button.setEnabled(enabled)
        self.save_image_button.setEnabled(enabled)
        self.exposure_spinbox.setEnabled(enabled)
        self.gain_spinbox.setEnabled(enabled)
        self.save_format_combo.setEnabled(enabled)

        # Inteligentne odblokowanie Gain (tylko jeśli dostępny)
        if enabled and "N/A" not in self.gain_spinbox.suffix():
            self.gain_spinbox.setEnabled(True)
        elif not enabled:
            self.gain_spinbox.setEnabled(False)

    def _run_auto_mode_step(self):
        """KROK 1: Zleć zmianę filtra."""
        if not self.auto_mode_active:
            return
        if self.auto_mode_current_step >= len(self.auto_mode_steps):
            self.stop_auto_mode()
            return

        step_data = self.auto_mode_steps[self.auto_mode_current_step]
        name = step_data['name']
        self.status_auto_mode_label.setText(
            f"Tryb Auto: Krok {self.auto_mode_current_step + 1}/{len(self.auto_mode_steps)} ({name})"
        )
        self.request_filter_change(step_data['position'])

    def _auto_mode_set_exposure_and_wait(self):
        """KROK 2: Ustaw ekspozycję i czekaj na stabilizację."""
        if not self.auto_mode_active:
            return

        step_data = self.auto_mode_steps[self.auto_mode_current_step]
        multiplier = step_data.get('exposure_multiplier', 1.0)
        base_val = self.base_exposure_spinbox.value()
        target_exposure = base_val * multiplier

        self.status_auto_mode_label.setText(f"Tryb Auto: Ekspozycja {target_exposure:.1f} ms")
        self.exposure_spinbox.setValue(target_exposure)

        # Czas na stabilizację sensora (1s)
        QTimer.singleShot(1000, self._auto_mode_save_and_continue)

    def _auto_mode_save_and_continue(self):
        """KROK 3: Zapisz plik i przejdź dalej."""
        if not self.auto_mode_active:
            return

        step_data = self.auto_mode_steps[self.auto_mode_current_step]
        name = step_data['name']
        format_setting = self.save_format_combo.currentText()

        extension = ".png" if "PNG" in format_setting else ".tif"
        file_name = f"auto_{name.replace(' ', '_').replace('/', '-')}{extension}"

        self.status_auto_mode_label.setText(f"Tryb Auto: Zapis...")

        if self._save_image_to_path(file_name, force_format_str=format_setting):
            self.auto_mode_current_step += 1
            self._run_auto_mode_step()
        else:
            self.stop_auto_mode(error=True)

    # ---------------------------------------------------
    # Pomocnicze
    # ---------------------------------------------------
    @Slot()
    def request_next_filter(self):
        if self.current_filter_pos == 0:
            self.request_filter_change(1)
        elif self.current_filter_pos == 8:
            self.request_filter_change(1)
        else:
            self.request_filter_change(self.current_filter_pos + 1)

    @Slot()
    def request_prev_filter(self):
        if self.current_filter_pos == 0:
            self.request_filter_change(1)
        elif self.current_filter_pos == 1:
            self.request_filter_change(8)
        else:
            self.request_filter_change(self.current_filter_pos - 1)

    @Slot(str)
    def show_error_message(self, message):
        print(f"BŁĄD: {message}")
        QMessageBox.critical(self, "Błąd Systemu", message)

    def closeEvent(self, event):
        self.stop_auto_mode()
        if self.camera_worker:
            self.camera_worker.stop_streaming()
        if self.camera_thread:
            self.camera_thread.quit()
            self.camera_thread.wait()
        self.is_filter_wheel_busy = True
        self.thread_pool.waitForDone()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FilterWheelApp()
    window.show()
    sys.exit(app.exec())