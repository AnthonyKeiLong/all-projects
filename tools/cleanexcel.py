import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import os
import sys
import subprocess
import re

# --- Auto-Install Required Libraries ---
def install_required_packages():
    required_packages = ['pandas', 'openpyxl', 'xlsxwriter', 'xlrd', 'pyxlsb']
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            print(f"Package '{package}' not found. Installing it now (this might take a moment)...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"Successfully installed {package}.")
            except Exception as e:
                print(f"Failed to install {package}. Please install it manually. Error: {e}")
                sys.exit(1)
                
install_required_packages()

# Now it is safe to import pandas
import pandas as pd

class ExcelCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel Test Data Cleaner")
        self.root.geometry("550x450")
        self.root.configure(padx=20, pady=20)
        
        self.file_path = None

        # --- UI Elements ---
        title_label = tk.Label(root, text="Test Report Cleaner", font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 10))

        instruction_label = tk.Label(root, text="Select the raw, exported Excel file to clean and merge its columns.", font=("Arial", 10))
        instruction_label.pack(pady=(0, 20))

        # File Selection
        file_frame = tk.Frame(root)
        file_frame.pack(fill="x", pady=5)
        
        self.btn_select = tk.Button(file_frame, text="1. Select Excel File", command=self.select_file, width=20, bg="#e0e0e0")
        self.btn_select.pack(side="left", padx=(0, 10))
        
        self.lbl_file = tk.Label(file_frame, text="No file selected...", fg="gray", wraplength=300, justify="left")
        self.lbl_file.pack(side="left", fill="x", expand=True)

        # Process Button
        self.btn_process = tk.Button(root, text="2. Clean & Process Data", command=self.process_file, state="disabled", width=25, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.btn_process.pack(pady=20)

        # Log Output
        tk.Label(root, text="Activity Log:", font=("Arial", 9, "bold")).pack(anchor="w")
        self.log_text = scrolledtext.ScrolledText(root, height=10, width=60, font=("Consolas", 9), bg="#f5f5f5")
        self.log_text.pack(fill="both", expand=True)

    def log(self, message):
        """Helper to print messages to the text box"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update()

    def get_read_engine(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext == '.xls':
            return 'xlrd'
        elif ext == '.xlsb':
            return 'pyxlsb'
        else:  # .xlsx, .xlsm, .xlam, etc.
            return 'openpyxl'

    def select_file(self):
        filetypes = (("Excel files", "*.xlsx *.xls *.xlsm *.xlsb *.xlam"), ("All files", "*.*"))
        path = filedialog.askopenfilename(title="Open Excel File", filetypes=filetypes)
        
        if path:
            self.file_path = path
            self.lbl_file.config(text=os.path.basename(path), fg="black")
            self.btn_process.config(state="normal")
            self.log(f"Selected file: {os.path.basename(path)}")

    def process_file(self):
        if not self.file_path:
            return

        self.btn_process.config(state="disabled")
        self.log("\n--- Starting processing ---")
        
        try:
            # 1. Ask user where to save the cleaned file
            ext = os.path.splitext(self.file_path)[1]
            default_out = self.file_path[:-len(ext)] + "_Cleaned.xlsx"
            save_path = filedialog.asksaveasfilename(
                title="Save Cleaned File As",
                initialfile=os.path.basename(default_out),
                defaultextension=".xlsx",
                filetypes=[("Excel Workbook", "*.xlsx")]
            )
            
            if not save_path:
                self.log("Save cancelled.")
                self.btn_process.config(state="normal")
                return

            # 2. Read the raw excel file without applying headers yet
            self.log("Reading data and dropping empty spacers...")
            engine = self.get_read_engine(self.file_path)
            self.log(f"Detected format — using engine: {engine}")
            df = pd.read_excel(self.file_path, header=None, engine=engine)

            # Drop completely empty rows and columns
            df.dropna(how='all', inplace=True)
            df.dropna(axis=1, how='all', inplace=True)

            cleaned_rows = []
            
            # 3. Iterate through rows and magically merge the split cells
            self.log("Merging split numbers, brackets, and percentages...")
            def fmt_val(v):
                """Convert a cell value to a clean string, rounding floats to 1 d.p."""
                if isinstance(v, float):
                    # Round to 1 decimal, strip trailing .0 only if it was a whole number
                    rounded = round(v, 1)
                    return str(int(rounded)) if rounded == int(rounded) else str(rounded)
                return str(v).strip()

            for index, row in df.iterrows():
                # Extract non-empty values from the row and convert to strings
                vals = [fmt_val(v) for v in row.values if pd.notna(v) and str(v).strip() != '']
                if not vals:
                    continue

                merged_vals = []
                i = 0
                while i < len(vals):
                    val = vals[i]

                    # Pattern A: next cell is a standalone "("
                    if i + 1 < len(vals) and vals[i+1] == '(':
                        combined = val + ' ('
                        i += 2
                        while i < len(vals):
                            token = vals[i]
                            combined += token
                            if ')' in token:
                                i += 1
                                break
                            i += 1
                        combined = combined.replace(' )', ')').replace('( ', '(').replace(' %', '%').replace(' .', '.')
                        merged_vals.append(combined)

                    # Pattern B: current cell ends with "(" (e.g. "8.7 (" stored as one cell)
                    elif val.endswith('(') and ')' not in val:
                        combined = val
                        i += 1
                        while i < len(vals):
                            token = vals[i]
                            combined += token
                            if ')' in token:
                                i += 1
                                break
                            i += 1
                        combined = combined.replace(' )', ')').replace('( ', '(').replace(' %', '%').replace(' .', '.')
                        merged_vals.append(combined)

                    else:
                        merged_vals.append(val)
                        i += 1
                
                cleaned_rows.append(merged_vals)

            # ── 4. Format Detection ──────────────────────────────────────────
            # Ranking Analysis rows start with class codes like "4A02" (digit+letter)
            # Questions Analysis rows start with section numbers like "2" (pure digit)
            is_ranking_format = any(
                r and re.match(r'^\d[A-Z]\d', r[0]) for r in cleaned_rows
            )

            if is_ranking_format:
                # ══════════════════════════════════════════════════════════════
                # FORMAT B: Test Ranking Analysis
                # ══════════════════════════════════════════════════════════════
                self.log("Detected format: Test Ranking Analysis")

                meta_rows, data_rows, average_row = [], [], None

                for r in cleaned_rows:
                    if not r:
                        continue
                    first = r[0].strip()
                    if any('report date' in str(v).lower() for v in r):
                        meta_rows.append(r)
                    elif first.lower().startswith('average'):
                        average_row = r
                    elif re.match(r'^\d[A-Z]', first):
                        data_rows.append(r)
                    else:
                        if any(str(v).strip() for v in r):
                            meta_rows.append(r)

                if not data_rows:
                    raise ValueError(
                        "Could not detect data rows in Ranking Analysis format.\n"
                        "Ensure class codes (e.g. 4A02) appear in the first column.")

                RANK_HDR = ['Class & Class No.', 'Mark', 'Result', 'Ranking',
                            'Correct Answer', 'Wrong Answer', 'Unanswered Question', 'Status']
                num_cols = len(RANK_HDR)

                final_data = []
                for r in data_rows:
                    # Merge split "4A" + "02" → "4A02" if stored separately
                    if (len(r) >= 2
                            and re.match(r'^\d[A-Z]+$', r[0])
                            and re.match(r'^\d+$', r[1])):
                        r = [r[0] + r[1]] + r[2:]
                    final_data.append((r + [''] * num_cols)[:num_cols])

                clean_df      = pd.DataFrame(final_data, columns=RANK_HDR)
                num_data_rows = len(clean_df)

                self.log(f"Writing clean data to:\n{save_path}")

                # Separate header meta from footer (Report Date)
                header_meta = [r for r in meta_rows
                               if not any('report date' in str(v).lower() for v in r)]
                seen_d, footer_meta = set(), []
                for r in meta_rows:
                    if any('report date' in str(v).lower() for v in r):
                        parts = [str(v) for v in r if 'report date' in str(v).lower()]
                        k = parts[0].split('Page')[0].strip() if parts else str(r)
                        if k not in seen_d:
                            seen_d.add(k)
                            footer_meta.append(r)

                # Row positions (0-indexed):
                # 0..n-1   : meta rows (title, subtitle, info lines)
                # n        : blank spacer
                # n+1      : Excel table header (green)
                # n+2..end : data rows
                # end+2    : Average mark row (green)
                # end+4    : Report Date
                num_meta     = len(header_meta)
                tbl_start    = num_meta + 1
                data_start   = tbl_start + 1
                data_end     = data_start + num_data_rows - 1
                avg_row_idx  = data_end + 2
                footer_start = avg_row_idx + 2

                with pd.ExcelWriter(save_path, engine='xlsxwriter') as writer:
                    clean_df.to_excel(writer, index=False, header=False,
                                      sheet_name='Analyzed Data', startrow=data_start)

                    wb = writer.book
                    ws = writer.sheets['Analyzed Data']

                    title_fmt = wb.add_format({'bold': True, 'font_size': 13,
                                               'align': 'center', 'valign': 'vcenter'})
                    sub_fmt   = wb.add_format({'font_size': 11, 'align': 'center',
                                               'italic': True})
                    meta_fmt  = wb.add_format({'font_size': 10})
                    avg_fmt   = wb.add_format({'bold': True, 'bg_color': '#C6EFCE', 'border': 1})
                    date_fmt  = wb.add_format({'italic': True, 'font_size': 9,
                                               'font_color': '#595959'})

                    # Write meta rows: row 0 = title (merged+bold), row 1 = subtitle
                    # (merged+italic), rows 2+ = plain text left-aligned
                    for i, r in enumerate(header_meta):
                        joined = '  '.join(str(v) for v in r if str(v).strip())
                        if i == 0:
                            ws.merge_range(i, 0, i, num_cols - 1, joined, title_fmt)
                        elif i == 1:
                            ws.merge_range(i, 0, i, num_cols - 1, joined, sub_fmt)
                        else:
                            ws.write(i, 0, joined, meta_fmt)

                    # Excel table (green header + banded rows)
                    ws.add_table(tbl_start, 0, data_end, num_cols - 1, {
                        'columns':    [{'header': col} for col in RANK_HDR],
                        'style':      'Table Style Medium 4',
                        'header_row': True
                    })

                    # Average mark row — full-width green
                    if average_row:
                        avg_padded = (average_row + [''] * num_cols)[:num_cols]
                        for ci, val in enumerate(avg_padded):
                            ws.write(avg_row_idx, ci, val, avg_fmt)

                    # Report Date footer
                    cur = footer_start
                    for r in footer_meta:
                        ws.write(cur, 0,
                                 '  '.join(str(v) for v in r if str(v).strip()),
                                 date_fmt)
                        cur += 1

                    # Auto-adjust column widths
                    for ci, col in enumerate(RANK_HDR):
                        max_len = max(clean_df[col].astype(str).map(len).max(), len(col)) + 2
                        ws.set_column(ci, ci, max_len)

            else:
                # ══════════════════════════════════════════════════════════════
                # FORMAT A: Test Questions Analysis  (original logic)
                # ══════════════════════════════════════════════════════════════
                self.log("Detected format: Test Questions Analysis")

                # 4. Categorize all rows into their respective sections
                self.log("Categorizing rows (data, metadata, averages, choice distribution)...")
                meta_rows = []
                data_rows = []
                average_row = None
                choice_dist_rows = []
                in_choice_dist = False

                for r in cleaned_rows:
                    if not r:
                        continue
                    first = r[0] if r[0] else ''
                    if 'choice distribution' in first.lower():
                        in_choice_dist = True
                        choice_dist_rows.append(r)
                    elif in_choice_dist:
                        if any(str(v).strip() for v in r):
                            choice_dist_rows.append(r)
                    elif first.lower().startswith('average'):
                        # Post-process: merge any remaining "n1 n2 %)" → "n1 (n2%)"
                        def _is_numstr(s):
                            try: float(s); return True
                            except ValueError: return False
                        cleaned_avg = []
                        j = 0
                        while j < len(r):
                            tok = r[j]
                            if (_is_numstr(tok) and
                                    j + 2 < len(r) and _is_numstr(r[j+1]) and
                                    r[j+2].endswith(')') and '%' in r[j+2]):
                                pct_part = r[j+2].replace('%)', '').replace('(', '').strip()
                                cleaned_avg.append(f"{tok} ({r[j+1]}{pct_part}%)")
                                j += 3
                            else:
                                cleaned_avg.append(tok)
                                j += 1
                        average_row = cleaned_avg
                    elif len(r) > 5 and first and first[0].isdigit():
                        data_rows.append(r)
                    else:
                        if any(str(v).strip() for v in r):
                            meta_rows.append(r)

                if not data_rows:
                    raise ValueError("Could not detect data rows. Ensure the first column (Section) contains numbers.")

                # 5. Apply the standard column headers to data rows
                headers = ['Section', 'Question', 'Correct', 'Incorrect', 'Missing',
                           'Choice 1', 'Choice 2', 'Choice 3', 'Choice 4', 'Choice 5', 'Choice 6', 'Model Answer']

                final_data = []
                for r in data_rows:
                    if len(r) >= len(headers):
                        final_data.append(r[:len(headers)])
                    else:
                        final_data.append(r + [''] * (len(headers) - len(r)))

                clean_df      = pd.DataFrame(final_data, columns=headers)
                num_data_rows = len(clean_df)
                num_cols      = len(headers)

                # 6. Save — single sheet mirroring the original layout exactly
                self.log(f"Writing clean data to:\n{save_path}")

                header_meta = [r for r in meta_rows if not any('report date' in str(v).lower() for v in r)]
                seen_dates  = set()
                footer_meta = []
                for r in meta_rows:
                    if any('report date' in str(v).lower() for v in r):
                        date_parts = [str(v) for v in r if 'report date' in str(v).lower()]
                        date_key   = date_parts[0].split('Page')[0].strip() if date_parts else str(r)
                        if date_key not in seen_dates:
                            seen_dates.add(date_key)
                            footer_meta.append(r)

                def _is_meta_info(txt):
                    return '=' in txt or (':' in txt and 'http' not in txt.lower())

                num_meta       = len(header_meta)
                blank1_row     = num_meta
                grp1_row       = blank1_row + 1
                col1_row       = grp1_row + 1
                data_start     = col1_row + 1
                data_end       = data_start + num_data_rows - 1
                b2_start       = data_end + 3
                b2_blank_row   = b2_start + num_meta
                b2_grp_row     = b2_blank_row + 1
                b2_col_row     = b2_grp_row + 1
                avg_row_idx    = b2_col_row + 1
                footer_row_idx = avg_row_idx + 2

                col_display = ['Section', 'Question', 'Correct', 'Incorrect', 'Missing',
                               '1', '2', '3', '4', '5', '6', 'Model Answer']

                with pd.ExcelWriter(save_path, engine='xlsxwriter') as writer:
                    clean_df.to_excel(writer, index=False, header=False,
                                      sheet_name='Analyzed Data', startrow=data_start)

                    workbook  = writer.book
                    worksheet = writer.sheets['Analyzed Data']

                    title_fmt    = workbook.add_format({'bold': True, 'font_size': 13,
                                                        'align': 'center', 'valign': 'vcenter'})
                    subtitle_fmt = workbook.add_format({'font_size': 11, 'align': 'center',
                                                        'italic': True})
                    meta_fmt     = workbook.add_format({'font_size': 10})
                    grp_hdr_fmt  = workbook.add_format({'bold': True, 'bg_color': '#375623',
                                                        'font_color': 'white', 'align': 'center',
                                                        'valign': 'vcenter', 'border': 1})
                    col_sub_fmt  = workbook.add_format({'bold': True, 'bg_color': '#375623',
                                                        'font_color': 'white', 'border': 1})
                    avg_fmt      = workbook.add_format({'bold': True, 'bg_color': '#C6EFCE',
                                                        'border': 1})
                    date_fmt     = workbook.add_format({'italic': True, 'font_size': 9,
                                                        'font_color': '#595959'})
                    dist_hdr_fmt = workbook.add_format({'bold': True, 'bg_color': '#375623',
                                                        'font_color': 'white', 'border': 1,
                                                        'align': 'center'})
                    dist_num_fmt = workbook.add_format({'bold': True, 'bg_color': '#E2EFDA',
                                                        'border': 1, 'align': 'center'})
                    dist_val_fmt = workbook.add_format({'bg_color': '#F9F9F9', 'border': 1})

                    def write_meta_block(ws, start_row):
                        for i, r in enumerate(header_meta):
                            joined  = '  '.join(str(v) for v in r if str(v).strip())
                            row_idx = start_row + i
                            if _is_meta_info(joined):
                                ws.write(row_idx, 0, joined, meta_fmt)
                            elif i == 0:
                                ws.merge_range(row_idx, 0, row_idx, num_cols - 1, joined, title_fmt)
                            else:
                                ws.merge_range(row_idx, 0, row_idx, num_cols - 1, joined, subtitle_fmt)

                    def write_group_header(ws, row):
                        for c in [0, 1, 11]:
                            ws.write(row, c, '', grp_hdr_fmt)
                        ws.merge_range(row, 2, row, 4, 'Accuracy (%) of Answer', grp_hdr_fmt)
                        ws.merge_range(row, 5, row, 10, 'Choice Distribution',   grp_hdr_fmt)

                    def write_col_subheaders(ws, row):
                        for c, lbl in enumerate(col_display):
                            ws.write(row, c, lbl, col_sub_fmt)

                    # Block 1: metadata + data table
                    write_meta_block(worksheet, 0)
                    write_group_header(worksheet, grp1_row)
                    worksheet.add_table(col1_row, 0, data_end, num_cols - 1, {
                        'columns':    [{'header': col} for col in col_display],
                        'style':      'Table Style Medium 4',
                        'header_row': True
                    })

                    # Block 2: repeated header + average row (mimics page 2)
                    write_meta_block(worksheet, b2_start)
                    write_group_header(worksheet, b2_grp_row)
                    write_col_subheaders(worksheet, b2_col_row)

                    if average_row:
                        target_cols = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10]
                        avg_mapped  = [''] * num_cols
                        for k, tok in enumerate(average_row):
                            if k < len(target_cols):
                                avg_mapped[target_cols[k]] = tok
                        for col_idx, val in enumerate(avg_mapped):
                            worksheet.write(avg_row_idx, col_idx, val, avg_fmt)

                    cur_footer_row = footer_row_idx
                    for r in footer_meta:
                        worksheet.write(cur_footer_row, 0,
                                        '  '.join(str(v) for v in r if str(v).strip()),
                                        date_fmt)
                        cur_footer_row += 1

                    if choice_dist_rows:
                        dist_row_idx = cur_footer_row + 1
                        for r in choice_dist_rows:
                            is_section_hdr = any('choice distribution' in str(v).lower() for v in r)
                            is_num_row     = bool(r and str(r[0]).strip().isdigit())
                            if is_section_hdr:
                                worksheet.merge_range(dist_row_idx, 0, dist_row_idx, num_cols - 1,
                                                      'Choice Distribution', dist_hdr_fmt)
                            elif is_num_row:
                                for col_idx, val in enumerate(r):
                                    worksheet.write(dist_row_idx, col_idx, val, dist_num_fmt)
                            else:
                                for col_idx, val in enumerate(r):
                                    worksheet.write(dist_row_idx, col_idx, val, dist_val_fmt)
                            dist_row_idx += 1

                    # Auto-adjust column widths
                    avg_padded_w = (average_row + [''] * num_cols)[:num_cols] if average_row else []
                    all_vals = pd.concat([clean_df,
                                          pd.DataFrame([avg_padded_w] if avg_padded_w else [],
                                                       columns=headers)])
                    for col_num, (hdr, disp) in enumerate(zip(headers, col_display)):
                        max_len = max(all_vals[hdr].astype(str).map(len).max(), len(disp)) + 2
                        worksheet.set_column(col_num, col_num, max_len)

            self.log("✅ Success! File processed successfully.")
            messagebox.showinfo("Complete", f"Successfully cleaned data and saved to:\n\n{save_path}")

        except PermissionError:
            msg = (f"Permission denied — cannot write to:\n\n{save_path}\n\n"
                   "The file is likely already open in Excel.\n"
                   "Please close it and try again.")
            self.log(f"❌ Error: {msg}")
            messagebox.showerror("Error", msg)
        except Exception as e:
            self.log(f"❌ Error: {str(e)}")
            messagebox.showerror("Error", f"An error occurred while processing:\n\n{str(e)}")
        finally:
            self.btn_process.config(state="normal")


if __name__ == "__main__":
    root = tk.Tk()
    app = ExcelCleanerApp(root)
    root.mainloop()