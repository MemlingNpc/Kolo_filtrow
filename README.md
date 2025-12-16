# System Sterowania Kołem Filtrów i Kamerą Naukową Thorlabs 

Oprogramowanie sterujące przeznaczone do automatyzacji akwizycji obrazów multispektralnych. System integruje sterowanie zmotoryzowanym kołem filtrów (opartym na mikrokontrolerze ESP32) z obsługą kamery naukowej firmy Thorlabs.

Projekt został zrealizowany w ramach pracy inżynierskiej.

## Główne funkcjonalności

* **Obsługa Kamery Thorlabs:** Pełna kontrola nad parametrami ekspozycji i wzmocnienia (Gain).
* **Wizualizacja na żywo:** Podgląd obrazu z dynamiczną normalizacją histogramu (Auto-Contrast), umożliwiający podgląd 16-bitowych danych na standardowym monitorze.
* **Sterowanie Kołem Filtrów:** Komunikacja z ESP32, obsługa 8 pozycji filtrów, inteligentny wybór najkrótszej ścieżki ruchu.
* **Zapis Danych:** Możliwość zapisu surowych danych w formacie **16-bit TIFF** (bezstratny) lub podglądu w **8-bit PNG/TIFF**.
* **Tryb Automatyczny:** Sekwencyjne wykonywanie zdjęć dla wszystkich filtrów z automatycznym doborem ekspozycji na podstawie kalibracji.
* **Dedykowana Kalibracja:** Osobne narzędzie do wyznaczania współczynników ekspozycji dla każdego filtra.

## Wymagania Sprzętowe

1.  **Komputer PC:** System Windows
2.  **Kamera:** Kompatybilna z Thorlabs TSI SDK (np. seria Zelux, CS165CU).
3.  **Koło Filtrów (Hardware):**
    * Mikrokontroler ESP32-WROOM.
    * Silnik krokowy ze sterownikiem (np. A4988).
    * Enkoder magnetyczny absolutny AS5600 (I2C).

## Wymagania Programowe

* Python 3.10+
* Biblioteki Python (wymienione w `requirements.txt`)
* **Thorlabs Scientific Imaging SDK** (należy pobrać ze strony producenta i zainstalować sterowniki).

## Instalacja

1.  **Sklonuj repozytorium:**
    ```bash
    git clone https://github.com/MemlingNpc/Kolo_filtrow.git
    cd twoj-projekt
    ```

2.  **Zainstaluj wymagane biblioteki:**
    ```bash
    pip install PySide6 opencv-python pyserial tifffile numpy
    ```

3.  **Skonfiguruj SDK Thorlabs:**
    * Zainstaluj oprogramowanie Thorlabs Windos SDK https://www.thorlabs.com/software_pages/ViewSoftwarePage.cfm?Code=ThorCam.
    * Upewnij się, że biblioteka `thorlabs_tsi_sdk` jest dostępna w Twoim środowisku Python.
    * Upewnij się, że pliki DLL są w ścieżce systemowej (PATH) lub użyj skryptu `windows_setup.py`.

## Struktura Projektu

* `main_app.py` - Główna aplikacja sterująca (GUI, PySide6).
* `workers.py` - Logika wielowątkowa (obsługa kamery i portu szeregowego).
* `calibration.py` - Narzędzie do kalibracji filtrów (Tkinter).
* `config.json` - Plik konfiguracyjny generowany przez kalibrator.
* `windows_setup.py` - Skrypt pomocniczy do ładowania DLL Thorlabs.
* `stepper.ino` - Kod źródłowy dla mikrokontrolera ESP32 (Arduino C++).

## Konfiguracja i Kalibracja

Przed rozpoczęciem pracy zaleca się przeprowadzenie kalibracji:

1.  Uruchom `calibration.py`.
2.  Dla każdego filtra wczytaj zdjęcie wzorca bieli (Flat Field).
3.  Wybierz filtr referencyjny.
4.  Kliknij "Zapisz Konfigurację" – wygeneruje to plik `config.json`.

Plik `config.json` zawiera mapowanie pozycji filtrów oraz mnożniki czasów ekspozycji.

## Uruchomienie

1.  Podłącz ESP32 oraz kamerę do portów USB.
2.  Sprawdź w Menedżerze Urządzeń numer portu COM dla ESP32 (np. COM3).
3.  Edytuj `main_app.py` (linia `self.serial_port = "COM3"`), jeśli port jest inny.
4.  Uruchom aplikację:
    ```bash
    python main_app.py
    ```

## Autorzy

**Bartosz Twardowski, Jan Landecki**
Praca Inżynierska
Politechnika Gdańska
2025


