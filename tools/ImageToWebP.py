import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import sys
import subprocess
import threading

# --- Auto-Install Required Libraries ---
def install_required_packages():
    required_packages = ['Pillow']
    for package in required_packages:
        try:
            __import__('PIL')
        except ImportError:
            print(f"Package '{package}' not found. Installing it now...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"Successfully installed {package}.")
            except Exception as e:
                print(f"Failed to install {package}. Please install it manually. Error: {e}")
                sys.exit(1)

install_required_packages()

try:
    from PIL import Image # type: ignore
except ImportError:
    Image = None  # type: ignore[assignment]

SUPPORTED_FORMATS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".tif", ".webp")


class ImageToWebPApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image to WebP Converter")
        self.root.geometry("620x720")
        self.root.configure(padx=20, pady=20)
        self.root.resizable(False, True)

        self.input_files = []
        self.output_dir = tk.StringVar()
        self.quality = tk.IntVar(value=85)
        self.lossless = tk.BooleanVar(value=False)
        self.delete_originals = tk.BooleanVar(value=False)
        self.keep_structure = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self):
        # Title
        tk.Label(self.root, text="Image to WebP Converter", font=("Arial", 16, "bold")).pack(pady=(0, 4))
        tk.Label(self.root, text="Convert PNG, JPG, BMP, GIF, TIFF and more to WebP format.",
                 font=("Arial", 9), fg="#555").pack(pady=(0, 14))

        # --- Input Section ---
        input_frame = tk.LabelFrame(self.root, text=" Input ", font=("Arial", 10, "bold"), padx=10, pady=8)
        input_frame.pack(fill="x", pady=(0, 10))

        btn_row = tk.Frame(input_frame)
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="Add Files", command=self.add_files, width=14, bg="#d0e8ff").pack(side="left", padx=(0, 6))
        tk.Button(btn_row, text="Add Folder", command=self.add_folder, width=14, bg="#d0e8ff").pack(side="left", padx=(0, 6))
        tk.Button(btn_row, text="Clear List", command=self.clear_files, width=10, bg="#f0d0d0").pack(side="left")

        self.file_count_label = tk.Label(input_frame, text="No files selected.", fg="#444", font=("Arial", 9))
        self.file_count_label.pack(anchor="w", pady=(6, 0))

        # File list box
        list_frame = tk.Frame(input_frame)
        list_frame.pack(fill="x", pady=(4, 0))
        self.file_listbox = tk.Listbox(list_frame, height=6, font=("Arial", 8), selectmode=tk.EXTENDED)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=scrollbar.set)
        self.file_listbox.pack(side="left", fill="x", expand=True)
        scrollbar.pack(side="right", fill="y")

        tk.Button(input_frame, text="Remove Selected", command=self.remove_selected,
                  font=("Arial", 8), fg="#a00").pack(anchor="e", pady=(4, 0))

        # --- Output Section ---
        out_frame = tk.LabelFrame(self.root, text=" Output ", font=("Arial", 10, "bold"), padx=10, pady=8)
        out_frame.pack(fill="x", pady=(0, 10))

        out_row = tk.Frame(out_frame)
        out_row.pack(fill="x")
        self.out_entry = tk.Entry(out_row, textvariable=self.output_dir, state="readonly", width=52)
        self.out_entry.pack(side="left", padx=(0, 6))
        tk.Button(out_row, text="Browse", command=self.choose_output, width=8, bg="#e0e0e0").pack(side="left")

        tk.Label(out_frame, text="Leave blank to save WebP files alongside originals.",
                 font=("Arial", 8), fg="#777").pack(anchor="w", pady=(4, 0))

        # --- Options Section ---
        opt_frame = tk.LabelFrame(self.root, text=" Options ", font=("Arial", 10, "bold"), padx=10, pady=8)
        opt_frame.pack(fill="x", pady=(0, 10))

        # Quality slider
        q_row = tk.Frame(opt_frame)
        q_row.pack(fill="x", pady=(0, 4))
        tk.Label(q_row, text="Quality:", width=12, anchor="w").pack(side="left")
        self.quality_slider = tk.Scale(q_row, from_=1, to=100, orient="horizontal",
                                       variable=self.quality, length=280, command=self._update_quality_label)
        self.quality_slider.pack(side="left")
        self.quality_val_label = tk.Label(q_row, text="85", width=4, font=("Arial", 9, "bold"), fg="#005")
        self.quality_val_label.pack(side="left")

        # Lossless checkbox
        lossless_row = tk.Frame(opt_frame)
        lossless_row.pack(fill="x", pady=(0, 4))
        tk.Checkbutton(lossless_row, text="Lossless encoding (ignores quality setting)",
                       variable=self.lossless, command=self._toggle_lossless).pack(anchor="w")

        # Delete originals
        tk.Checkbutton(opt_frame, text="Delete original files after conversion",
                       variable=self.delete_originals, fg="#a00").pack(anchor="w")

        # --- Convert Button ---
        tk.Button(self.root, text="Convert to WebP", command=self.start_conversion,
                  font=("Arial", 12, "bold"), bg="#3a7bd5", fg="white",
                  activebackground="#2a5bac", activeforeground="white",
                  height=2, cursor="hand2").pack(fill="x", pady=(6, 8))

        # --- Progress ---
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.root, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=(0, 4))

        self.status_label = tk.Label(self.root, text="Ready.", font=("Arial", 9), fg="#444", anchor="w")
        self.status_label.pack(fill="x")

    # -------------------------------------------------------------------------
    # File Management
    # -------------------------------------------------------------------------
    def add_files(self):
        files = filedialog.askopenfilenames(
            title="Select Image Files",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif *.webp"),
                       ("All Files", "*.*")]
        )
        for f in files:
            if f not in self.input_files:
                self.input_files.append(f)
        self._refresh_list()

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select Folder Containing Images")
        if not folder:
            return
        added = 0
        for root_dir, _, files in os.walk(folder):
            for fname in files:
                if fname.lower().endswith(SUPPORTED_FORMATS):
                    full_path = os.path.join(root_dir, fname)
                    if full_path not in self.input_files:
                        self.input_files.append(full_path)
                        added += 1
        if added == 0:
            messagebox.showinfo("No Images Found", "No supported image files were found in that folder.")
        self._refresh_list()

    def clear_files(self):
        self.input_files.clear()
        self._refresh_list()

    def remove_selected(self):
        selected_indices = list(self.file_listbox.curselection())
        for i in reversed(selected_indices):
            del self.input_files[i]
        self._refresh_list()

    def _refresh_list(self):
        self.file_listbox.delete(0, tk.END)
        for f in self.input_files:
            self.file_listbox.insert(tk.END, os.path.basename(f))
        count = len(self.input_files)
        self.file_count_label.config(
            text=f"{count} file{'s' if count != 1 else ''} selected." if count > 0 else "No files selected."
        )

    def choose_output(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_dir.set(folder)

    # -------------------------------------------------------------------------
    # UI helpers
    # -------------------------------------------------------------------------
    def _update_quality_label(self, _=None):
        self.quality_val_label.config(text=str(self.quality.get()))

    def _toggle_lossless(self):
        state = "disabled" if self.lossless.get() else "normal"
        self.quality_slider.config(state=state)

    def _set_ui_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        for widget in self.root.winfo_children():
            try:
                widget.config(state=state)
            except tk.TclError:
                pass

    # -------------------------------------------------------------------------
    # Conversion
    # -------------------------------------------------------------------------
    def start_conversion(self):
        if not self.input_files:
            messagebox.showwarning("No Files", "Please add at least one image file to convert.")
            return

        self._set_ui_busy(True)
        self.progress_var.set(0)
        self.status_label.config(text="Converting...", fg="#005")

        thread = threading.Thread(target=self._run_conversion, daemon=True)
        thread.start()

    def _run_conversion(self):
        total = len(self.input_files)
        success_count = 0
        fail_count = 0
        errors = []

        output_folder = self.output_dir.get().strip()
        quality = self.quality.get()
        lossless = self.lossless.get()
        delete_originals = self.delete_originals.get()

        for i, src_path in enumerate(self.input_files):
            try:
                # Determine output path
                base_name = os.path.splitext(os.path.basename(src_path))[0] + ".webp"
                if output_folder:
                    dest_path = os.path.join(output_folder, base_name)
                    os.makedirs(output_folder, exist_ok=True)
                else:
                    dest_path = os.path.join(os.path.dirname(src_path), base_name)

                # Avoid overwriting the source if it's already a webp
                if os.path.abspath(src_path) == os.path.abspath(dest_path):
                    dest_path = os.path.splitext(dest_path)[0] + "_converted.webp"

                with Image.open(src_path) as img: # type: ignore
                    # Preserve transparency where needed
                    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                        img = img.convert("RGBA")
                    else:
                        img = img.convert("RGB")

                    save_kwargs = {"format": "WEBP", "lossless": lossless}
                    if not lossless:
                        save_kwargs["quality"] = quality

                    img.save(dest_path, **save_kwargs)

                if delete_originals and os.path.abspath(src_path) != os.path.abspath(dest_path):
                    os.remove(src_path)

                success_count += 1

            except Exception as e:
                fail_count += 1
                errors.append(f"{os.path.basename(src_path)}: {e}")

            # Update progress on main thread
            progress = ((i + 1) / total) * 100
            self.root.after(0, self._update_progress, progress, i + 1, total)

        self.root.after(0, self._conversion_done, success_count, fail_count, errors)

    def _update_progress(self, progress, done, total):
        self.progress_var.set(progress)
        self.status_label.config(text=f"Converting... {done}/{total}")

    def _conversion_done(self, success_count, fail_count, errors):
        self._set_ui_busy(False)
        self.progress_var.set(100)

        if fail_count == 0:
            self.status_label.config(text=f"Done! {success_count} file(s) converted successfully.", fg="#060")
            messagebox.showinfo("Conversion Complete",
                                f"{success_count} file(s) converted to WebP successfully.")
        else:
            self.status_label.config(
                text=f"Done with errors. {success_count} succeeded, {fail_count} failed.", fg="#a00")
            error_details = "\n".join(errors[:10])
            if len(errors) > 10:
                error_details += f"\n...and {len(errors) - 10} more."
            messagebox.showwarning("Conversion Complete with Errors",
                                   f"{success_count} succeeded, {fail_count} failed.\n\nErrors:\n{error_details}")


def main():
    root = tk.Tk()
    ImageToWebPApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
