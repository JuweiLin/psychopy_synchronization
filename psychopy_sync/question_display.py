"""Centered question stem and four mouse-selectable answer buttons."""

import math


class QuestionPage:
    def __init__(self, view, question, total):
        self.question = question
        self.buttons = []
        scale = view.text_scale
        width = view.text_width
        for font_size in (view.config.text_height_px, 26, 24, 22, 20, 18):
            options = dict(units="pix", font=view.config.font, color="white", height=font_size / scale,
                           alignText="center", wrapWidth=(width - 40) / scale, autoLog=False)
            stem = view.visual.TextStim(view.win, text=question.content, anchorVert="top", **options)
            stem_height = max(font_size, float(stem.boundingBox[1]) * scale)
            labels = [view.visual.TextStim(view.win, text=f"{letter}. {text}", **options)
                      for letter, text in zip("ABCD", question.options)]
            heights = [max(60, float(label.boundingBox[1]) * scale + 24) for label in labels]
            total_height = stem_height + 28 + sum(heights) + 12 * 3
            if total_height <= view.text_height:
                break
        else:
            raise ValueError(f"Question {question.question_id} does not fit the screen; shorten its text/options")
        self.font_size_px = font_size
        stem.pos = (0, total_height / 2 / scale)
        self.stem = stem
        cursor = total_height / 2 - stem_height - 28
        self.interest_areas = []
        for index, (letter, label, height) in enumerate(zip("ABCD", labels, heights), 1):
            center_y = cursor - height / 2
            rectangle = view.visual.Rect(view.win, width=width, height=height, units="pix", pos=(0, center_y),
                fillColor="#252B36", lineColor="#778397", autoLog=False)
            label.pos = (0, center_y / scale)
            self.buttons.append((letter, rectangle, label))
            left = max(0, math.floor((view.win.size[0] - width) / 2))
            top = max(0, math.floor(view.win.size[1] / 2 - center_y - height / 2))
            self.interest_areas.append(dict(word_index=index, ia_label="option_" + letter, left=left, top=top,
                right=min(int(view.win.size[0]) - 1, math.ceil((view.win.size[0] + width) / 2) - 1),
                bottom=min(int(view.win.size[1]) - 1, math.ceil(view.win.size[1] / 2 - center_y + height / 2) - 1)))
            cursor -= height + 12
        self.heading = view.visual.TextStim(view.win, text=f"Question {question.question_order} / {total}", units="pix",
            pos=(0, view.win.size[1] * 0.43 / scale), height=22 / scale, color="white", autoLog=False)
        self.footer = view.visual.TextStim(view.win, text="Click one answer. Escape: stop", units="pix",
            pos=(0, -view.win.size[1] * 0.44 / scale), height=20 / scale, color="white", autoLog=False)

    def draw(self):
        self.heading.draw()
        self.stem.draw()
        for _, rectangle, label in self.buttons:
            rectangle.draw()
            label.draw()
        self.footer.draw()

    def choice_at(self, mouse):
        return next((letter for letter, rectangle, _ in self.buttons if rectangle.contains(mouse)), None)
