import cv2
import base64
import os
import pythoncom
import math
import pyautogui
import autopy
import threading
import logging
import sys
import flet as ft
import numpy as np
import HandTrackingModule as htm
from pygrabber.dshow_graph import FilterGraph
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from typing import List, Optional, Tuple

# Ensure proper Protocol Buffers implementation
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

def resource_path(relative_path: str) -> str:
    """Get absolute path to a resource, works for both development and PyInstaller."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Constants
CAMERA_WIDTH, CAMERA_HEIGHT = 640, 480
CURSOR_X_MIN, CURSOR_X_MAX = 110, 620
CURSOR_Y_MIN, CURSOR_Y_MAX = 20, 350
VOLUME_MIN_DIST, VOLUME_MAX_DIST = 50, 200
SMOOTHING_FACTOR = 0.2

# Initialize hand detector and audio control
detector = htm.handDetector(maxHands=1, detectionCon=0.85, trackCon=0.8)
devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume = cast(interface, POINTER(IAudioEndpointVolume))
MIN_VOL, MAX_VOL = -63, volume.GetVolumeRange()[1]
TIP_IDS = [4, 8, 12, 16, 20]

pyautogui.FAILSAFE = False

def list_webcams() -> List[str]:
    """Return a list of available webcam devices."""
    pythoncom.CoInitialize()
    cams = FilterGraph().get_input_devices()
    pythoncom.CoUninitialize()
    return cams

class Setup(ft.UserControl):
    def __init__(self) -> None:
        super().__init__()
        # State variables
        self.is_running: bool = False
        self.cap: Optional[cv2.VideoCapture] = None
        self.thread: Optional[threading.Thread] = None
        self.img_path: str = resource_path('img/nocam.jpg')
        self.selected_webcam_index: Optional[int] = None
        self.prev_x: int = 0
        self.prev_y: int = 0
        self.left_click_active: bool = False
        self.right_click_active: bool = False
        self.active: bool = False

        # UI Elements
        self.start_stop_button: Optional[ft.ElevatedButton] = None
        self.theme_toggle_button: Optional[ft.IconButton] = None
        self.img = ft.Image(border_radius=ft.border_radius.all(20))
        self.mode = ft.Text(
            value='None', 
            theme_style=ft.TextThemeStyle.TITLE_MEDIUM, 
            size=20,
            text_align=ft.TextAlign.LEFT, 
            width=120
        )

    def did_mount(self) -> None:
        """Called when the control is mounted; sets the default image."""
        self.set_default_image()

    def set_default_image(self) -> None:
        """Display a default image when the webcam is not running."""
        if os.path.exists(self.img_path):
            with open(self.img_path, 'rb') as image_file:
                self.img.src_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        self.update()

    def get_finger_state(self, lmList: List[List[int]]) -> List[bool]:
        """
        Determine which fingers are up.
        Returns a list of booleans: [thumb, index, middle, ring, pinky]
        """
        thumb_up = lmList[TIP_IDS[0]][1] > lmList[TIP_IDS[0] - 1][1]
        fingers_up = [lmList[TIP_IDS[i]][2] < lmList[TIP_IDS[i] - 2][2] for i in range(1, 5)]
        return [thumb_up] + fingers_up

    def draw_marker(self, pos: Tuple[int, int], color: Tuple[int, int, int],
                    radius: int = 5, thickness: int = cv2.FILLED) -> None:
        """Draw a circular marker on the current frame."""
        cv2.circle(self.frame, pos, radius, color, thickness)

    def adjust_volume(self, lmList: List[List[int]]) -> None:
        """
        Adjust the system volume based on the distance between thumb and index finger.
        Visual markers are drawn on the frame for feedback.
        """
        x1, y1 = lmList[4][1], lmList[4][2]
        x2, y2 = lmList[8][1], lmList[8][2]
        length = math.hypot(x2 - x1, y2 - y1)
        vol = np.interp(length, [VOLUME_MIN_DIST, VOLUME_MAX_DIST], [MIN_VOL, MAX_VOL])
        vol = np.clip(vol, MIN_VOL, MAX_VOL)
        volume.SetMasterVolumeLevel(vol, None)

        # Draw markers for volume control
        cv2.line(self.frame, (x1, y1), (x2, y2), (255, 255, 255), 2)
        center = ((x1 + x2) // 2, (y1 + y2) // 2)
        self.draw_marker(center, (0, 0, 255))
        self.draw_marker((x1, y1), (0, 255, 0))
        self.draw_marker((x2, y2), (0, 255, 0))

    def move_cursor(self, lmList: List[List[int]]) -> None:
        """
        Move the cursor based on hand position and simulate mouse clicks.
        Implements a smoothing factor for smoother cursor movement.
        """
        x1, y1 = lmList[12][1], lmList[12][2]
        screen_width, screen_height = autopy.screen.size()
        # Map hand coordinates to screen coordinates (inverting x-axis mapping)
        target_x = int(np.interp(x1, [CURSOR_X_MIN, CURSOR_X_MAX], [screen_width - 1, 0]))
        target_y = int(np.interp(y1, [CURSOR_Y_MIN, CURSOR_Y_MAX], [0, screen_height - 1]))
        # Apply smoothing
        self.prev_x = int(self.prev_x * (1 - SMOOTHING_FACTOR) + target_x * SMOOTHING_FACTOR)
        self.prev_y = int(self.prev_y * (1 - SMOOTHING_FACTOR) + target_y * SMOOTHING_FACTOR)
        autopy.mouse.move(self.prev_x, self.prev_y)
        self.draw_marker((x1, y1), (255, 255, 255))

        # Simulate left click (thumb below index finger)
        if lmList[4][1] < lmList[8][1]:
            self.draw_marker((lmList[4][1], lmList[4][2]), (0, 255, 0))
            if not self.left_click_active:
                pyautogui.mouseDown(button='left')
                self.left_click_active = True
        elif self.left_click_active:
            pyautogui.mouseUp(button='left')
            self.left_click_active = False

        # Simulate right click (index finger below middle finger)
        if lmList[8][2] > lmList[6][2]:
            self.draw_marker((lmList[8][1], lmList[8][2]), (0, 255, 0))
            if not self.right_click_active:
                pyautogui.mouseDown(button='right')
                self.right_click_active = True
        elif self.right_click_active:
            pyautogui.mouseUp(button='right')
            self.right_click_active = False

    def process_gestures(self, lmList: List[List[int]]) -> None:
        """
        Process hand landmarks to determine the current gesture and trigger the corresponding action.
        Gesture modes include:
          - 'Scroll' for vertical scrolling.
          - 'Volume' for adjusting system volume.
          - 'Cursor' for mouse movement and clicks.
          - 'None' for no active gesture.
        """
        fingers = self.get_finger_state(lmList)
        if fingers in ([False, True, False, False, False], [False, True, True, False, False]):
            gesture_mode = 'Scroll'
        elif fingers == [True, True, False, False, False]:
            gesture_mode = 'Volume'
        elif fingers == [True, True, True, True, True]:
            gesture_mode = 'Cursor'
        else:
            gesture_mode = 'None'

        if gesture_mode != 'None':
            self.mode.value = gesture_mode
            self.active = True

        if self.mode.value == 'Scroll':
            self.draw_marker((lmList[8][1], lmList[8][2]), (0, 255, 0))
            if fingers == [False, True, False, False, False]:
                pyautogui.scroll(200)
            else:
                pyautogui.scroll(-200)
                self.draw_marker((lmList[12][1], lmList[12][2]), (0, 255, 0))
        elif self.mode.value == 'Volume':
            self.adjust_volume(lmList)
        elif self.mode.value == 'Cursor':
            self.move_cursor(lmList)

        # Reset mode if only the thumb is up
        if fingers[1:] == [False, False, False, False]:
            self.active = False
            self.mode.value = 'None'

    def update_webcam(self) -> None:
        """Continuously capture frames from the webcam, process them, and update the UI."""
        try:
            while self.is_running:
                success, self.frame = self.cap.read()
                if not success:
                    continue

                # Hand tracking and gesture processing
                self.frame = detector.findHands(self.frame)
                lmList = detector.findPosition(self.frame, draw=False)
                if lmList:
                    self.process_gestures(lmList)

                # Update UI with the processed frame
                ret, im_arr = cv2.imencode('.png', self.frame)
                if ret:
                    self.img.src_base64 = base64.b64encode(im_arr).decode('utf-8')
                    self.update()
        except Exception as e:
            logging.error(f"Error in webcam thread: {e}")
        finally:
            if self.cap is not None:
                self.cap.release()

    def start_camera(self) -> None:
        """Start webcam capture and processing in a separate thread."""
        if self.selected_webcam_index is None:
            logging.warning("Webcam not selected.")
            return
        self.is_running = True
        self.start_stop_button.text = 'Stop'
        self.start_stop_button.icon = ft.Icons.STOP_ROUNDED
        self.cap = cv2.VideoCapture(self.selected_webcam_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self.thread = threading.Thread(target=self.update_webcam, daemon=True)
        self.thread.start()
        self.update()

    def stop_camera(self) -> None:
        """Stop the webcam capture and clean up the thread."""
        self.is_running = False
        if self.cap is not None:
            self.cap.release()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        self.cap, self.thread = None, None
        self.start_stop_button.text = 'Start'
        self.start_stop_button.icon = ft.Icons.PLAY_ARROW_ROUNDED
        self.set_default_image()

    def toggle_webcam(self, _e) -> None:
        """Toggle the webcam between start and stop states."""
        if self.is_running:
            self.stop_camera()
        else:
            self.start_camera()

    def toggle_theme(self, _e) -> None:
        """Switch between light and dark UI themes."""
        if self.page.theme_mode == ft.ThemeMode.LIGHT:
            self.page.theme_mode = ft.ThemeMode.DARK
            self.theme_toggle_button.icon = ft.Icons.LIGHT_MODE_ROUNDED
        else:
            self.page.theme_mode = ft.ThemeMode.LIGHT
            self.theme_toggle_button.icon = ft.Icons.DARK_MODE_ROUNDED
        self.page.update()
        self.update()

    def build(self) -> ft.Row:
        """Construct the UI layout."""
        webcam_list = list_webcams()
        dropdown = ft.Dropdown(
            label='Select Webcam',
            options=[ft.dropdown.Option(str(i), text=name) for i, name in enumerate(webcam_list)],
            width=300,
            on_change=lambda e: setattr(self, 'selected_webcam_index', int(e.control.value))
        )
        self.start_stop_button = ft.ElevatedButton(
            text='Start',
            on_click=self.toggle_webcam,
            icon=ft.Icons.PLAY_ARROW_ROUNDED,
            width=100,
            height=50,
            style=ft.ButtonStyle(
                alignment=ft.alignment.center_left,
                icon_size=30,
                text_style=ft.TextStyle(size=18, weight=ft.FontWeight.BOLD)
            )
        )
        self.theme_toggle_button = ft.IconButton(
            ft.Icons.DARK_MODE_ROUNDED if self.page.theme_mode == ft.ThemeMode.LIGHT else ft.Icons.LIGHT_MODE_ROUNDED,
            on_click=self.toggle_theme,
            tooltip='Toggle Theme',
            style=ft.ButtonStyle(alignment=ft.alignment.center_left, icon_size=30)
        )
        main_content = ft.Column([
            ft.Container(ft.Row([self.theme_toggle_button], alignment=ft.alignment.center_left),
                         padding=ft.padding.only(top=40)),
            ft.Column([
                self.img,
                ft.Container(dropdown, padding=ft.padding.only(top=20)),
                ft.Container(ft.Row([
                    self.start_stop_button,
                    ft.Container(content=self.mode, padding=ft.padding.only(left=40))
                ]), padding=ft.padding.only(left=40))
            ], alignment=ft.alignment.center, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        ])
        gestures_section = ft.Column([
            ft.Container(ft.Text(value='   Gestures', theme_style=ft.TextThemeStyle.DISPLAY_MEDIUM),
                         padding=ft.padding.only(bottom=25)),
            ft.Row([ft.Image(src=resource_path('img/None.png'), width=65, height=65),
                    ft.Text('   None-position', size=20)]),
            ft.Row([ft.Image(src=resource_path('img/Cursor.png'), width=65, height=65),
                    ft.Text('   Cursor Control', size=20)]),
            ft.Row([ft.Image(src=resource_path('img/LMB.png'), width=65, height=65),
                    ft.Text('   Left Click', size=20)]),
            ft.Row([ft.Image(src=resource_path('img/RMB.png'), width=65, height=65),
                    ft.Text('   Right Click', size=20)]),
            ft.Row([ft.Image(src=resource_path('img/UScroll.png'), width=65, height=65),
                    ft.Text('   Scroll UP', size=20)]),
            ft.Row([ft.Image(src=resource_path('img/DScroll.png'), width=65, height=65),
                    ft.Text('   Scroll DOWN', size=20)]),
            ft.Row([ft.Image(src=resource_path('img/Volume.png'), width=65, height=65),
                    ft.Text('   Volume Control', size=20)]),
        ], alignment=ft.alignment.top_left, horizontal_alignment=ft.CrossAxisAlignment.START)
        gestures_section = ft.Container(content=gestures_section)
        return ft.Row([main_content, gestures_section], alignment=ft.alignment.center, spacing=100)

def main(page: ft.Page) -> None:
    """Initialize the Flet page with settings and add the Setup control."""
    page.title = 'Gesture Control'
    page.window.width = 1200
    page.window.height = 800
    page.window.resizable = False
    page.window.alignment = ft.alignment.center
    page.window.maximized = False
    page.padding = ft.padding.only(left=80)
    page.theme_mode = ft.ThemeMode.LIGHT if page.platform_brightness == ft.Brightness.LIGHT else ft.ThemeMode.DARK
    page.add(Setup())

if __name__ == '__main__':
    ft.app(target=main)
