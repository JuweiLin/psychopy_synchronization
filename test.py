from psychopy import visual, core
import pylink
from EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy

tracker = pylink.EyeLink("100.1.1.1")
print("EyeLink connected!")

# 先用窗口模式，避免双屏 fullscreen / frame-rate detection 问题
win = visual.Window(
    size=(1280, 720),
    fullscr=False,
    screen=1,          # 第二块屏；不对就改成 0
    units="pix",
    color="black",
    waitBlanking=False
)

w, h = win.size

tracker.sendCommand(
    f"screen_pixel_coords = 0 0 {w - 1} {h - 1}"
)
tracker.sendMessage(
    f"DISPLAY_COORDS 0 0 {w - 1} {h - 1}"
)

tracker.sendCommand("calibration_type = HV9")

genv = EyeLinkCoreGraphicsPsychoPy(tracker, win)
pylink.openGraphicsEx(genv)

print("Starting EyeLink setup...")
tracker.doTrackerSetup()

tracker.close()
win.close()
core.quit()