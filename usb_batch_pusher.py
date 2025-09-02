#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USB Batch Pusher (Windows)
- Choose a file OR a folder to push
- Friendly destination options:
    1) Copy to drive root
    2) Copy into a folder named (same on each USB)
    3) Create a folder using the source name
- Optional rename when source is a FILE
- Checks free space before copying
- Optional overwrite
- Progress bar + log
- Live preview of example destination (uses E:\ as illustrative drive)

Build to EXE:
  pyinstaller --noconfirm --onefile --windowed usb_batch_pusher.py
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

DRIVE_REMOVABLE = 2

def list_removable_drives():
    """Return list of removable drive roots like ['E:\\','F:\\']"""
    drives = []
    mask = GetLogicalDrives()
    for i in range(26):
        if mask & (1 << i):
            root = f"{chr(65+i)}:\\"
            if GetDriveTypeW(root) == DRIVE_REMOVABLE:
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
    return folder_size_bytes(src) if os.path.isdir(src) else os.path.getsize(src)

def drive_free_bytes(root):
    return shutil.disk_usage(root).free

def safe_copy_file(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)

def merge_copy_tree(src_dir, dst_dir):
    """Copy folder contents into dst_dir (merge)."""
    for d, _, files in os.walk(src_dir):
        rel = os.path.relpath(d, src_dir)
        out_dir = os.path.join(dst_dir, '' if rel == '.' else rel)
        os.makedirs(out_dir, exist_ok=True)
        for f in files:
            safe_copy_file(os.path.join(d, f), os.path.join(out_dir, f))

def source_display_name(path):
    """For 'use source name' mode: folder -> folder name; file -> file stem."""
    base = os.path.basename(path.rstrip("\\/"))
    if os.path.isdir(path):
        return base
    stem, _ = os.path.splitext(base)
    return stem or base

# --------------------------- worker ------------------------------------
class Copier(threading.Thread):
    MODE_ROOT = 0
    MODE_FIXED_FOLDER = 1
    MODE_SOURCE_NAME = 2

    def __init__(self, src_path, mode, fixed_folder_name, rename_file_to,
                 targets, overwrite, log_fn, step_fn, done_fn):
        super().__init__(daemon=True)
        self.src_path = src_path
        self.mode = mode
        self.fixed_folder_name = (fixed_folder_name or "").strip().strip("\\/")
        self.rename_file_to = (rename_file_to or "").strip()
        self.targets = targets
        self.overwrite = overwrite
        self.log = log_fn
        self.step = step_fn
        self.done = done_fn

    def compute_base_dest(self, drive_root):
        if self.mode == self.MODE_ROOT:
            return drive_root
        elif self.mode == self.MODE_FIXED_FOLDER:
            return os.path.join(drive_root, self.fixed_folder_name) if self.fixed_folder_name else drive_root
        else:  # MODE_SOURCE_NAME
            return os.path.join(drive_root, source_display_name(self.src_path))

    def run(self):
        try:
            need_bytes = required_size_bytes(self.src_path)
        except Exception as e:
            self.log(f"[!] Could not stat source: {e}")
            self.done()
            return

        total = len(self.targets)
        src_is_dir = os.path.isdir(self.src_path)
        self.log(f"[i] Source: {self.src_path}")
        self.log(f"[i] Type: {'folder' if src_is_dir else 'file'}")
        self.log(f"[i] Estimated size to copy: {human(need_bytes)}")

        # Describe destination mode
        if self.mode == self.MODE_ROOT:
            self.log("[i] Destination: drive root on each USB")
        elif self.mode == self.MODE_FIXED_FOLDER:
            self.log(f"[i] Destination: folder named '{self.fixed_folder_name or '(root)'}' on each USB")
        else:
            self.log("[i] Destination: folder using the source name on each USB")

        # For file rename info
        if not src_is_dir:
            if self.rename_file_to:
                self.log(f"[i] File rename on copy: '{os.path.basename(self.src_path)}' -> '{self.rename_file_to}'")
            else:
                self.log(f"[i] File rename on copy: keep original filename")

        for idx, drive in enumerate(self.targets, 1):
            try:
                base_dest = self.compute_base_dest(drive)
                free = drive_free_bytes(drive)
                if free < need_bytes:
                    self.log(f"[{drive}] SKIP: Not enough free space ({human(free)} free, need {human(need_bytes)})")
                    self.step(idx, total)
                    continue

                if src_is_dir:
                    # Folder copy
                    if os.path.exists(base_dest) and self.overwrite:
                        self.log(f"[{drive}] Removing existing folder: {base_dest}")
                        shutil.rmtree(base_dest, ignore_errors=True)
                    os.makedirs(base_dest, exist_ok=True)
                    self.log(f"[{drive}] Copying folder into: {base_dest}")
                    merge_copy_tree(self.src_path, base_dest)
                else:
                    # File copy
                    os.makedirs(base_dest, exist_ok=True)
                    dst_name = self.rename_file_to if self.rename_file_to else os.path.basename(self.src_path)
                    dst_file = os.path.join(base_dest, dst_name)
                    if os.path.exists(dst_file) and self.overwrite:
                        try: os.remove(dst_file)
                        except OSError: pass
                    self.log(f"[{drive}] Copying file to: {dst_file}")
                    shutil.copy2(self.src_path, dst_file)

                self.log(f"[{drive}] DONE")
            except Exception as e:
                self.log(f"[{drive}] ERROR: {e}")
            finally:
                self.step(idx, total)

        self.log("✅ All selected drives processed.")
        self.done()

# ----------------------------- UI --------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("USB Batch Pusher")
        self.geometry("780x600")
        self.minsize(760, 580)

        self.src_path = tk.StringVar()
        self.overwrite = tk.BooleanVar(value=False)

        # destination mode: 0 root, 1 fixed folder name, 2 use source name
        self.dest_mode = tk.IntVar(value=Copier.MODE_ROOT)
        self.fixed_folder_name = tk.StringVar(value="")
        self.rename_file_to = tk.StringVar(value="")  # for file source only

        self.log_q = queue.Queue()
        self.worker = None

        self._build_ui()
        self.scan_drives()
        self.after(100, self._drain_log)
        self.update_preview()  # initial

    def _build_ui(self):
        # Source
        frm_src = ttk.LabelFrame(self, text="Source (file OR folder)")
        frm_src.pack(fill="x", padx=10, pady=8)

        ttk.Entry(frm_src, textvariable=self.src_path).pack(side="left", fill="x", expand=True, padx=8, pady=8)
        ttk.Button(frm_src, text="Pick…", command=self.pick_src).pack(side="left", padx=8, pady=8)

        # Destination section
        frm_dest = ttk.LabelFrame(self, text="Destination on each USB")
        frm_dest.pack(fill="x", padx=10, pady=8)

        rb_row = ttk.Frame(frm_dest)
        rb_row.pack(fill="x", padx=8, pady=(8,4))
        ttk.Radiobutton(rb_row, text="Copy to drive root", variable=self.dest_mode,
                        value=Copier.MODE_ROOT, command=self.update_preview).pack(anchor="w")
        ttk.Radiobutton(rb_row, text="Copy into folder named:", variable=self.dest_mode,
                        value=Copier.MODE_FIXED_FOLDER, command=self.update_preview).pack(anchor="w")
        # folder name entry (indented)
        ent_row = ttk.Frame(frm_dest)
        ent_row.pack(fill="x", padx=32, pady=(0,8))
        ent_fixed = ttk.Entry(ent_row, textvariable=self.fixed_folder_name)
        ent_fixed.pack(fill="x")
        ent_fixed.bind("<KeyRelease>", lambda e: self.update_preview())

        ttk.Radiobutton(frm_dest, text="Create a folder using the source name",
                        variable=self.dest_mode, value=Copier.MODE_SOURCE_NAME,
                        command=self.update_preview).pack(anchor="w", padx=8, pady=(0,4))

        # Preview line (no hardcoded names)
        self.preview_label = ttk.Label(frm_dest, text="(No source selected)")
        self.preview_label.pack(anchor="w", padx=8, pady=(4,8))

        # Optional rename (only matters if source is a FILE)
        frm_rename = ttk.LabelFrame(self, text="File rename (only applies when source is a FILE)")
        frm_rename.pack(fill="x", padx=10, pady=8)
        ttk.Label(frm_rename, text="New filename (leave blank to keep original):").pack(anchor="w", padx=8, pady=(8,0))
        ent_rename = ttk.Entry(frm_rename, textvariable=self.rename_file_to)
        ent_rename.pack(fill="x", padx=8, pady=(0,8))
        ent_rename.bind("<KeyRelease>", lambda e: self.update_preview())

        # Options + drive scan
        frm_opts = ttk.Frame(self)
        frm_opts.pack(fill="x", padx=10, pady=4)
        ttk.Checkbutton(frm_opts, text="Overwrite existing", variable=self.overwrite).pack(side="left", padx=(0,12))
        ttk.Button(frm_opts, text="Scan USB Drives", command=self.scan_drives).pack(side="left")

        # Drive list
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

        # Progress + Go
        frm_go = ttk.Frame(self)
        frm_go.pack(fill="x", padx=10, pady=8)

        self.prog = ttk.Progressbar(frm_go, length=320)
        self.prog.pack(side="left", padx=(0,10))
        self.btn_go = ttk.Button(frm_go, text="Start Copy", command=self.start_copy)
        self.btn_go.pack(side="left")

        # Log
        frm_log = ttk.LabelFrame(self, text="Log")
        frm_log.pack(fill="both", expand=True, padx=10, pady=(0,10))
        self.txt = tk.Text(frm_log, height=10, wrap="word")
        self.txt.pack(fill="both", expand=True, padx=8, pady=8)

        # trace for preview updates on variable changes
        self.dest_mode.trace_add("write", lambda *args: self.update_preview())
        self.fixed_folder_name.trace_add("write", lambda *args: self.update_preview())
        self.rename_file_to.trace_add("write", lambda *args: self.update_preview())
        self.src_path.trace_add("write", lambda *args: self.update_preview())

    # ----- actions -----
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

    def update_preview(self):
        src = self.src_path.get().strip()
        if not src:
            self.preview_label.config(text="(No source selected)")
            return

        example_drive = "E:\\"
        # compute base destination per mode
        if self.dest_mode.get() == Copier.MODE_ROOT:
            base_dest = example_drive
        elif self.dest_mode.get() == Copier.MODE_FIXED_FOLDER:
            folder = self.fixed_folder_name.get().strip("\\/")
            base_dest = os.path.join(example_drive, folder) if folder else example_drive
        else:  # MODE_SOURCE_NAME
            base_dest = os.path.join(example_drive, source_display_name(src))

        if os.path.isfile(src):
            dst_name = self.rename_file_to.get().strip() or os.path.basename(src)
            path = os.path.join(base_dest, dst_name)
        else:
            # show trailing backslash for directory target
            path = base_dest if base_dest.endswith("\\") else base_dest + "\\"

        self.preview_label.config(text=f"Example destination on E: → {path}")

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
            mode=self.dest_mode.get(),
            fixed_folder_name=self.fixed_folder_name.get(),
            rename_file_to=self.rename_file_to.get(),
            targets=targets,
            overwrite=self.overwrite.get(),
            log_fn=self._log,
            step_fn=self._step,
            done_fn=self._done
        )
        self.worker.start()

    # ----- logging/progress -----
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
        # Use a basic dialog instead of printing to a missing console window.
        tk.Tk().withdraw()
        messagebox.showerror("Windows Only", "This tool is for Windows (uses WinAPI for drive detection).")
        sys.exit(1)
    app = App()
    app.mainloop()
