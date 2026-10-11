"""Prepare word stimuli and their AOIs from one shared pixel layout."""

import math
import re


class WordPage:
    """One CSV page, with individually positioned PsychoPy TextStim words.

    All measurements/positions use framebuffer pixels. TextStim positions and
    font height are divided by the display's legacy Retina scale together.
    Nothing is measured or written during reading.
    """

    def __init__(self, win, visual, config, text, width, height, scale):
        self.text = text
        self.stimuli = []
        self.word_areas = []
        screen_width, screen_height = (int(value) for value in win.size)
        # Keep each label on one line; this module owns all wrapping. A label's
        # wrap frame is not its measured content width (boundingBox).
        wrap_width = max(screen_width * 2, len(text) * config.text_height_px * 2)

        def stimulus(value):
            return visual.TextStim(
                win, text=value, units="pix", font=config.font, color="white",
                height=config.text_height_px / scale, wrapWidth=wrap_width / scale,
                alignText="left", anchorHoriz="left", anchorVert="top", autoLog=False,
            )

        probe = stimulus("M")

        def measure(value):
            probe.text = value
            result = tuple(float(part) * scale for part in probe.boundingBox)
            if not all(math.isfinite(part) and part >= 0 for part in result):
                raise ValueError("The font returned invalid text dimensions")
            return result

        # Bracket the space so multiline label engines cannot discard it as
        # trailing whitespace. Measure the same font used for the actual words.
        bar_width, _ = measure("|")
        spaced_width, _ = measure("| |")
        space_width = spaced_width - 2 * bar_width
        if space_width <= 0:
            raise ValueError("Could not measure a space in the selected font")

        slots = []
        cursor = 0.0
        line = 0
        has_word = False
        previous_end = 0
        line_height = 0.0
        for match in re.finditer(r"\S+", text):
            word = match.group()
            word_stimulus = stimulus(word)
            word_width, word_height = (float(part) * scale for part in word_stimulus.boundingBox)
            if not all(math.isfinite(part) and part > 0 for part in (word_width, word_height)):
                raise ValueError(f"Could not measure word {word!r}")
            if word_width > width:
                raise ValueError(f"Word {word!r} exceeds the configured display width")
            separator = text[previous_end:match.start()].replace("\r\n", "\n").replace("\r", "\n")
            breaks = separator.count("\n")
            if breaks:
                line += breaks
                cursor, has_word = 0.0, False
            gap = len(separator.expandtabs(4)) * space_width if has_word else 0.0
            if has_word and cursor + gap + word_width > width:
                line += 1
                cursor, has_word, gap = 0.0, False, 0.0
            cursor += gap
            slots.append(dict(stimulus=word_stimulus, word=word, x=cursor,
                              width=word_width, height=word_height, line=line,
                              char_start=match.start(), char_end=match.end()))
            line_height = max(line_height, word_height)
            cursor += word_width
            has_word = True
            previous_end = match.end()
        if not slots:
            raise ValueError("A reading page must contain at least one word")
        line_gap = max(6, math.ceil(line_height * 0.25))
        total_height = (line + 1) * line_height + line * line_gap
        if total_height > height:
            raise ValueError("Page exceeds the configured display height")
        origin_x = (screen_width - width) / 2
        origin_y = (screen_height - total_height) / 2
        for index, slot in enumerate(slots, 1):
            left = origin_x + slot["x"]
            top = origin_y + slot["line"] * (line_height + line_gap)
            slot["stimulus"].pos = ((left - screen_width / 2) / scale,
                                      (screen_height / 2 - top) / scale)
            # Two pixels of padding, limited at the midpoint of each word gap.
            # Integer, inclusive rectangle edges never overlap adjacent words.
            aoi_left = max(0, math.floor(left) - 2)
            aoi_right = min(screen_width - 1, math.ceil(left + slot["width"]) + 1)
            if index > 1 and slots[index - 2]["line"] == slot["line"]:
                previous = slots[index - 2]
                midpoint = origin_x + (previous["x"] + previous["width"] + slot["x"]) / 2
                aoi_left = max(aoi_left, math.floor(midpoint))
            if index < len(slots) and slots[index]["line"] == slot["line"]:
                following = slots[index]
                midpoint = origin_x + (slot["x"] + slot["width"] + following["x"]) / 2
                aoi_right = min(aoi_right, math.floor(midpoint) - 1)
            aoi_top = max(0, math.floor(top) - 2)
            aoi_bottom = min(screen_height - 1, math.ceil(top + line_height) + 1)
            if aoi_left > aoi_right or aoi_top > aoi_bottom:
                raise ValueError(f"Invalid AOI for word {index}")
            # EDF messages contain only portable ASCII paths. IAS labels also
            # stay ASCII; the CSV retains the exact Unicode word and offsets.
            label = f"w{index:04d}_" + slot["word"].encode("ascii", "backslashreplace").decode("ascii")
            self.word_areas.append(dict(
                word_index=index, line_index=slot["line"] + 1, word=slot["word"], ia_label=label,
                char_start=slot["char_start"], char_end=slot["char_end"],
                left=aoi_left, top=aoi_top, right=aoi_right, bottom=aoi_bottom,
            ))
            self.stimuli.append(slot["stimulus"])

    def draw(self):
        for stimulus in self.stimuli:
            stimulus.draw()


def interest_area_text(areas):
    return "".join(
        f"RECTANGLE {area['word_index']} {area['left']} {area['top']} "
        f"{area['right']} {area['bottom']} {area['ia_label']}\n"
        for area in areas
    )
