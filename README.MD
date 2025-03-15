# Gesture Mouse Control Application

This project is available for download via the [latest release](https://github.com/pqxq/GestureMouseControl/releases/latest).

![alt text](https://github.com/pqxq/GestureMouseControl/blob/main/PREVIEW.PNG)

# Used Python 3.8.0

### Full Dependency List:

**Standard Libraries** :

- `base64`
- `os`
- `math`
- `threading`
- `logging`
- `ctypes`
- `sys`
- `typing (List, Optional, Tuple)`

**Third-party Packages** :

- `opencv-python` (cv2)
- `pythoncom` (from pywin32)
- `pyautogui`
- `autopy`
- `flet`
- `numpy`
- `pygrabber`
- `comtypes`
- `pycaw`
- `mediapipe`

**Windows-specific Dependencies** :

- `pywin32` (for pythoncom)
- `comtypes` (for Windows COM integration)

**Indirect Dependencies** :

- `protobuf` (required by mediapipe)
- `pillow` (required by pyautogui)
- `screeninfo` (required by flet)

## Steps to Compile

1. First, make sure you have Flet installed:

   ```bash
   pip install flet
   ```
2. Navigate to your project folder and run the following command to compile the application:

   ```bash
   flet pack src/Main.py --name GestureControl --icon img/icon.ico --add-data "img;img" --add-data "mediapipe;mediapipe"
   ```
3. After running the command, the executable will be created in the `dist` folder with the name `GestureControl.exe`.
