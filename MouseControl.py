import cv2, base64, os, pythoncom, time, math, pyautogui, autopy
import flet as ft
import numpy as np
import HandTrackingModule as htm
from pygrabber.dshow_graph import FilterGraph
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import threading

# Camera settings
wCam, hCam = 640, 480

detector = htm.handDetector(maxHands=1, detectionCon=0.85, trackCon=0.8)

devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume = cast(interface, POINTER(IAudioEndpointVolume))
minVol, maxVol = -63, volume.GetVolumeRange()[1]

# Gesture-related variables
tipIds = [4, 8, 12, 16, 20]
mode, active = '', False
smooth_factor, prev_x, prev_y = 0.2, 0, 0

pyautogui.FAILSAFE = False

def list_webcams():
    """Lists available webcams."""
    pythoncom.CoInitialize()
    devices = FilterGraph().get_input_devices()
    pythoncom.CoUninitialize()
    return devices

class WebcamView(ft.UserControl):
    def __init__(self):
        super().__init__()
        self.is_running, self.cap, self.thread = False, None, None
        self.img_path, self.selected_webcam_index = "nocam.jpg", None
        self.start_stop_button, self.frame = None, None
        self.img = ft.Image(border_radius=ft.border_radius.all(20))
    
    def did_mount(self):
        self.set_default_image()
        self.update_webcam()
    
    def set_default_image(self):
        """Sets the default preview image when no webcam is active."""
        if os.path.exists(self.img_path):
            with open(self.img_path, "rb") as image_file:
                self.img.src_base64 = base64.b64encode(image_file.read()).decode("utf-8")
        self.update()

    def get_finger_state(self, lmList):
        """Returns a list indicating which fingers are up."""
        return [
            1 if lmList[tipIds[0]][1] > lmList[tipIds[0] - 1][1] else 0,
            *[1 if lmList[tipIds[i]][2] < lmList[tipIds[i] - 2][2] else 0 for i in range(1, 5)]
        ]

    def adjust_volume(self, lmList):
        """Adjusts system volume based on pinch distance."""
        x1, y1, x2, y2 = *lmList[4][1:], *lmList[8][1:]
        length = math.hypot(x2 - x1, y2 - y1)
        vol = np.clip(np.interp(length, [50, 200], [minVol, maxVol]), minVol, maxVol)
        volume.SetMasterVolumeLevel(vol, None)
            # Drawing UI elements
        cv2.line(self.frame, (x1, y1), (x2, y2), (255, 255, 255), 2)
        cv2.circle(self.frame, ((x1 + x2) // 2, (y1 + y2) // 2), 6, (0, 0, 255), cv2.FILLED)

    def move_cursor(self, lmList):
        """Moves cursor smoothly based on index finger position."""
        global prev_x, prev_y
        x1, y1 = lmList[8][1:]
        w, h = autopy.screen.size()
        target_x, target_y = int(np.interp(x1, [110, 620], [w - 1, 0])), int(np.interp(y1, [20, 350], [0, h - 1]))
        prev_x, prev_y = int(prev_x * (1 - smooth_factor) + target_x * smooth_factor), int(prev_y * (1 - smooth_factor) + target_y * smooth_factor)
        autopy.mouse.move(prev_x, prev_y)
        if lmList[4][1] < lmList[8][1]:
            pyautogui.click()

    def update_webcam(self):
        """Handles webcam streaming in a separate thread."""
        global mode, active
        if not self.cap or not self.is_running:
            return
        
        while self.is_running:
            success, self.frame = self.cap.read()
            if not success:
                continue
            
            self.frame = detector.findHands(self.frame)
            lmList = detector.findPosition(self.frame, draw=False)
            
            if lmList:
                fingers = self.get_finger_state(lmList)
                new_mode = ('Scroll' if fingers in ([0, 1, 0, 0, 0], [0, 1, 1, 0, 0]) else
                            'Volume' if fingers == [1, 1, 0, 0, 0] else
                            'Cursor' if fingers == [1, 1, 1, 1, 1] else 'N')
                if new_mode != 'N':
                    mode, active = new_mode, True
                if mode == 'Scroll':
                    pyautogui.scroll(300 if fingers == [0, 1, 0, 0, 0] else -300 if fingers == [0, 1, 1, 0, 0] else 0)
                elif mode == 'Volume':
                    self.adjust_volume(lmList)
                elif mode == 'Cursor':
                    self.move_cursor(lmList)
                if fingers[1:] == [0, 0, 0, 0]:
                    active, mode = False, 'N'
            
            _, im_arr = cv2.imencode('.png', self.frame)
            self.img.src_base64 = base64.b64encode(im_arr).decode("utf-8")
            self.update()
            time.sleep(0.03)

    def toggle_webcam(self, _):
        """Toggles webcam state."""
        if self.is_running:
            global mode, active
            self.is_running, mode, active = False, '', False
            if self.cap:
                self.cap.release()
            self.cap, self.thread = None, None
            self.start_stop_button.text = "Start"
            self.set_default_image()
        else:
            if self.selected_webcam_index is None:
                return
            self.is_running, self.start_stop_button.text = True, "Stop"
            self.cap = cv2.VideoCapture(self.selected_webcam_index)
            self.cap.set(3, wCam), self.cap.set(4, hCam)
            self.thread = threading.Thread(target=self.update_webcam)
            self.thread.start()
        self.update()

    def dropdown_change(self, e):
        """Updates the selected webcam index."""
        self.selected_webcam_index = int(e.control.value) if e.control.value else None
        self.update()

    def build(self):
        """Builds the UI components."""
        webcam_list = list_webcams()
        dropdown = ft.Dropdown(label="Select Webcam", options=[ft.dropdown.Option(str(i), text=name) for i, name in enumerate(webcam_list)], width=300, on_change=self.dropdown_change)
        self.start_stop_button = ft.ElevatedButton("Start", on_click=self.toggle_webcam)
        return ft.Column(controls=[self.img, dropdown, self.start_stop_button])

def main(page: ft.Page):
    page.padding = 50
    page.add(WebcamView())

if __name__ == '__main__':
    ft.app(target=main)
