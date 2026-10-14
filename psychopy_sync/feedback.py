"""Fixed, silent post-article feedback with continuous ratings and typed notes."""

from dataclasses import dataclass
import json
import math

from .condition1 import ExperimentAborted


@dataclass(frozen=True)
class FeedbackItem:
    order: int
    question_id: str
    content: str
    kind: str
    low_label: str = ""
    high_label: str = ""
    note_prompt: str = ""


FEEDBACK_ITEMS = (
    FeedbackItem(1, "F01", "How easy was it to follow the article across screen changes?",
                 "slider", "very difficult", "very easy"),
    FeedbackItem(2, "F02", "How appropriate were the six questions as a set?",
                 "slider", "not appropriate", "very appropriate"),
    FeedbackItem(3, "F03", "Did any questions repeat the same point unnecessarily?",
                 "choice_text", note_prompt="If Yes, give the question IDs. You may also explain an Unsure answer."),
    FeedbackItem(4, "F04", "Was an important article idea missing from the questions?",
                 "choice_text", note_prompt="If Yes, describe the missing idea. You may also explain an Unsure answer."),
    FeedbackItem(5, "F05", "Any additional screen, text, audio, or question concerns?",
                 "text", note_prompt="Type any concerns below, or leave blank if you have none."),
)


class FeedbackPage:
    """One reusable page per fixed item; coordinates match the button AOIs."""

    def __init__(self, view, item):
        self.view, self.item = view, item
        self.value = None
        self.choice = ""
        self.dragging = False
        self.buttons = []
        self.interest_areas = []
        self.scale = view.text_scale
        self.width = min(view.text_width * 0.78, 1000)
        height = int(view.win.size[1])
        # The question is centered, directly above its response controls.
        self.stem = self.label(item.content, (0, height * 0.17), view.config.text_height_px,
                               wrap=view.text_width)
        self.heading = self.label(f"Article feedback {item.order} / {len(FEEDBACK_ITEMS)}",
                                  (0, height * 0.43), 22)
        self.footer = self.label("Click Continue to submit. Escape: stop", (0, -height * 0.44), 20)
        self.error = self.label("", (0, -height * 0.32), 20)
        self.error.color = "#FFCA80"
        self.submit = self.rectangle((0, -height * 0.38), (220, 56))
        self.submit_label = self.label("Continue", self.submit.pos, 24)
        self.add_area("continue", self.submit.pos, (220, 56))
        self.textbox = None
        if item.kind == "slider":
            self.track_y = -height * 0.02
            self.track = self.rectangle((0, self.track_y), (self.width, 6))
            self.track.fillColor = "#A9B5C7"
            self.slider_hit = self.rectangle((0, self.track_y), (self.width + 30, 60))
            self.knob = view.visual.Circle(view.win, radius=12, units="pix", fillColor="#65C3FF",
                                           lineColor="white", autoLog=False)
            self.ticks, self.tick_labels = [], []
            for number in range(1, 5):
                x = -self.width / 2 + self.width * (number - 1) / 3
                self.ticks.append(self.rectangle((x, self.track_y), (2, 24)))
                caption = (f"1\n{item.low_label}" if number == 1 else
                           f"4\n{item.high_label}" if number == 4 else str(number))
                self.tick_labels.append(self.label(caption, (x, self.track_y - 55), 22,
                                                    wrap=self.width * 0.30))
            self.value_label = self.label("Click or drag anywhere on the scale", (0, height * 0.06), 20)
            self.add_area("rating_slider", self.slider_hit.pos, (self.width + 30, 60))
        else:
            if item.kind == "choice_text":
                for index, choice in enumerate(("No", "Yes", "Unsure")):
                    pos = ((index - 1) * self.width / 3, height * 0.04)
                    rectangle = self.rectangle(pos, (self.width / 3 - 20, 52))
                    self.buttons.append((choice, rectangle, self.label(choice, pos, 24)))
                    self.add_area("choice_" + choice, pos, (self.width / 3 - 20, 52))
            self.note = self.label(item.note_prompt, (0, -height * 0.05), 20, wrap=view.text_width)
            # TextBox2 handles normal typing, editing and pasted text via the window.
            # Keep all boxes disabled except the currently displayed feedback page.
            self.textbox = view.visual.TextBox2(view.win, text="", units="pix", font=view.config.font,
                letterHeight=24, pos=(0, -height * 0.19), size=(self.width, height * 0.20),
                color="white", fillColor="#151C26", borderColor="#778397", padding=12,
                placeholder="Type here...", editable=False, autoLog=False)
            self.add_area("feedback_text", self.textbox.pos, (self.width, height * 0.20))

    def label(self, text, pos, size, wrap=None):
        return self.view.visual.TextStim(self.view.win, text=text, units="pix", font=self.view.config.font,
            height=size / self.scale, pos=(pos[0] / self.scale, pos[1] / self.scale),
            alignText="center", wrapWidth=(wrap or self.view.text_width) / self.scale,
            color="white", autoLog=False)

    def rectangle(self, pos, size):
        return self.view.visual.Rect(self.view.win, units="pix", pos=pos, width=size[0], height=size[1],
                                     fillColor="#252B36", lineColor="#778397", autoLog=False)

    def add_area(self, label, pos, size):
        width, height = (int(value) for value in self.view.win.size)
        self.interest_areas.append(dict(word_index=len(self.interest_areas) + 1, ia_label=label,
            left=max(0, math.floor(width / 2 + pos[0] - size[0] / 2)),
            right=min(width - 1, math.ceil(width / 2 + pos[0] + size[0] / 2) - 1),
            top=max(0, math.floor(height / 2 - pos[1] - size[1] / 2)),
            bottom=min(height - 1, math.ceil(height / 2 - pos[1] + size[1] / 2) - 1)))

    def reset(self, question_ids=()):
        self.value, self.choice, self.dragging = None, "", False
        self.error.text = ""
        if self.item.kind == "slider":
            self.value_label.text = "Click or drag anywhere on the scale"
        if self.textbox is not None:
            self.textbox.editable = False
            self.textbox.text = ""
            self.textbox.hasFocus = False
            # Include IDs on the live page and its prepared background image.
            self.note.text = self.item.note_prompt
            if self.item.question_id == "F03":
                self.note.text += "\nQuestion IDs: " + ", ".join(question_ids)

    def draw(self):
        self.heading.draw()
        self.stem.draw()
        if self.item.kind == "slider":
            self.track.draw()
            for tick, label in zip(self.ticks, self.tick_labels):
                tick.draw()
                label.draw()
            if self.value is not None:
                self.knob.pos = (-self.width / 2 + self.width * (self.value - 1) / 3, self.track_y)
                self.knob.draw()
            self.value_label.draw()
        else:
            for choice, rectangle, label in self.buttons:
                rectangle.fillColor = "#245B80" if choice == self.choice else "#252B36"
                rectangle.draw()
                label.draw()
            self.note.draw()
            self.textbox.draw()
        self.submit.draw()
        self.submit_label.draw()
        self.error.draw()
        self.footer.draw()

    def update_mouse(self, mouse, pressed, fresh):
        if self.item.kind == "slider":
            if fresh and self.slider_hit.contains(mouse):
                self.dragging = True
            if self.dragging and pressed:
                x = mouse.getPos()[0]
                self.value = 1 + 3 * max(0, min(1, (x + self.width / 2) / self.width))
                self.value_label.text = f"{self.value:.2f}"
            if not pressed:
                self.dragging = False
        elif fresh:
            for choice, rectangle, _ in self.buttons:
                if rectangle.contains(mouse):
                    self.choice = choice
        return fresh and self.submit.contains(mouse)

    def answer(self):
        return dict(rating=self.value if self.value is not None else "", selected_answer=self.choice,
                    response_text=self.textbox.text.strip() if self.textbox is not None else "")

    def valid(self):
        if self.item.kind == "slider" and self.value is None:
            self.error.text = "Please choose a position on the scale."
        elif self.item.kind == "choice_text" and not self.choice:
            self.error.text = "Please choose No, Yes, or Unsure."
        elif self.choice == "Yes" and not self.answer()["response_text"]:
            self.error.text = "Please add the question IDs or a description."
        else:
            self.error.text = ""
            return True
        return False


def ask_feedback(view, article, log, store, condition):
    rows = [row for row in store.feedback_rows if row["condition"] == condition and row["article_id"] == article.article_id]
    question_ids = [row["question_id"] for row in store.question_rows
                    if row["condition"] == condition and row["article_id"] == article.article_id]
    mouse = view.question_mouse
    mouse.setVisible(True)
    store.metadata["feedback_status"] = "running"
    try:
        for row in rows:
            page = view.feedback_pages[row["question_order"]]
            auxiliary = view.data_viewer.auxiliary[condition, article.article_id, f"f{row['question_order']:03d}"]
            page.reset(question_ids)
            view.keyboard.clearEvents()
            armed = not mouse.getPressed()[0]
            try:
                page.draw()
                view._auxiliary_on_flip(log, condition, article.article_id, auxiliary["item_id"])
                view.win.flip()
                row.update(status="presenting", start_event_id=auxiliary["start_event_id"],
                           start_timestamp_s=auxiliary["start_timestamp_s"])
                if page.textbox is not None:
                    page.textbox.editable = True
                    page.textbox.hasFocus = True
                while True:
                    view.controller.check_recording()
                    if view.keyboard.getKeys(keyList=[view.config.quit_key], waitRelease=False, clear=True):
                        raise ExperimentAborted("Escape pressed during article feedback")
                    pressed = bool(mouse.getPressed()[0])
                    fresh = armed and pressed
                    submit = page.update_mouse(mouse, pressed, fresh)
                    if pressed:
                        armed = False
                    else:
                        armed = True
                    if submit and page.valid():
                        answer = page.answer()
                        token = (f"{answer['rating']:.6f}" if answer["rating"] != "" else
                                 answer["selected_answer"] or "text")
                        response = log.emit("FEEDBACK_RESPONSE", condition, article.article_id,
                            page=row["question_order"], marker=f"FEEDBACK_RESPONSE {row['question_id']} {token}",
                            detail=json.dumps(answer, ensure_ascii=True))
                        row.update(status="answered", **answer, response_event_id=response["event_id"],
                            response_timestamp_s=response["timestamp_s"],
                            response_time_s=response["timestamp_s"] - row["start_timestamp_s"])
                        log.emit("DV_TRIAL_VAR", condition, article.article_id, page=row["question_order"],
                                 marker=f"!V TRIAL_VAR selected_answer {token}")
                        break
                    page.draw()
                    view.win.flip()
                view.clear_auxiliary(log)
                row.update(status="completed", end_event_id=auxiliary["end_event_id"],
                           end_timestamp_s=auxiliary["end_timestamp_s"])
            except BaseException as exc:
                row.update(page.answer())
                row["status"] = "aborted" if isinstance(exc, (ExperimentAborted, KeyboardInterrupt)) else "failed"
                try:
                    view.clear_auxiliary(log, row["status"])
                except Exception:
                    pass
                row.update(end_event_id=auxiliary["end_event_id"], end_timestamp_s=auxiliary["end_timestamp_s"])
                raise
            finally:
                if page.textbox is not None:
                    page.textbox.editable = False
                    page.textbox.hasFocus = False
                log.flush()
                store.save()
        store.metadata["feedback_status"] = ("completed" if all(row["status"] == "completed" for row in store.feedback_rows)
                                             else "pending")
    except BaseException as exc:
        store.metadata["feedback_status"] = "aborted" if isinstance(exc, (ExperimentAborted, KeyboardInterrupt)) else "failed"
        raise
    finally:
        mouse.setVisible(False)
        store.save()
