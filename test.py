from psychopy import visual, core
import pylink
from EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy


# ============================================================
# Configuration
# ============================================================

EYELINK_IP = "100.1.1.1"

SCREEN_INDEX = 0
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

REFRESH_RATE = 60.0


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
print("Window size:", w, h)


# ============================================================
# 3. Force / bypass frame-rate measurement
# ============================================================

print(f"Forcing frame rate to {REFRESH_RATE} Hz")

# Prevent PsychoPy / EyeLink graphics from trying to measure
# the real frame rate and hanging on dual-screen systems.
win.getActualFrameRate = lambda *args, **kwargs: REFRESH_RATE

# Some PsychoPy code may inspect this value directly
win.monitorFramePeriod = 1.0 / REFRESH_RATE


# ============================================================
# 4. PsychoPy display test
# ============================================================

print("Displaying white test dot for 5 seconds...")

test_dot = visual.Circle(
    win=win,
    radius=30,
    pos=(0, 0),
    fillColor="white",
    lineColor="white"
)

test_dot.draw()
win.flip()

core.wait(5)

# Clear display
win.flip()

print("Display test finished.")


# ============================================================
# 5. Configure EyeLink display coordinates
# ============================================================

el.sendCommand(
    f"screen_pixel_coords = 0 0 {w - 1} {h - 1}"
)

el.sendMessage(
    f"DISPLAY_COORDS 0 0 {w - 1} {h - 1}"
)

# 9-point calibration
el.sendCommand("calibration_type = HV9")


# ============================================================
# 6. EyeLink PsychoPy graphics
# ============================================================

print("Creating EyeLink PsychoPy graphics...")

genv = EyeLinkCoreGraphicsPsychoPy(
    el,
    win
)

# Calibration target/background colors
genv.setCalibrationColors(
    (1, 1, 1),      # white target
    (-1, -1, -1)    # black background
)

# Calibration target shape
genv.setTargetType("circle")
genv.setTargetSize(24)

# Register PsychoPy graphics with pylink
pylink.openGraphicsEx(genv)

print("EyeLink graphics initialized.")


# ============================================================
# 7. Prepare tracker
# ============================================================

el.setOfflineMode()

print("")
print("========================================")
print("EyeLink connected")
print("PsychoPy display initialized")
print(f"Frame rate forced to {REFRESH_RATE} Hz")
print("Starting calibration directly...")
print("========================================")
print("")


# ============================================================
# 8. Start calibration directly
# ============================================================

# 1 = enter calibration directly
# instead of stopping at Camera Setup first

el.doTrackerSetup(1)


# ============================================================
# 9. Calibration finished
# ============================================================

print("Calibration/setup returned successfully.")


# ============================================================
# 10. Cleanup
# ============================================================

el.setOfflineMode()
el.close()

win.close()

print("EyeLink disconnected.")
print("Test complete.")

core.quit()