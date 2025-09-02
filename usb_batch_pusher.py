#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USB Batch Pusher (Windows)
- Choose a file OR a folder to push
- Copy to all selected removable USB drives
- Checks free space before copying
- Optional overwrite
- Simple progress + log

Build to EXE:
  pyinstaller --noconfirm --windowed --onefile usb_batch_pusher.py
"""

import os
import sys
import queue
import threading
import shutil
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ------------- Windows drive discovery (removable USB) -----------------
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

GetLogicalDrives = kernel32.GetLogicalDrives
GetLogicalDrives.restype = wintypes.DWORD

GetDriveTypeW = kernel32.GetDriveTypeW
GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
GetDriveTypeW.restype = wintypes.UINT

# Drive type constants
DRIVE_REMOVABLE = 2

def list_removable_drives():
    """Return list of removable drive roots like ['E:\\','F:\\']"""
    drives = []
    mask = GetLogicalDrives()
    for i in range(26):
        if mask & (1 << i):
            root = f"{chr(65+i)}:\\"
            dtype = GetDriveTypeW(root)
            if dtype == DRIVE_REMOVABLE:
                drives.append(root)
    return drives

# --------------------------- helpers -----------------------------------
def human(n):
    for unit in ('B','KB','MB','GB','TB'):
        if n < 1024.0:
            return f"{n:,.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"

def folder_size_bytes(path):
    total = 0
    for d, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(d, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total

def required_size_bytes(src):
    if os.path.isdir(src):
        return folder_size_bytes(src)
    return os.path.getsize(src)

def drive_free_bytes(root):
    usage = shutil.disk_usage(root)
    return usage.free

def safe_copy_file(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)

def merge_copy_tree(src_dir, dst_dir):
    for d, _, files in os.walk(src_dir):
        rel = os.path.relpath(d, src_dir)
        out_dir = os.path.join(dst_dir, '' if rel == '.' else rel)
        os.makedirs(out_dir, exist_ok=True)
        for f in files:
            safe_copy_file(os.path.join(d, f), os.path.join(out_dir, f))

# --------------------------- worker ------------------------------------
class Copier(threading.Thread):
    def __init__(self, src_path, dest_rel, targets, overwrite, log_fn, step_fn, done_fn):
        super().__init__(daemon=True)
        self.src_path  = src_path
        self.dest_rel  = dest_rel.strip().lstrip("\\/")  # may be blank
        self.targets   = targets
        self.overwrite = overwrite
        self.log       = log_fn
        self.step      = step_fn
        self.done      = done_fn

    def run(self):
        try:
            need_bytes = required_size_bytes(self.src_path)
        except Exception as e:
            self.log(f"[!] Could not stat source: {e}")
            self.done()
            return

        total = len(self.targets)
        self.log(f"[i] Source: {self.src_path}")
        self.log(f"[i] Estimated size to copy: {human(need_bytes)}")
        self.log(f"[i] Destination path (relative on each USB): \\{self.dest_rel or '(root)'}")

        for idx, root in enumerate(self.targets, 1):
            try:
                dest_full = os.path.join(root, self.dest_rel) if self.dest_rel else root
                drive_root = os.path.splitdrive(dest_full)[0] + "\\"

                # Free space check
                free = drive_free_bytes(drive_root)
                if free < need_bytes:
                    self.log(f"[{root}] SKIP: Not enough free space ({human(free)} free, need {human(need_bytes)})")
                    self.step(idx, total)
                    continue

                if os.path.isdir(self.src_path):
                    if os.path.exists(dest_full) and self.overwrite:
                        self.log(f"[{root}] Removing existing folder: {dest_full}")
                        shutil.rmtree(dest_full, ignore_errors=True)
                    os.makedirs(dest_full, exist_ok=True)
                    self.log(f"[{root}] Copying folder → {dest_full}")
                    merge_copy_tree(self.src_path, dest_full)
                else:
                    if self.dest_rel.endswith(("\\","/")) or os.path.isdir(dest_full):
                        os.makedirs(dest_full, exist_ok=True)
                        dst_file = os.path.join(dest_full, os.path.basename(self.src_path))
                    else:
                        dst_file = dest_full
                        os.makedirs(os.path.dirname(dst_file), exist_ok=True)

                    if os.path.exists(dst_file) and self.overwrite:
                        try: os.remove(dst_file)
                        except OSError: pass

                    self.log(f"[{root}] Copying file → {dst_file}")
                    shutil.copy2(self.src_path, dst_file)

                self.log(f"[{root}] DONE")
            except Exception as e:
                self.log(f"[{root}] ERROR: {e}")
            finally:
                self.step(idx, total)

        self.log("✅ All selected drives processed.")
        self.done()

# ----------------------------- UI --------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("USB Batch Pusher")
        self.geometry("720x520")
        self.minsize(720, 520)

        self.src_path = tk.StringVar()
        self.dest_rel = tk.StringVar(value="")  # start blank
        self.overwrite = tk.BooleanVar(value=False)

        self.log_q = queue.Queue()
        self.worker = None

        self._build()
        self.scan_drives()
        self.after(100, self._drain_log)

    def _build(self):
        frm_src = ttk.LabelFrame(self, text="Source (file OR folder)")
        frm_src.pack(fill="x", padx=10, pady=8)

        ttk.Entry(frm_src, textvariable=self.src_path).pack(side="left", fill="x", expand=True, padx=8, pady=8)
        ttk.Button(frm_src, text="Pick…", command=self.pick_src).pack(side="left", padx=8, pady=8)

        frm_opts = ttk.LabelFrame(self, text="Destination on each USB")
        frm_opts.pack(fill="x", padx=10, pady=8)

        ttk.Label(frm_opts, text=r"Relative path (e.g. DiagTest\  or  scripts\bin\  or  update_all.bat):").pack(anchor="w", padx=8, pady=(8,0))
        ttk.Entry(frm_opts, textvariable=self.dest_rel).pack(fill="x", padx=8, pady=8)

        opt_row = ttk.Frame(frm_opts)
        opt_row.pack(fill="x", padx=8, pady=4)
        ttk.Checkbutton(opt_row, text="Overwrite existing", variable=self.overwrite).pack(side="left", padx=(0,12))
        ttk.Button(opt_row, text="Scan USB Drives", command=self.scan_drives).pack(side="left")

        frm_list = ttk.LabelFrame(self, text="USB Drives (removable)")
        frm_list.pack(fill="both", expand=True, padx=10, pady=8)

        self.listbox = tk.Listbox(frm_list, selectmode="extended", height=8)
        self.listbox.pack(side="left", fill="both", expand=True, padx=(8,0), pady=8)

        sb = ttk.Scrollbar(frm_list, orient="vertical", command=self.listbox.yview)
        sb.pack(side="left", fill="y", pady=8)
        self.listbox.config(yscrollcommand=sb.set)

        btns = ttk.Frame(frm_list)
        btns.pack(side="left", fill="y", padx=8, pady=8)
        ttk.Button(btns, text="Select All", command=self.select_all).pack(fill="x", pady=(0,6))
        ttk.Button(btns, text="Clear", command=self.clear_sel).pack(fill="x")

        frm_go = ttk.Frame(self)
        frm_go.pack(fill="x", padx=10, pady=8)

        self.prog = ttk.Progressbar(frm_go, length=300)
        self.prog.pack(side="left", padx=(0,10))
        self.btn_go = ttk.Button(frm_go, text="Start Copy", command=self.start_copy)
        self.btn_go.pack(side="left")

        frm_log = ttk.LabelFrame(self, text="Log")
        frm_log.pack(fill="both", expand=True, padx=10, pady=(0,10))
        self.txt = tk.Text(frm_log, height=10, wrap="word")
        self.txt.pack(fill="both", expand=True, padx=8, pady=8)

    def pick_src(self):
        path = filedialog.askopenfilename(
            title="Select source FILE (Cancel to pick a folder)",
            filetypes=[("All files","*.*")]
        )
        if not path:
            folder = filedialog.askdirectory(title="…or pick a source FOLDER")
            if folder:
                self.src_path.set(folder)
            return
        self.src_path.set(path)

    def scan_drives(self):
        self.listbox.delete(0, "end")
        drives = list_removable_drives()
        if not drives:
            self._log("No removable USB drives found.")
        for d in drives:
            free = drive_free_bytes(d)
            self.listbox.insert("end", f"{d}  (free {human(free)})")
        self._log(f"Found {len(drives)} removable drive(s).")

    def select_all(self):
        self.listbox.select_set(0, "end")

    def clear_sel(self):
        self.listbox.selection_clear(0, "end")

    def start_copy(self):
        if self.worker and self.worker.is_alive():
            return
        src = self.src_path.get().strip()
        if not src:
            messagebox.showwarning("Select Source", "Please pick a source file or folder.")
            return
        if not os.path.exists(src):
            messagebox.showerror("Missing", "Selected source does not exist.")
            return

        sel = [self.listbox.get(i) for i in self.listbox.curselection()]
        if not sel:
            messagebox.showwarning("Select Drives", "Please select at least one USB drive.")
            return
        targets = [s.split()[0] for s in sel]

        self.prog.config(value=0, maximum=len(targets))
        self.btn_go.config(state="disabled")
        self._log("----- Starting -----")

        self.worker = Copier(
            src_path=src,
            dest_rel=self.dest_rel.get(),
            targets=targets,
            overwrite=self.overwrite.get(),
            log_fn=self._log,
            step_fn=self._step,
            done_fn=self._done
        )
        self.worker.start()

    def _log(self, msg):
        self.log_q.put(str(msg))

    def _drain_log(self):
        try:
            while True:
                line = self.log_q.get_nowait()
                self.txt.insert("end", line + "\n")
                self.txt.see("end")
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    def _step(self, i, total):
        self.prog.config(value=i)

    def _done(self):
        self.btn_go.config(state="normal")
        self._log("----- Finished -----")

# ----------------------------- main ------------------------------------
if __name__ == "__main__":
    if os.name != "nt":
        messagebox.showerror("Windows Only", "This tool is for Windows (uses WinAPI for drive detection).")
        sys.exit(1)
    app = App()
    app.mainloop()
