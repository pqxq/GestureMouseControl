import cv2
import mediapipe as mp
import math

class HandDetector:
    """
    A class for hand detection using MediaPipe.
    """
    def __init__(self, mode=False, maxHands=2, detectionCon=0.5, trackCon=0.5):
        self.mode = mode
        self.maxHands = maxHands
        self.detectionCon = detectionCon
        self.trackCon = trackCon

        self.mpHands = mp.solutions.hands
        self.hands = self.mpHands.Hands(
            static_image_mode=self.mode,
            max_num_hands=self.maxHands,
            min_detection_confidence=self.detectionCon,
            min_tracking_confidence=self.trackCon
        )
        self.mpDraw = mp.solutions.drawing_utils
        self.tipIds = [4, 8, 12, 16, 20]
        self.lmList = []

    def findHands(self, img, draw=True):
        """
        Detect hands in an image.
        :param img: Input frame
        :param draw: Whether to draw hand landmarks
        :return: Processed image
        """
        imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.results = self.hands.process(imgRGB)

        if self.results.multi_hand_landmarks:
            for handLms in self.results.multi_hand_landmarks:
                if draw:
                    self.mpDraw.draw_landmarks(img, handLms, self.mpHands.HAND_CONNECTIONS)

        return img

    def findPosition(self, img, handNo=0, draw=True):
        """
        Get landmark positions of detected hand.
        :param img: Input frame
        :param handNo: Hand index (0 for first hand)
        :param draw: Whether to draw points
        :return: List of landmark positions and bounding box
        """
        self.lmList = []
        bbox = None

        if self.results.multi_hand_landmarks:
            try:
                myHand = self.results.multi_hand_landmarks[handNo]
                xList, yList = [], []

                for id, lm in enumerate(myHand.landmark):
                    h, w, _ = img.shape
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    xList.append(cx)
                    yList.append(cy)
                    self.lmList.append([id, cx, cy])

                    if draw:
                        cv2.circle(img, (cx, cy), 5, (255, 0, 255), cv2.FILLED)

                bbox = (min(xList), min(yList), max(xList), max(yList))

                if draw:
                    cv2.rectangle(img, (bbox[0] - 20, bbox[1] - 20),
                                  (bbox[2] + 20, bbox[3] + 20), (0, 255, 0), 2)
            except IndexError:
                self.lmList = []  # Ensure stability

        return self.lmList

    def fingersUp(self):
        """
        Determine which fingers are up.
        :return: List indicating finger status (1 = up, 0 = down)
        """
        if not self.lmList:
            return []

        fingers = []
        
        # Thumb (different comparison since it moves sideways)
        fingers.append(1 if self.lmList[self.tipIds[0]][1] > self.lmList[self.tipIds[0] - 1][1] else 0)

        # Other four fingers
        fingers.extend(1 if self.lmList[self.tipIds[i]][2] < self.lmList[self.tipIds[i] - 2][2] else 0 for i in range(1, 5))

        return fingers

    def findDistance(self, p1, p2, img, draw=True, r=15, t=3):
        """
        Calculate the Euclidean distance between two finger points.
        :param p1: First landmark index
        :param p2: Second landmark index
        :param img: Input frame
        :param draw: Whether to draw line/circles
        :param r: Radius of circles
        :param t: Thickness of line
        :return: Distance, processed image, midpoint coordinates
        """
        if not self.lmList:
            return 0, img, [0, 0, 0, 0, 0, 0]

        try:
            x1, y1 = self.lmList[p1][1:]
            x2, y2 = self.lmList[p2][1:]
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

            if draw:
                cv2.line(img, (x1, y1), (x2, y2), (255, 0, 255), t)
                cv2.circle(img, (x1, y1), r, (255, 0, 255), cv2.FILLED)
                cv2.circle(img, (x2, y2), r, (255, 0, 255), cv2.FILLED)
                cv2.circle(img, (cx, cy), r, (0, 0, 255), cv2.FILLED)

            length = math.hypot(x2 - x1, y2 - y1)
            return length, img, [x1, y1, x2, y2, cx, cy]

        except IndexError:
            return 0, img, [0, 0, 0, 0, 0, 0]

