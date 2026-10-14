"""Scrollable long-text preview used only by the audio diagnostic."""

import math


class ScrollableDebugText:
    def __init__(self, view, text):
        from psychopy import event

        self.view = view
        self.offset = 0
        self.wheel_remainder = 0.0
        self.dragging = False
        self.mouse = event.Mouse(win=view.win, visible=True)
        scale = view.text_scale
        wrap_width = max(view.win.size[0] * 2, len(text) * view.config.text_height_px * 2)
        options = dict(units="pix", font=view.config.font, color="white",
                       height=view.config.text_height_px / scale, wrapWidth=wrap_width / scale,
                       alignText="left", anchorHoriz="left", anchorVert="top", autoLog=False)
        probe = view.visual.TextStim(view.win, text="Ag", **options)
        glyph_height = float(probe.boundingBox[1]) * scale
        self.line_height = max(view.config.text_height_px, glyph_height) + max(6, math.ceil(glyph_height * 0.25))
        self.visible_count = max(1, int(view.text_height // self.line_height))

        def width(value):
            probe.text = value
            measured = float(probe.boundingBox[0]) * scale
            if not math.isfinite(measured) or measured < 0:
                raise ValueError("The font returned invalid debug text dimensions")
            return measured

        self.lines = []
        for paragraph in text.splitlines():
            current = ""
            for word in paragraph.split():
                candidate = current + " " + word if current else word
                if width(candidate) <= view.text_width:
                    current = candidate
                    continue
                if current:
                    self.lines.append(current)
                    current = ""
                # Long tokens (for example URLs) wrap in the preview too.
                # The original text sent to TTS is never changed.
                while width(word) > view.text_width:
                    low, high = 1, len(word)
                    while low < high:
                        middle = (low + high + 1) // 2
                        if width(word[:middle]) <= view.text_width:
                            low = middle
                        else:
                            high = middle - 1
                    self.lines.append(word[:low])
                    word = word[low:]
                current = word
            self.lines.append(current)
        self.lines = self.lines or [""]
        self.max_offset = max(0, len(self.lines) - self.visible_count)
        self.labels = [view.visual.TextStim(view.win, text="", **options) for _ in range(self.visible_count)]
        self.footer = view.visual.TextStim(view.win, text="", units="pix", height=16 / scale,
            pos=(0, -view.win.size[1] * 0.44 / scale), wrapWidth=view.win.size[0] * 0.95 / scale,
            color="white", autoLog=False)
        self.track = view.visual.Rect(view.win, units="pix", width=14, height=view.text_height,
            pos=(view.text_width / 2 + 20, 0), fillColor="#404040", lineColor="#404040", autoLog=False)
        thumb_height = max(20, view.text_height * min(1, self.visible_count / len(self.lines)))
        self.thumb = view.visual.Rect(view.win, units="pix", width=10, height=thumb_height,
            fillColor="#C0C0C0", lineColor="#C0C0C0", autoLog=False)

    def reset_scroll(self):
        self.offset = 0
        self.wheel_remainder = 0.0
        self.mouse.getWheelRel()

    def draw(self):
        self.wheel_remainder += float(self.mouse.getWheelRel()[1]) * 3
        steps = math.trunc(self.wheel_remainder)
        self.wheel_remainder -= steps
        self.offset -= steps
        keys = self.view.keyboard.getKeys(keyList=["up", "down", "pageup", "pagedown", "home", "end"],
                                          waitRelease=False, clear=True)
        for key in keys:
            if key.name == "home":
                self.offset = 0
            elif key.name == "end":
                self.offset = self.max_offset
            else:
                self.offset += {"up": -1, "down": 1, "pageup": -self.visible_count,
                                "pagedown": self.visible_count}[key.name]
        if self.max_offset:
            if not self.mouse.getPressed()[0]:
                self.dragging = False
            elif self.dragging or self.mouse.isPressedIn(self.track, buttons=[0]):
                self.dragging = True
                travel = self.view.text_height - self.thumb.height
                fraction = (self.view.text_height / 2 - self.thumb.height / 2 - self.mouse.getPos()[1]) / max(1, travel)
                self.offset = round(fraction * self.max_offset)
        self.offset = max(0, min(self.max_offset, self.offset))
        scale = self.view.text_scale
        for index, label in enumerate(self.labels):
            line = self.offset + index
            if line >= len(self.lines):
                break
            label.text = self.lines[line]
            label.pos = (-self.view.text_width / 2 / scale,
                         (self.view.text_height / 2 - index * self.line_height) / scale)
            label.draw()
        if self.max_offset:
            self.track.draw()
            self.thumb.pos = (self.track.pos[0], self.view.text_height / 2 - self.thumb.height / 2
                              - self.offset / self.max_offset * (self.view.text_height - self.thumb.height))
            self.thumb.draw()
        self.footer.text = (f"Scroll: wheel / Up / Down / Page Up / Page Down   "
                            f"Lines {self.offset + 1}–{min(len(self.lines), self.offset + self.visible_count)} / {len(self.lines)}")
        self.footer.draw()
