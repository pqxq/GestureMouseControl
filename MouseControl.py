import cv2
import numpy as np
import HandTrackingModule as htm
import time
import autopy

# Constants
CAM_WIDTH, CAM_HEIGHT = 640, 480
FRAME_MARGIN = 100  # Reduce active frame area
SMOOTHENING = 5  # Adjust for smoother mouse movement

# Initialize variables
prev_time = 0
prev_x, prev_y = 0, 0
curr_x, curr_y = 0, 0

# Camera setup
cap = cv2.VideoCapture(0)
cap.set(3, CAM_WIDTH)
cap.set(4, CAM_HEIGHT)

# Initialize hand detector
detector = htm.HandDetector(maxHands=1)

# Get screen size
screen_width, screen_height = autopy.screen.size()

def main():
    global prev_x, prev_y, prev_time  # To update across frames

    while True:
        # 1. Capture frame & detect hands
        success, img = cap.read()
        if not success:
            print("Failed to capture frame")
            continue

        img = detector.findHands(img)
        landmarks = detector.findPosition(img)

        # 2. Process detected hand
        if landmarks:
            process_hand(img, landmarks)

        # 3. Calculate & display FPS
        display_fps(img)

        # 4. Show frame
        cv2.imshow("Virtual Mouse", img)
        cv2.waitKey(1)

def process_hand(img, landmarks):
    """Handles hand processing, movement & clicking."""
    global prev_x, prev_y

    # Get index finger positions
    x, y = landmarks[8][1:]  # Index finger tip

    # Get which fingers are up
    fingers = detector.fingersUp()

    # Draw frame boundary
    cv2.rectangle(img, (FRAME_MARGIN, FRAME_MARGIN), (CAM_WIDTH - FRAME_MARGIN, CAM_HEIGHT - FRAME_MARGIN), (255, 0, 255), 2)

    # Move mode: Only index finger up
    if fingers[1] and not fingers[2]:
        move_mouse(x, y)

    # Click mode: Both index & middle fingers up
    if fingers[1] and fingers[2]:
        click_mouse(img)

def move_mouse(x, y):
    """Moves the mouse pointer based on hand movement."""
    global prev_x, prev_y

    # Convert coordinates to screen space
    mapped_x = np.interp(x, (FRAME_MARGIN, CAM_WIDTH - FRAME_MARGIN), (0, screen_width))
    mapped_y = np.interp(y, (FRAME_MARGIN, CAM_HEIGHT - FRAME_MARGIN), (0, screen_height))

    # Smooth the movement
    curr_x = prev_x + (mapped_x - prev_x) / SMOOTHENING
    curr_y = prev_y + (mapped_y - prev_y) / SMOOTHENING

    # Move the mouse
    autopy.mouse.move(screen_width - curr_x, curr_y)

    # Update previous positions
    prev_x, prev_y = curr_x, curr_y

def click_mouse(img):
    """Handles clicking action when index and middle fingers are close."""
    length, img, line_info = detector.findDistance(8, 12, img)

    if length < 40:
        cv2.circle(img, (line_info[4], line_info[5]), 15, (0, 255, 0), cv2.FILLED)
        autopy.mouse.click()

def display_fps(img):
    """Calculates and displays FPS."""
    global prev_time
    curr_time = time.time()
    fps = 1 / (curr_time - prev_time)
    prev_time = curr_time

    cv2.putText(img, f'FPS: {int(fps)}', (20, 50), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)

if __name__ == "__main__":
    main()
