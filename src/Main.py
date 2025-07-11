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
import HandTrackingModule as Htm
from pygrabber.dshow_graph import FilterGraph
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from typing import List, Optional, Tuple
from collections import deque

os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CAMERA_WIDTH, CAMERA_HEIGHT = 640, 480
CURSOR_X_MIN, CURSOR_X_MAX = 110, 620
CURSOR_Y_MIN, CURSOR_Y_MAX = 20, 350
VOLUME_MIN_DIST, VOLUME_MAX_DIST = 50, 200
SMOOTHING_FACTOR = 0.2

detector = Htm.handDetector(maxHands=1, detectionCon=0.85, trackCon=0.8)
devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume = interface.QueryInterface(IAudioEndpointVolume)
volume.GetMasterVolumeLevel()
volRange = volume.GetVolumeRange()
volume.SetMasterVolumeLevel(0, None)
MIN_VOL, MAX_VOL = volRange[0], volRange[1]
TIP_IDS = [4, 8, 12, 16, 20]

pyautogui.FAILSAFE = False

def resource_path(relative_path: str) -> str:
    """Get absolute path to a resource, works for both development and PyInstaller."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def list_webcams() -> List[str]:
    """Return a list of available webcam devices."""
    pythoncom.CoInitialize()
    cams = FilterGraph().get_input_devices()
    pythoncom.CoUninitialize()
    return cams

def get_finger_state(lm_list: List[List[int]]) -> List[bool]:
    thumb_up = lm_list[TIP_IDS[0]][1] > lm_list[TIP_IDS[0] - 1][1]
    fingers_up = [lm_list[TIP_IDS[i]][2] < lm_list[TIP_IDS[i] - 2][2] for i in range(1, 5)]
    return [thumb_up] + fingers_up


class Setup(ft.UserControl):
    def __init__(self) -> None:
        super().__init__()
        self.frame = None
        self.is_running: bool = False
        self.cap: Optional[cv2.VideoCapture] = None
        self.thread: Optional[threading.Thread] = None
        self.img_path: str = resource_path('img/no-cam.jpg')
        self.selected_webcam_index: Optional[int] = None
        self.prev_x: int = 0
        self.prev_y: int = 0
        self.left_click_active: bool = False
        self.right_click_active: bool = False
        self.active: bool = False
        self.no_hand_counter: int = 0
        self.gesture_buffer = deque(maxlen=5)
        self.gesture_threshold = 4
        self.current_mode = 'None'
        self.lm_buffer = deque(maxlen=5)
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

    def draw_marker(self, pos: Tuple[int, int], color: Tuple[int, int, int], radius: int = 5, thickness: int = cv2.FILLED) -> None:
        if self.frame is not None and isinstance(self.frame, np.ndarray):
            cv2.circle(self.frame, pos, radius, color, thickness)

    def adjust_volume(self, lm_list: List[List[int]]) -> None:
        x1, y1 = lm_list[4][1], lm_list[4][2]
        x2, y2 = lm_list[8][1], lm_list[8][2]
        length = math.hypot(x2 - x1, y2 - y1)
        vol = np.interp(length, [VOLUME_MIN_DIST, VOLUME_MAX_DIST], [MIN_VOL, MAX_VOL])
        vol = np.clip(vol, MIN_VOL, MAX_VOL)
        volume.SetMasterVolumeLevel(vol, None)

        if isinstance(self.frame, np.ndarray):
            cv2.line(self.frame, (x1, y1), (x2, y2), (255, 255, 255), 2)
        center = ((x1 + x2) // 2, (y1 + y2) // 2)
        self.draw_marker(center, (0, 0, 255))
        self.draw_marker((x1, y1), (0, 255, 0))
        self.draw_marker((x2, y2), (0, 255, 0))

    def move_cursor(self, lm_list: List[List[int]]) -> None:
        x1, y1 = lm_list[12][1], lm_list[12][2]
        screen_width, screen_height = autopy.screen.size()
        target_x = int(np.interp(x1, [CURSOR_X_MIN, CURSOR_X_MAX], [screen_width - 1, 0]))
        target_y = int(np.interp(y1, [CURSOR_Y_MIN, CURSOR_Y_MAX], [0, screen_height - 1]))
        self.prev_x = int(self.prev_x * (1 - SMOOTHING_FACTOR) + target_x * SMOOTHING_FACTOR)
        self.prev_y = int(self.prev_y * (1 - SMOOTHING_FACTOR) + target_y * SMOOTHING_FACTOR)
        autopy.mouse.move(self.prev_x, self.prev_y)
        self.draw_marker((x1, y1), (255, 255, 255))
        if lm_list[4][1] < lm_list[8][1]:
            self.draw_marker((lm_list[4][1], lm_list[4][2]), (0, 255, 0))
            if not self.left_click_active:
                pyautogui.mouseDown(button='left')
                self.left_click_active = True
        elif self.left_click_active:
            pyautogui.mouseUp(button='left')
            self.left_click_active = False
        if lm_list[8][2] > lm_list[6][2]:
            self.draw_marker((lm_list[8][1], lm_list[8][2]), (0, 255, 0))
            if not self.right_click_active:
                pyautogui.mouseDown(button='right')
                self.right_click_active = True
        elif self.right_click_active:
            pyautogui.mouseUp(button='right')
            self.right_click_active = False

    @staticmethod
    def _classify_gesture(lm_list: List[List[int]]) -> str:
        fingers = get_finger_state(lm_list)
        if fingers == [False, True, False, False, False]:
            return 'Scroll ↑'
        elif fingers == [False, True, True, False, False]:
            return 'Scroll ↓'
        elif fingers == [True, True, False, False, False]:
            return 'Volume'
        elif fingers in ([True, True, True, True, True], [False, True, True, True, True], [True, False, True, True, True]):
            return 'Cursor'
        return 'None'


    def process_gestures(self, lm_list: List[List[int]]) -> None:
        raw = self._classify_gesture(lm_list)
        self.gesture_buffer.append(raw)

        stable = 'None'
        for gesture in ['Cursor', 'Volume', 'Scroll ↓', 'Scroll ↑']:
            if self.gesture_buffer.count(gesture) >= self.gesture_threshold:
                stable = gesture
                break

        if stable != self.current_mode:
            self.current_mode = stable
            self.mode.value = stable
            self.update()

        if self.current_mode == 'Cursor':
            self.move_cursor(lm_list)
        elif self.current_mode == 'Volume':
            self.adjust_volume(lm_list)
        elif self.current_mode == 'Scroll ↓':
            pyautogui.scroll(-200)
            self.draw_marker((lm_list[8][1], lm_list[8][2]), (0, 255, 0))
            self.draw_marker((lm_list[12][1], lm_list[12][2]), (0, 255, 0))
        elif self.current_mode == 'Scroll ↑':
            pyautogui.scroll(200)
            self.draw_marker((lm_list[8][1], lm_list[8][2]), (0, 255, 0))

    def update_webcam(self) -> None:
        try:
            while self.is_running:
                if self.cap is None:
                    continue
                success, self.frame = self.cap.read()
                if not success:
                    continue

                self.frame = detector.findHands(self.frame)
                lm_list = detector.findPosition(self.frame, draw=False)
                if lm_list:
                    self.lm_buffer.append(lm_list)
                    smooth = []
                    for idx in range(len(lm_list)):
                        xs = [frm[idx][1] for frm in self.lm_buffer]
                        ys = [frm[idx][2] for frm in self.lm_buffer]
                        smooth.append([lm_list[idx][0], int(sum(xs)/len(xs)), int(sum(ys)/len(ys))])
                    self.process_gestures(smooth)
                    self.no_hand_counter = 0
                else:
                    self.no_hand_counter += 1
                    if self.no_hand_counter >= 30:
                        self.current_mode = 'None'
                        self.mode.value = 'None'
                        self.active = False
                        self.left_click_active = False
                        self.right_click_active = False
                        self.no_hand_counter = 0

                ret, im_arr = cv2.imencode('.png', self.frame)
                if ret:
                    self.img.src_base64 = base64.b64encode(im_arr.tobytes()).decode('utf-8')
                    self.update()
        except Exception as e:
            logging.error(f"Error in webcam thread: {e}")
        finally:
            if self.cap is not None:
                self.cap.release()

    def start_camera(self) -> None:
        self.mode.value = 'Starting'
        self.is_running = True
        if self.start_stop_button is not None:
            self.start_stop_button.text = 'Stop'
            self.start_stop_button.icon = ft.Icons.STOP_ROUNDED
        self.update()
        cam_index = self.selected_webcam_index if self.selected_webcam_index is not None else 0
        self.cap = cv2.VideoCapture(cam_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self.thread = threading.Thread(target=self.update_webcam, daemon=True)
        self.thread.start()

    def stop_camera(self) -> None:
        self.is_running = False
        self.mode.value = 'None'
        if self.cap is not None:
            self.cap.release()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        self.cap, self.thread = None, None
        if self.start_stop_button is not None:
            self.start_stop_button.text = 'Start'
            self.start_stop_button.icon = ft.Icons.PLAY_ARROW_ROUNDED
        self.set_default_image()

    def toggle_webcam(self, _e) -> None:
        if self.is_running:
            self.stop_camera()
        else:
            if self.selected_webcam_index is None:
                logging.warning("Webcam not selected.")
                return
            self.start_camera()

    def toggle_theme(self, _e) -> None:
        if not hasattr(self, "page") or self.page is None:
            logging.warning("Page is not set. Cannot toggle theme.")
            return
        if self.page.theme_mode == ft.ThemeMode.LIGHT:
            self.page.theme_mode = ft.ThemeMode.DARK
            if self.theme_toggle_button is not None:
                self.theme_toggle_button.icon = ft.Icons.LIGHT_MODE_ROUNDED
        else:
            self.page.theme_mode = ft.ThemeMode.LIGHT
            if self.theme_toggle_button is not None:
                self.theme_toggle_button.icon = ft.Icons.DARK_MODE_ROUNDED
        self.page.update()
        self.update()

    def build(self) -> None:
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
        theme_icon = ft.Icons.DARK_MODE_ROUNDED
        if hasattr(self, "page") and self.page is not None:
            if self.page.theme_mode == ft.ThemeMode.LIGHT:
                theme_icon = ft.Icons.DARK_MODE_ROUNDED
            else:
                theme_icon = ft.Icons.LIGHT_MODE_ROUNDED
        self.theme_toggle_button = ft.IconButton(
            theme_icon,
            on_click=self.toggle_theme,
            tooltip='Toggle Theme',
            style=ft.ButtonStyle(alignment=ft.alignment.center_left, icon_size=30)
        )
        main_content = ft.Column([
            ft.Row([self.theme_toggle_button]),
            ft.Column([
                self.img,
                ft.Divider(),
                dropdown,
                ft.Container(
                    ft.Row([
                        self.start_stop_button,
                        self.mode
                    ], spacing=40, expand=True), padding=ft.padding.only(left=40))
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        ])


        gestures_section = ft.Column([
            ft.Container(ft.Text(value='   Gestures', theme_style=ft.TextThemeStyle.DISPLAY_MEDIUM)),
            ft.Divider(),
            ft.Row([ft.Image(src=resource_path('img/None.png'), width=65, height=65),
                    ft.Text('   None-position', size=20)]),
            ft.Row([ft.Image(src=resource_path('img/Cursor.png'), width=65, height=65),
                    ft.Text('   Cursor Control', size=20)]),
            ft.Row([ft.Image(src=resource_path('img/LMB.png'), width=65, height=65),
                    ft.Text('   Left Click', size=20)]),
            ft.Row([ft.Image(src=resource_path('img/RMB.png'), width=65, height=65),
                    ft.Text('   Right Click', size=20)]),
            ft.Row([ft.Image(src=resource_path('img/UScroll.png'), width=65, height=65),
                    ft.Text('   Scroll ↑', size=20)]),
            ft.Row([ft.Image(src=resource_path('img/DScroll.png'), width=65, height=65),
                    ft.Text('   Scroll ↓', size=20)]),
            ft.Row([ft.Image(src=resource_path('img/Volume.png'), width=65, height=65),
                    ft.Text('   Volume Control', size=20)]),
        ])

        self.controls.append(
            ft.Row([main_content, gestures_section], spacing=100, alignment=ft.MainAxisAlignment.SPACE_EVENLY)
        )

def main(page: ft.Page) -> None:
    page.title = 'Gesture Control'
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window.width = 1200
    page.window.height = 800
    page.window.resizable = False
    page.window.alignment = ft.alignment.center
    page.window.maximized = False
    page.theme_mode = ft.ThemeMode.LIGHT if page.platform_brightness == ft.Brightness.LIGHT else ft.ThemeMode.DARK
    page.add(Setup())

if __name__ == '__main__':
    ft.app(target=main)
