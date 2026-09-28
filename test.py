from psychopy import visual, core
import pylink
from EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy

# 1. Connect to EyeLink
tracker = pylink.EyeLink("100.1.1.1")
print("Connected.")

# 2. Create PsychoPy window
win = visual.Window(
    size=(1280, 720),
    screen=1,              # 第二块屏幕；不对就改 0
    fullscr=False,         # 测试阶段先不要 fullscreen
    units="pix",
    color="black",
    waitBlanking=False
)

print("Window created.")

# 3. IMPORTANT: bypass actual frame-rate measurement
win.getActualFrameRate = lambda *args, **kwargs: 60.0

# 4. Tell EyeLink the display size
w, h = win.size

tracker.sendCommand(
    f"screen_pixel_coords = 0 0 {w - 1} {h - 1}"
)
tracker.sendMessage(
    f"DISPLAY_COORDS 0 0 {w - 1} {h - 1}"
)

tracker.sendCommand("calibration_type = HV9")

# 5. EyeLink PsychoPy graphics
print("Creating EyeLink graphics...")
genv = EyeLinkCoreGraphicsPsychoPy(tracker, win)

pylink.openGraphicsEx(genv)

# 6. Calibration
print("Setting up...")
tracker.doTrackerSetup()

print("Calibration finished.")

# 7. Cleanup
tracker.close()
win.close()
core.quit()