USB Batch Pusher (Windows)
==========================

A simple Windows tool to copy a file or folder to multiple USB drives at once.

- Detects removable USB drives
- Copies a file **or** a whole folder
- Checks free space before copying
- Option to overwrite existing files
- Progress bar + log window
- Friendly destination options:
  - Copy to the root of each USB
  - Copy into a folder name (same name on every USB)
  - Create a folder using the source name
- Optional rename when source is a file
- Live preview line showing an example destination (e.g., E:\MyFolder\)

This tool is distributed as a Python script.
You build the `.exe` yourself — no prebuilt binaries are hosted.

------------------------------------------------------------

Quick Start (Recommended)
-------------------------

1. Download this repo as a ZIP:
   - Click the green 'Code' button → 'Download ZIP'
   - Extract it somewhere (e.g. Desktop)

2. Inside the extracted folder, double-click:
   build_exe.bat

   - If Python isn’t installed, the script will:
     - Try Winget to install Python
     - If Winget is missing, download Python from python.org and install silently
   - Then it will install PyInstaller, build the `.exe`, and clean up extra files.

3. When it finishes, you’ll see:
   usb_batch_pusher.exe

   in the same folder as the script.

------------------------------------------------------------

Using the App
-------------

1. Double-click usb_batch_pusher.exe.
2. Click 'Pick…' and select a file (Cancel to pick a folder).
3. Choose a destination option:
   - Copy to drive root → places it directly at E:\
   - Copy into folder named → you type the folder name (same on each USB)
   - Create a folder using the source name → automatically uses the source file/folder name
4. (Optional) If the source is a file, you can enter a new name to rename it on the USBs.
5. The Preview line updates live to show an example destination (always uses E:\ as a sample).
6. Click 'Scan USB Drives', then select drives (or 'Select All').
7. (Optional) tick 'Overwrite existing' to replace existing files.
8. Click 'Start Copy'.
9. Watch the log to confirm each drive.

------------------------------------------------------------

Manual Build (Advanced)
-----------------------

If you want to build the exe manually instead of using build_exe.bat:

1. Install Python 3 from https://www.python.org/downloads/windows/
   - Check "Add Python to PATH" during install
2. Open Command Prompt in this repo folder
3. Upgrade pip and install PyInstaller:

   pip install --upgrade pip
   pip install pyinstaller

4. Build the exe:

   pyinstaller --noconfirm --onefile --windowed usb_batch_pusher.py

5. The exe will appear at:

   dist\usb_batch_pusher.exe

6. (Optional) Clean up:

   rmdir /s /q build
   del usb_batch_pusher.spec

------------------------------------------------------------

License
-------
MIT — free to use, share, and modify
