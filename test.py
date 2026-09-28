from psychopy import visual, core
import pylink
import threading
import time

from EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy


# ============================================================
# Configuration
# ============================================================

EYELINK_IP = "100.1.1.1"

SCREEN_INDEX = 0

SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

REFRESH_RATE = 60.0

# Delay before automatically sending "C" to EyeLink Host.
# Gives doTrackerSetup() enough time to enter setup mode.
AUTO_CAL_DELAY = 2.0


# ============================================================
# 1. Connect to EyeLink
# ============================================================

print("Connecting to EyeLink...")

el = pylink.EyeLink(EYELINK_IP)

print("Connected:", el.isConnected())
print("Tracker version:", el.getTrackerVersion())


# ============================================================
# 2. Create PsychoPy window
# ============================================================

print("Creating PsychoPy window...")

win = visual.Window(
    size=(SCREEN_WIDTH, SCREEN_HEIGHT),
    screen=SCREEN_INDEX,
    fullscr=True,
    units="pix",
    color="black",
    waitBlanking=True
)

w, h = win.size

print("Window created.")
print("Actual PsychoPy window size:", w, h)


# ============================================================
# 3. Bypass PsychoPy frame-rate measurement
# ============================================================

print(f"Forcing refresh rate to {REFRESH_RATE} Hz")

win.getActualFrameRate = lambda *args, **kwargs: REFRESH_RATE
win.monitorFramePeriod = 1.0 / REFRESH_RATE


# ============================================================
# 4. Quick display test
# ============================================================

# Small donut-style target, just to verify PsychoPy can draw.

outer = visual.Circle(
    win=win,
    radius=12,
    pos=(0, 0),
    fillColor="white",
    lineColor="white"
)

inner = visual.Circle(
    win=win,
    radius=4,
    pos=(0, 0),
    fillColor="black",
    lineColor="black"
)

outer.draw()
inner.draw()

win.flip()

print("Showing PsychoPy test target for 2 seconds...")
core.wait(2)

win.flip()


# ============================================================
# 5. Tell EyeLink about display coordinates
# ============================================================

el.sendCommand(
    f"screen_pixel_coords = 0 0 {w - 1} {h - 1}"
)

el.sendMessage(
    f"DISPLAY_COORDS 0 0 {w - 1} {h - 1}"
)


# ============================================================
# 6. Calibration configuration
# ============================================================

# Nine-point calibration
el.sendCommand("calibration_type = HV9")

# Automatically accept fixation and advance between calibration points
el.sendCommand("enable_automatic_calibration = YES")

# Minimum delay before accepting each point.
# 1000 ms is SR Research's typical suggested starting point.
el.sendCommand("automatic_calibration_pacing = 1000")

print("Calibration type: HV9")
print("Automatic calibration: enabled")
print("Automatic pacing: 1000 ms")


# ============================================================
# 7. Setup EyeLink PsychoPy graphics
# ============================================================

print("Creating EyeLink PsychoPy graphics...")

genv = EyeLinkCoreGraphicsPsychoPy(
    el,
    win
)

# Don't manually force giant circle target.
# Leave EyeLinkCoreGraphicsPsychoPy target appearance at defaults.

genv.setCalibrationColors(
    (1, 1, 1),      # white foreground
    (-1, -1, -1)    # black background
)

pylink.openGraphicsEx(genv)

print("EyeLink graphics initialized.")


# ============================================================
# 8. Function to automatically press C on the EyeLink Host
# ============================================================

def start_calibration_automatically():
    time.sleep(AUTO_CAL_DELAY)

    print("Sending C to EyeLink Host...")

    # ASCII code for lowercase 'c' = 99
    el.sendKeybutton(
        ord("c"),
        0,
        pylink.KB_PRESS
    )

    # Send release as well
    time.sleep(0.05)

    try:
        el.sendKeybutton(
            ord("c"),
            0,
            pylink.KB_RELEASE
        )
    except Exception:
        # Some versions do not require/handle release separately.
        pass


# ============================================================
# 9. Enter setup and automatically start calibration
# ============================================================

el.setOfflineMode()

print("")
print("==========================================")
print("Entering EyeLink setup...")
print("Calibration will start automatically.")
print("You should NOT need to press C.")
print("==========================================")
print("")

# Start timer/thread BEFORE doTrackerSetup(),
# because doTrackerSetup() blocks until setup is completed.
auto_cal_thread = threading.Thread(
    target=start_calibration_automatically,
    daemon=True
)

auto_cal_thread.start()

# This opens EyeLink setup and handles calibration graphics.
el.doTrackerSetup()


# ============================================================
# 10. Setup/calibration finished
# ============================================================

print("")
print("EyeLink setup returned.")
print("Calibration finished or setup was exited.")


# ============================================================
# 11. Cleanup
# ============================================================

el.setOfflineMode()

el.close()

win.close()

print("EyeLink disconnected.")
print("Test complete.")

core.quit()