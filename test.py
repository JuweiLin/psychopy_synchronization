from psychopy import visual, core
import pylink

# -------------------------
# 1. Connect to EyeLink
# -------------------------
# EyeLink Host PC default IP
tracker = pylink.EyeLink("100.1.1.1")

print("Connected to EyeLink!")

# -------------------------
# 2. Create PsychoPy window
# -------------------------
win = visual.Window(
    size=(1920, 1080),
    fullscr=True,
    units="pix",
    color="black"
)

width, height = win.size

# Tell EyeLink the display resolution
tracker.sendCommand(
    f"screen_pixel_coords = 0 0 {width - 1} {height - 1}"
)

tracker.sendMessage(
    f"DISPLAY_COORDS 0 0 {width - 1} {height - 1}"
)

# -------------------------
# 3. Calibration settings
# -------------------------
tracker.sendCommand("calibration_type = HV9")

# -------------------------
# 4. Start EyeLink setup
# -------------------------
# This enters Camera Setup + Calibration
tracker.doTrackerSetup()

# -------------------------
# 5. Done
# -------------------------
print("Calibration completed!")

tracker.close()
win.close()
core.quit()