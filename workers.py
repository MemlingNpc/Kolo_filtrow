import time
import numpy as np
import serial
import cv2

from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThread, QTimer

# --- Konfiguracja SDK Thorlabs ---
try:
    from windows_setup import configure_path

    configure_path()
except ImportError:
    pass  # Ignoruj brak pliku, jeśli środowisko jest już skonfigurowane

try:
    from thorlabs_tsi_sdk.tl_camera import TLCameraSDK

    THORLABS_SDK_AVAILABLE = True
except ImportError:
    THORLABS_SDK_AVAILABLE = False
    print("OSTRZEŻENIE: Nie znaleziono SDK Thorlabs.")


# -----------------------------------------------------------------
# PRACOWNIK KAMERY (RealCameraService)
# Działa w dedykowanym wątku QThread
# -----------------------------------------------------------------

class RealCameraService(QObject):
    """
    Obsługuje fizyczną kamerę Thorlabs.
    Działa w pętli nieblokującej, wykorzystując QTimer do pobierania klatek.
    """
    # Sygnały do komunikacji z GUI
    new_image = Signal(np.ndarray)
    error = Signal(str)
    status = Signal(str)
    gain_supported = Signal(bool)

    def __init__(self):
        super().__init__()
        self._is_running = False
        self.sdk = None
        self.camera = None
        self.timer = None

    @Slot()
    def start_streaming(self):
        """Inicjalizuje kamerę i rozpoczyna pobieranie klatek."""
        if not THORLABS_SDK_AVAILABLE:
            self.error.emit("Nie znaleziono bibliotek SDK Thorlabs.")
            return

        try:
            self.sdk = TLCameraSDK()
            available_cameras = self.sdk.discover_available_cameras()

            if len(available_cameras) < 1:
                self.error.emit("Nie wykryto żadnej kamery.")
                return

            # Otwarcie pierwszej dostępnej kamery
            self.camera = self.sdk.open_camera(available_cameras[0])
            self.status.emit("Kamera: ✅ Połączona")

            # Sprawdzenie obsługi wzmocnienia (Gain)
            try:
                min_gain = self.camera.gain_range.min
                max_gain = self.camera.gain_range.max
                print(f"Kamera obsługuje Gain: {min_gain} - {max_gain}")
                self.gain_supported.emit(True)
            except Exception:
                print("Kamera NIE obsługuje Gain.")
                self.gain_supported.emit(False)

            # Konfiguracja początkowa
            try:
                self.camera.exposure_time_us = 14000
            except Exception:
                pass

            self.camera.frames_per_trigger_zero_for_unlimited = 0
            self.camera.image_poll_timeout_ms = 1000
            self.camera.arm(2)
            self.camera.issue_software_trigger()

            # Uruchomienie pętli akwizycji (timer co 0ms = tak szybko jak to możliwe)
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._produce_frame)
            self.timer.start(0)
            self._is_running = True

        except Exception as e:
            self.error.emit(f"Błąd krytyczny kamery: {e}")
            self.stop_streaming()

    @Slot()
    def _produce_frame(self):
        """Pobiera pojedynczą klatkę z bufora kamery."""
        if not self._is_running:
            return
        try:
            frame = self.camera.get_pending_frame_or_null()
            if frame is not None:
                # Kopiowanie danych obrazu do tablicy NumPy
                image_buffer_copy = np.copy(frame.image_buffer)
                numpy_image_16bit = image_buffer_copy.reshape(
                    self.camera.image_height_pixels,
                    self.camera.image_width_pixels
                )
                self.new_image.emit(numpy_image_16bit)
        except Exception as e:
            self.error.emit(f"Błąd akwizycji: {e}")
            self.stop_streaming()

    @Slot(float)
    def set_exposure(self, ms):
        """Ustawia czas ekspozycji w milisekundach."""
        if self.camera and self._is_running:
            try:
                self.camera.exposure_time_us = int(ms * 1000)
            except Exception as e:
                print(f"Błąd ustawiania ekspozycji: {e}")

    @Slot(float)
    def set_gain(self, db_value):
        """Ustawia wzmocnienie (Gain) w dB, konwertując je na indeks kamery."""
        if self.camera and self._is_running:
            try:
                raw_index = self.camera.convert_decibels_to_gain(db_value)
                self.camera.gain = raw_index
                real_db = self.camera.convert_gain_to_decibels(raw_index)
                print(f"[Kamera] Gain: {db_value:.2f} dB -> {real_db:.2f} dB")
            except Exception as e:
                print(f"Błąd ustawiania Gain: {e}")

    @Slot()
    def stop_streaming(self):
        """Zatrzymuje akwizycję i zwalnia zasoby kamery."""
        self._is_running = False
        if self.timer:
            self.timer.stop()

        try:
            if self.camera:
                self.camera.disarm()
                self.camera.dispose()
            if self.sdk:
                self.sdk.dispose()
        except Exception as e:
            print(f"Błąd zamykania: {e}")
        finally:
            self.camera = None
            self.sdk = None
            self.status.emit("Kamera: 🔴 Rozłączona")


# -----------------------------------------------------------------
# PRACOWNIK KOŁA FILTRÓW (RealSerialWorker)
# Działa jako zadanie w QThreadPool
# -----------------------------------------------------------------

class SerialWorkerSignals(QObject):
    """Sygnały pomocnicze dla QRunnable."""
    serial_response = Signal(str)
    error = Signal(str)
    finished = Signal()
    status = Signal(str)


class RealSerialWorker(QRunnable):
    """
    Obsługuje komunikację z mikrokontrolerem ESP32 przez port szeregowy.
    Wysyła komendę i oczekuje na odpowiedź.
    """

    def __init__(self, port, baud, command):
        super().__init__()
        self.signals = SerialWorkerSignals()
        self.port = port
        self.baud = baud
        self.command = command
        self.timeout_sec = 5

    @Slot()
    def run(self):
        ser = None
        try:
            # Otwarcie portu
            ser = serial.Serial(self.port, self.baud, timeout=1)

            # Pauza na reset DTR (można zmniejszyć jeśli ESP32 się nie resetuje)
            time.sleep(2)
            ser.flushInput()

            # Wysłanie komendy
            self.signals.status.emit("Koło: 🟡 Wysyłam polecenie...")
            ser.write(self.command.encode('utf-8'))

            # Oczekiwanie na odpowiedź
            response = ""
            start_time = time.time()
            while time.time() - start_time < self.timeout_sec:
                line = ser.readline().decode('utf-8').strip()
                if not line:
                    continue
                # Szukamy potwierdzenia OK lub błędu ERROR
                if line.startswith("OK:") or line.startswith("ERROR:"):
                    response = line
                    break

            if response:
                self.signals.serial_response.emit(response)
            else:
                self.signals.error.emit(f"Błąd koła: Brak odpowiedzi z {self.port}")

        except serial.SerialException as e:
            self.signals.error.emit(f"Błąd portu COM: {e}")
        except Exception as e:
            self.signals.error.emit(f"Nieznany błąd: {e}")
        finally:
            if ser and ser.is_open:
                ser.close()
            self.signals.finished.emit()