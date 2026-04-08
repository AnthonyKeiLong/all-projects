import os
import zipfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


class BatchUnzipApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Batch Unzip")
        self.root.geometry("680x520")
        self.root.resizable(True, True)

        self.zip_files = []
        self.dest_folder = tk.StringVar()
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 5}

        # --- Destination folder ---
        dest_frame = ttk.LabelFrame(self.root, text="Destination Folder")
        dest_frame.pack(fill="x", **pad)

        ttk.Entry(dest_frame, textvariable=self.dest_folder, width=60).pack(
            side="left", fill="x", expand=True, padx=(6, 4), pady=6
        )
        ttk.Button(dest_frame, text="Browse…", command=self._browse_dest).pack(
            side="left", padx=(0, 6), pady=6
        )

        # --- Zip file list ---
        list_frame = ttk.LabelFrame(self.root, text="ZIP Files to Extract")
        list_frame.pack(fill="both", expand=True, **pad)

        btn_row = ttk.Frame(list_frame)
        btn_row.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Button(btn_row, text="Add Files…", command=self._add_files).pack(side="left", padx=2)
        ttk.Button(btn_row, text="Add Folder…", command=self._add_folder).pack(side="left", padx=2)
        ttk.Button(btn_row, text="Remove Selected", command=self._remove_selected).pack(side="left", padx=2)
        ttk.Button(btn_row, text="Clear All", command=self._clear_all).pack(side="left", padx=2)

        self.file_count_label = ttk.Label(btn_row, text="0 file(s)")
        self.file_count_label.pack(side="right", padx=6)

        list_scroll = ttk.Scrollbar(list_frame, orient="vertical")
        self.file_listbox = tk.Listbox(
            list_frame,
            selectmode="extended",
            yscrollcommand=list_scroll.set,
            activestyle="none",
        )
        list_scroll.config(command=self.file_listbox.yview)
        list_scroll.pack(side="right", fill="y", padx=(0, 6), pady=(0, 6))
        self.file_listbox.pack(fill="both", expand=True, padx=(6, 0), pady=(0, 6))

        # --- Options ---
        opt_frame = ttk.Frame(self.root)
        opt_frame.pack(fill="x", padx=10, pady=(0, 4))

        self.subfolder_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opt_frame,
            text="Extract each ZIP into its own subfolder",
            variable=self.subfolder_var,
        ).pack(side="left")

        self.overwrite_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opt_frame,
            text="Overwrite existing files",
            variable=self.overwrite_var,
        ).pack(side="left", padx=20)

        # --- Progress ---
        prog_frame = ttk.Frame(self.root)
        prog_frame.pack(fill="x", padx=10, pady=(0, 4))

        self.progress = ttk.Progressbar(prog_frame, mode="determinate")
        self.progress.pack(fill="x")

        self.status_label = ttk.Label(prog_frame, text="Ready.")
        self.status_label.pack(anchor="w", pady=(2, 0))

        # --- Run button ---
        self.run_btn = ttk.Button(self.root, text="Extract All", command=self._start_extraction)
        self.run_btn.pack(pady=(0, 10))

    # ------------------------------------------------------------------ helpers

    def _browse_dest(self):
        folder = filedialog.askdirectory(title="Select Destination Folder")
        if folder:
            self.dest_folder.set(folder)

    def _add_files(self):
        files = filedialog.askopenfilenames(
            title="Select ZIP Files",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
        )
        self._append_files(files)

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Select Folder Containing ZIP Files")
        if not folder:
            return
        found = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(".zip")
        ]
        if not found:
            messagebox.showinfo("No ZIPs", "No .zip files found in that folder.")
            return
        self._append_files(found)

    def _append_files(self, paths):
        existing = set(self.zip_files)
        added = 0
        for p in paths:
            norm = os.path.normpath(p)
            if norm not in existing:
                self.zip_files.append(norm)
                self.file_listbox.insert("end", norm)
                existing.add(norm)
                added += 1
        self._update_count()

    def _remove_selected(self):
        indices = list(self.file_listbox.curselection())
        for i in reversed(indices):
            self.file_listbox.delete(i)
            del self.zip_files[i]
        self._update_count()

    def _clear_all(self):
        self.zip_files.clear()
        self.file_listbox.delete(0, "end")
        self._update_count()

    def _update_count(self):
        self.file_count_label.config(text=f"{len(self.zip_files)} file(s)")

    # ---------------------------------------------------------------- extraction

    def _start_extraction(self):
        if not self.zip_files:
            messagebox.showwarning("No Files", "Add at least one ZIP file first.")
            return
        dest = self.dest_folder.get().strip()
        if not dest:
            messagebox.showwarning("No Destination", "Please set a destination folder.")
            return
        self.run_btn.config(state="disabled")
        thread = threading.Thread(target=self._extract_all, args=(dest,), daemon=True)
        thread.start()

    def _extract_all(self, dest):
        total = len(self.zip_files)
        errors = []

        for idx, zip_path in enumerate(self.zip_files, start=1):
            name = os.path.splitext(os.path.basename(zip_path))[0]
            self._set_status(f"Extracting {idx}/{total}: {os.path.basename(zip_path)}")
            self._set_progress(idx, total)

            if self.subfolder_var.get():
                out_dir = os.path.join(dest, name)
            else:
                out_dir = dest

            os.makedirs(out_dir, exist_ok=True)

            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    if self.overwrite_var.get():
                        zf.extractall(out_dir)
                    else:
                        for member in zf.infolist():
                            target = os.path.join(out_dir, member.filename)
                            # Prevent path traversal
                            abs_target = os.path.realpath(target)
                            abs_out = os.path.realpath(out_dir)
                            if not abs_target.startswith(abs_out + os.sep) and abs_target != abs_out:
                                errors.append(f"Skipped unsafe path: {member.filename}")
                                continue
                            if not os.path.exists(target):
                                zf.extract(member, out_dir)
            except zipfile.BadZipFile:
                errors.append(f"Bad ZIP: {zip_path}")
            except Exception as e:
                errors.append(f"{os.path.basename(zip_path)}: {e}")

        self._set_progress(total, total)

        if errors:
            summary = "\n".join(errors)
            self._set_status(f"Done with {len(errors)} error(s). See details.")
            self.root.after(0, lambda: messagebox.showwarning("Completed with Errors", summary))
        else:
            self._set_status(f"Done! {total} file(s) extracted to: {dest}")
            self.root.after(0, lambda: messagebox.showinfo("Done", f"Successfully extracted {total} ZIP file(s)."))

        self.root.after(0, lambda: self.run_btn.config(state="normal"))

    def _set_status(self, msg):
        self.root.after(0, lambda: self.status_label.config(text=msg))

    def _set_progress(self, current, total):
        value = int(current / total * 100) if total else 0
        self.root.after(0, lambda: self.progress.config(value=value))


if __name__ == "__main__":
    root = tk.Tk()
    app = BatchUnzipApp(root)
    root.mainloop()
