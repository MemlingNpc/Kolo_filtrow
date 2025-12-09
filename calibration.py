import tkinter as tk
from tkinter import filedialog, messagebox
import cv2
import numpy as np
import os
import json


class CalibrationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kalibrator Multispektralny")
        self.root.geometry("950x600")

        # --- Konfiguracja globalna ---
        self.bit_depth = 65535  # Głębia 16-bit
        self.target_percent = 0.8
        self.roi_factor = 0.2
        self.filter_count = 8

        # Zmienna przechowująca indeks filtra referencyjnego (-1 = brak)
        self.ref_var = tk.IntVar(value=-1)

        # Przechowywanie referencji do widgetów wierszy
        self.rows = []

        self._build_ui()

    def _build_ui(self):
        """Buduje strukturę interfejsu graficznego."""
        # Nagłówek
        header_frame = tk.Frame(self.root)
        header_frame.pack(pady=10)
        tk.Label(header_frame, text="Konfiguracja Koła Filtrów", font=("Arial", 16, "bold")).pack()
        tk.Label(header_frame, text="Wprowadź dane kalibracyjne dla każdego filtra.").pack()

        # Ramka na tabelę filtrów
        self.scroll_frame = tk.Frame(self.root)
        self.scroll_frame.pack(fill="both", expand=True, padx=10)

        # Nagłówki tabeli
        headers = ["Poz.", "Nazwa Filtra", "Pusty?", "Plik Kalibracyjny", "Czas (ms)", "Referencja"]
        for idx, text in enumerate(headers):
            lbl = tk.Label(self.scroll_frame, text=text, font=("Arial", 10, "bold"))
            lbl.grid(row=0, column=idx, padx=5, pady=5)

        # Generowanie wierszy
        for i in range(self.filter_count):
            self._create_filter_row(i)

        # Przycisk akcji
        action_frame = tk.Frame(self.root)
        action_frame.pack(pady=20)
        tk.Button(action_frame, text="ZAPISZ KONFIGURACJĘ", command=self.calculate_and_save,
                  bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), height=2, width=25).pack()

    def _create_filter_row(self, index):
        """Tworzy pojedynczy wiersz tabeli dla danego filtra."""
        row_idx = index + 1

        # 1. Pozycja
        tk.Label(self.scroll_frame, text=str(row_idx)).grid(row=row_idx, column=0, padx=5, pady=5)

        # 2. Nazwa filtra
        entry_name = tk.Entry(self.scroll_frame, width=20)
        entry_name.insert(0, f"Filtr {row_idx}")
        entry_name.grid(row=row_idx, column=1, padx=5)

        # 3. Checkbox "Pusty"
        is_empty_var = tk.BooleanVar()
        chk_empty = tk.Checkbutton(self.scroll_frame, variable=is_empty_var,
                                   command=lambda i=index: self.toggle_empty(i))
        chk_empty.grid(row=row_idx, column=2, padx=5)

        # 4. Wybór pliku
        frame_file = tk.Frame(self.scroll_frame)
        frame_file.grid(row=row_idx, column=3, padx=5, sticky="w")

        lbl_file = tk.Label(frame_file, text="Brak pliku", fg="red", width=15, anchor="w")
        lbl_file.pack(side="left")

        btn_browse = tk.Button(frame_file, text="Wybierz...", command=lambda i=index: self.browse_file(i))
        btn_browse.pack(side="left", padx=5)

        path_var = tk.StringVar()

        # 5. Czas ekspozycji
        entry_time = tk.Entry(self.scroll_frame, width=10)
        entry_time.grid(row=row_idx, column=4, padx=5)

        # 6. Wybór referencji
        rb_ref = tk.Radiobutton(self.scroll_frame, variable=self.ref_var, value=index)
        rb_ref.grid(row=row_idx, column=5, padx=5)

        self.rows.append({
            "index": index,
            "entry_name": entry_name,
            "is_empty_var": is_empty_var,
            "chk_empty": chk_empty,
            "lbl_file": lbl_file,
            "btn_browse": btn_browse,
            "path_var": path_var,
            "entry_time": entry_time,
            "rb_ref": rb_ref
        })

    def toggle_empty(self, index):
        """Włącza/wyłącza pola edycji w zależności od stanu checkboxa 'Pusty'."""
        row = self.rows[index]
        is_empty = row["is_empty_var"].get()

        if is_empty:
            row["entry_name"].delete(0, tk.END)
            row["entry_name"].insert(0, "Pusty")
            row["entry_name"].config(state="disabled")
            row["btn_browse"].config(state="disabled")
            row["entry_time"].delete(0, tk.END)
            row["entry_time"].config(state="disabled")
            row["rb_ref"].config(state="disabled")
            row["lbl_file"].config(text="Niedostępne", fg="gray")
            row["path_var"].set("")

            if self.ref_var.get() == index:
                self.ref_var.set(-1)
        else:
            row["entry_name"].config(state="normal")
            row["entry_name"].delete(0, tk.END)
            row["entry_name"].insert(0, f"Filtr {index + 1}")
            row["btn_browse"].config(state="normal")
            row["entry_time"].config(state="normal")
            row["rb_ref"].config(state="normal")
            row["lbl_file"].config(text="Brak pliku", fg="red")

    def browse_file(self, index):
        """Otwiera okno wyboru pliku dla danego wiersza."""
        filename = filedialog.askopenfilename(
            title=f"Wybierz zdjęcie bieli dla poz. {index + 1}",
            filetypes=[("TIFF Images", "*.tif *.tiff"), ("All Files", "*.*")]
        )
        if filename:
            row = self.rows[index]
            row["path_var"].set(filename)
            short_name = os.path.basename(filename)
            if len(short_name) > 15:
                short_name = short_name[:12] + "..."
            row["lbl_file"].config(text=short_name, fg="green")

    def process_image(self, path, current_time):
        """Analizuje obraz i oblicza optymalny czas naświetlania."""
        try:
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if img is None:
                return None

            if len(img.shape) == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            h, w = img.shape
            cy, cx = h // 2, w // 2
            oy = int(h * self.roi_factor / 2)
            ox = int(w * self.roi_factor / 2)

            roi = img[cy - oy:cy + oy, cx - ox:cx + ox]
            mean_val = np.mean(roi)
            if mean_val < 1:
                mean_val = 1

            target_val = self.bit_depth * self.target_percent
            opt_time = current_time * (target_val / mean_val)
            return opt_time

        except Exception as e:
            print(f"Błąd przetwarzania {path}: {e}")
            return None

    def calculate_and_save(self):
        """Główna logika obliczania współczynników i zapisu konfiguracji."""
        ref_idx = self.ref_var.get()

        if ref_idx == -1:
            messagebox.showerror("Błąd", "Musisz wybrać filtr referencyjny!")
            return

        # 1. Przetwarzanie filtra referencyjnego
        ref_row = self.rows[ref_idx]
        ref_path = ref_row["path_var"].get()

        if not ref_path or not os.path.exists(ref_path):
            messagebox.showerror("Błąd", f"Brak poprawnego zdjęcia dla referencji (Poz. {ref_idx + 1})")
            return

        try:
            ref_time_input = float(ref_row["entry_time"].get())
        except ValueError:
            messagebox.showerror("Błąd", "Niepoprawny czas ekspozycji dla referencji.")
            return

        ref_opt_time = self.process_image(ref_path, ref_time_input)
        if ref_opt_time is None:
            messagebox.showerror("Błąd", "Nie udało się przetworzyć zdjęcia referencyjnego.")
            return

        # 2. Generowanie danych dla wszystkich filtrów
        filters_output = []

        for row in self.rows:
            idx = row["index"]
            position = idx + 1
            is_empty = row["is_empty_var"].get()
            name = row["entry_name"].get()

            filter_data = {
                "position": position,
                "name": name,
                "exposure_multiplier": 1.0
            }

            if is_empty:
                filter_data["exposure_multiplier"] = 0.1
                filter_data["name"] = "Pusty"
            elif idx == ref_idx:
                filter_data["exposure_multiplier"] = 1.0
                filter_data["name"] += " (Ref)"
            else:
                path = row["path_var"].get()
                time_str = row["entry_time"].get()

                if not path or not time_str:
                    messagebox.showwarning(
                        "Uwaga",
                        f"Filtr {position}: brak danych. Ustawiono mnożnik x1.0."
                    )
                else:
                    try:
                        curr_time = float(time_str)
                        opt_time = self.process_image(path, curr_time)
                        if opt_time:
                            multiplier = opt_time / ref_opt_time
                            filter_data["exposure_multiplier"] = round(multiplier, 4)
                    except ValueError:
                        messagebox.showerror("Błąd", f"Błędny czas dla filtru {position}")
                        return

            filters_output.append(filter_data)

        # 3. Zapis pliku
        final_json = {"filters": filters_output}
        save_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile="config.json",
            title="Zapisz plik konfiguracyjny"
        )

        if save_path:
            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(final_json, f, indent=4, ensure_ascii=False)
                messagebox.showinfo("Sukces", f"Zapisano konfigurację:\n{save_path}")
            except Exception as e:
                messagebox.showerror("Błąd zapisu", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = CalibrationApp(root)
    root.mainloop()