import cv2
import base64
import os
import pythoncom
import math
import pyautogui
import autopy
import threading
import flet as ft
import numpy as np
import HandTrackingModule as htm
from pygrabber.dshow_graph import FilterGraph
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

wCam, hCam = 640, 480
detector = htm.handDetector(maxHands=1, detectionCon=0.85, trackCon=0.8)
devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume = cast(interface, POINTER(IAudioEndpointVolume))
minVol, maxVol = -63, volume.GetVolumeRange()[1]
tipIds = [4, 8, 12, 16, 20]
pyautogui.FAILSAFE = False


def list_webcams():
    pythoncom.CoInitialize()
    devices = FilterGraph().get_input_devices()
    pythoncom.CoUninitialize()
    return devices


class Setup(ft.UserControl):
    def __init__(self):
        super().__init__()
        self.is_running = False
        self.cap = None
        self.thread = None
        self.img_path = 'img/nocam.jpg'
        self.selected_webcam_index = None
        self.start_stop_button = None
        self.img = ft.Image(border_radius=ft.border_radius.all(20))
        self.mode = ft.Text(value='None', theme_style=ft.TextThemeStyle.TITLE_MEDIUM, size=20,
                            text_align=ft.TextAlign.LEFT, width=120)
        self.active = False
        self.prev_x, self.prev_y = 0, 0
        self.smooth_factor = 0.2
        self.theme_toggle_button = None
        self.right_click_active = False
        self.left_click_active = False

    def did_mount(self):
        self.set_default_image()
        self.update_webcam()

    def set_default_image(self):
        if os.path.exists(self.img_path):
            with open(self.img_path, 'rb') as image_file:
                self.img.src_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        self.update()

    def get_finger_state(self, lmList):
        return [
            lmList[tipIds[0]][1] > lmList[tipIds[0] - 1][1],
            *[lmList[tipIds[i]][2] < lmList[tipIds[i] - 2][2] for i in range(1, 5)]
        ]

    def adjust_volume(self, lmList):
        x1, y1, x2, y2 = *lmList[4][1:], *lmList[8][1:]
        length = math.hypot(x2 - x1, y2 - y1)
        vol = np.clip(np.interp(length, [50, 200], [minVol, maxVol]), minVol, maxVol)
        volume.SetMasterVolumeLevel(vol, None)
        cv2.line(self.frame, (x1, y1), (x2, y2), (255, 255, 255), 2)
        cv2.circle(self.frame, ((x1 + x2) // 2, (y1 + y2) // 2), 5, (0, 0, 255), cv2.FILLED)
        cv2.circle(self.frame, lmList[8][1:], 5, (0, 255, 0), cv2.FILLED)
        cv2.circle(self.frame, lmList[4][1:], 5, (0, 255, 0), cv2.FILLED)

    def move_cursor(self, lmList):
        x1, y1 = lmList[12][1:]
        w, h = autopy.screen.size()
        target_x = int(np.interp(x1, [110, 620], [w - 1, 0]))
        target_y = int(np.interp(y1, [20, 350], [0, h - 1]))
        self.prev_x = int(self.prev_x * (1 - self.smooth_factor) + target_x * self.smooth_factor)
        self.prev_y = int(self.prev_y * (1 - self.smooth_factor) + target_y * self.smooth_factor)
        autopy.mouse.move(self.prev_x, self.prev_y)
        cv2.circle(self.frame, (x1, y1), 5, (255, 255, 255), cv2.FILLED)
        if lmList[4][1] < lmList[8][1]:
            cv2.circle(self.frame, lmList[4][1:], 5, (0, 255, 0), cv2.FILLED)
            if not self.left_click_active:
                pyautogui.mouseDown(button='left')
                self.left_click_active = True
        elif self.left_click_active:
            pyautogui.mouseUp(button='left')
            self.left_click_active = False
        if lmList[8][2] > lmList[6][2]:
            cv2.circle(self.frame, lmList[8][1:], 5, (0, 255, 0), cv2.FILLED)
            if not self.right_click_active:
                pyautogui.mouseDown(button='right')
                self.right_click_active = True
        elif self.right_click_active:
            pyautogui.mouseUp(button='right')
            self.right_click_active = False

    def update_webcam(self):
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
                            'Cursor' if fingers == [1, 1, 1, 1, 1] else 'None')
                if new_mode != 'None':
                    self.mode.value, self.active = new_mode, True
                if self.mode.value == 'Scroll':
                    cv2.circle(self.frame, lmList[8][1:], 5, (0, 255, 0), cv2.FILLED)
                    if fingers == [0, 1, 0, 0, 0]:
                        pyautogui.scroll(200)
                    else:
                        pyautogui.scroll(-200)
                        cv2.circle(self.frame, lmList[12][1:], 5, (0, 255, 0), cv2.FILLED)
                elif self.mode.value == 'Volume':
                    self.adjust_volume(lmList)
                elif self.mode.value == 'Cursor':
                    self.move_cursor(lmList)
                if fingers[1:] == [0, 0, 0, 0]:
                    self.active, self.mode.value = False, 'None'
            _, im_arr = cv2.imencode('.png', self.frame)
            self.img.src_base64 = base64.b64encode(im_arr).decode('utf-8')
            self.update()

    def toggle_webcam(self, _):
        if self.is_running:
            self.is_running = False
            if self.cap:
                self.cap.release()
            self.cap, self.thread = None, None
            self.start_stop_button.text = 'Start'
            self.start_stop_button.icon = ft.Icons.PLAY_ARROW_ROUNDED
            self.set_default_image()
        else:
            if self.selected_webcam_index is None:
                return
            self.is_running = True
            self.start_stop_button.text = 'Stop'
            self.start_stop_button.icon = ft.Icons.STOP_ROUNDED
            self.cap = cv2.VideoCapture(self.selected_webcam_index)
            self.cap.set(3, wCam), self.cap.set(4, hCam)
            self.thread = threading.Thread(target=self.update_webcam)
            self.thread.start()
        self.update()

    def toggle_theme(self, _):
        if self.page.theme_mode == ft.ThemeMode.LIGHT:
            self.page.theme_mode = ft.ThemeMode.DARK
            self.theme_toggle_button.icon = ft.Icons.LIGHT_MODE_ROUNDED
        else:
            self.page.theme_mode = ft.ThemeMode.LIGHT
            self.theme_toggle_button.icon = ft.Icons.DARK_MODE_ROUNDED
        self.page.update()
        self.update()

    def build(self):
        webcam_list = list_webcams()
        dropdown = ft.Dropdown(label='Select Webcam', options=[ft.dropdown.Option(str(i), text=name) for i, name in enumerate(webcam_list)], width=300, on_change=lambda e: setattr(self, 'selected_webcam_index', int(e.control.value)))
        self.start_stop_button = ft.ElevatedButton(text='Start', on_click=self.toggle_webcam, icon=ft.Icons.PLAY_ARROW_ROUNDED, width=100, height=50, style=ft.ButtonStyle(
            alignment=ft.alignment.center_left,
            icon_size=30,
            text_style=ft.TextStyle(size=18, weight=ft.FontWeight.BOLD)
        ))
        self.theme_toggle_button = ft.IconButton(ft.Icons.DARK_MODE_ROUNDED if self.page.theme_mode == ft.ThemeMode.LIGHT else ft.Icons.LIGHT_MODE_ROUNDED, on_click=self.toggle_theme, tooltip='Toggle Theme', style=ft.ButtonStyle(alignment=ft.alignment.center_left, icon_size=30))
        main_content = ft.Column([
            ft.Container(ft.Row([self.theme_toggle_button], alignment=ft.alignment.center_left), padding=ft.padding.only(top=40)),
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
            ft.Container(ft.Text(value='   Gestures', theme_style=ft.TextThemeStyle.DISPLAY_MEDIUM), padding=ft.padding.only(bottom=25)),
            ft.Row([ft.Image(src='img/None.png', width=65, height=65), ft.Text('   None-position', size=20)]),
            ft.Row([ft.Image(src='img/Cursor.png', width=65, height=65), ft.Text('   Cursor Control', size=20)]),
            ft.Row([ft.Image(src='img/LMB.png', width=65, height=65), ft.Text('   Left Click', size=20)]),
            ft.Row([ft.Image(src='img/RMB.png', width=65, height=65), ft.Text('   Right Click', size=20)]),
            ft.Row([ft.Image(src='img/UScroll.png', width=65, height=65), ft.Text('   Scroll UP', size=20)]),
            ft.Row([ft.Image(src='img/DScroll.png', width=65, height=65), ft.Text('   Scroll DOWN', size=20)]),
            ft.Row([ft.Image(src='img/Volume.png', width=65, height=65), ft.Text('   Volume Control', size=20)]),
        ], alignment=ft.alignment.top_left, horizontal_alignment=ft.CrossAxisAlignment.START)
        gestures_section = ft.Container(content=gestures_section)
        return ft.Row([main_content, gestures_section], alignment=ft.alignment.center, spacing=100)


def main(page: ft.Page):
    page.window.width = 1200
    page.window.height = 800
    page.window.resizable = False
    page.window.alignment = ft.alignment.center
    page.window.maximized = False
    page.padding = ft.padding.only(left=50)
    if page.platform_brightness == ft.Brightness.LIGHT:
        page.theme_mode = ft.ThemeMode.LIGHT
    else:
        page.theme_mode = ft.ThemeMode.DARK
    page.add(Setup())


if __name__ == '__main__':
    ft.app(target=main)
