"""Main-thread PsychoPy reading UI; all layouts are prepared before recording."""

from .condition1 import ExperimentAborted
from .data_viewer import DataViewerExport
from .word_layout import WordPage


class ReadingDisplay:
    def __init__(self, win, config, controller):
        from psychopy import visual
        from psychopy.hardware.keyboard import Keyboard

        self.win, self.config, self.controller = win, config, controller
        self.visual = visual
        self.keyboard = Keyboard()
        self.data_viewer = None
        self.text_width = int(win.size[0] * config.text_width_fraction)
        self.text_height = int(win.size[1] * config.text_height_fraction)
        scale = self.text_scale
        self.prompt = visual.TextStim(win, text="", height=config.text_height_px / scale, color="white",
                                      font=config.font, wrapWidth=self.text_width / scale, autoLog=False)
        self.footer = visual.TextStim(win, text=f"{config.advance_key.upper()}: next page / finish", height=20 / scale, color="white",
                                      pos=(0, -win.size[1] * 0.44 / scale), autoLog=False)
        self.baseline_cross = visual.TextStim(win, text="+", units="pix", pos=(0, 0),
                                             height=config.text_height_px / scale,
                                             font=config.font, color="white", autoLog=False)

    @property
    def text_scale(self):
        # Legacy TextStim's Window.setScale('pix') applies a 2x Retina
        # multiplier, although win.size / DISPLAY_COORDS use framebuffer
        # pixels. New OpenGL backends do not apply this legacy multiplier.
        return 2.0 if (getattr(self.win, "useRetina", False)
                       and getattr(self.win, "USE_LEGACY_GL", False)) else 1.0

    def prepare(self, articles):
        prepared = {}
        scale = self.text_scale
        for article in articles:
            pages = []
            for index, text in enumerate(article.pages, 1):
                try:
                    pages.append(WordPage(self.win, self.visual, self.config, text,
                                          self.text_width, self.text_height, scale))
                except ValueError as exc:
                    raise ValueError(f"Article {article.title!r}, page {index}: {exc}; "
                                     "adjust the prepared CSV page or the text layout") from exc
            prepared[article.article_id] = pages
        return prepared

    def export_pages(self, store, articles, prepared):
        self.prompt.text = "Preparing sentence images and word interest areas. Please wait."
        self.prompt.draw()
        # Establish the normal post-flip projection/viewport before taking
        # back-buffer captures, including on Retina displays.
        self.win.flip()
        self.data_viewer = DataViewerExport(store)
        self.data_viewer.prepare(self, articles, prepared)

    def draw_page(self, page, condition):
        page.draw()
        if condition == "condition1":
            self.footer.draw()

    def _page_on_flip(self, log, onset, condition, article_id, page_index):
        timing = {}
        self.win.timeOnFlip(timing, "timestamp")

        def callback():
            timestamp = timing["timestamp"]
            self.data_viewer.start_page(log, condition, article_id, page_index, timestamp)
            if page_index == 1:
                onset.update(log.emit("ARTICLE_ONSET", condition, article_id, page=1, timestamp=timestamp))

        self.win.callOnFlip(callback)

    def show_saving(self):
        self.prompt.text = "Saving session data. Please wait."
        self.prompt.draw()
        self.win.flip()

    def _advance_key_held(self):
        state = self.keyboard.getState(self.config.advance_key)
        # PsychoPy versions can return a scalar or a one-item sequence.
        return bool(state[0]) if isinstance(state, (list, tuple)) else bool(state)

    def _wait(self, draw, first_flip=None):
        kb, config = self.keyboard, self.config
        kb.clearEvents()
        # A held key from the previous screen must be released before a new press.
        armed = not self._advance_key_held()
        draw()
        if first_flip is not None:
            first_flip()
        self.win.flip()
        while True:
            self.controller.check_recording()
            keys = kb.getKeys(keyList=[config.advance_key, config.quit_key], waitRelease=False, clear=True)
            if any(k.name == config.quit_key for k in keys):
                raise ExperimentAborted("Escape pressed")
            if armed and any(k.name == config.advance_key for k in keys):
                return
            if not armed and not self._advance_key_held():
                armed = True
                kb.clearEvents()
            draw()
            self.win.flip()

    def wait_screen(self, text, log, event="WAIT", article_id="", condition="condition1"):
        self.prompt.text = text
        self._wait(self.prompt.draw, lambda: log.on_flip(
            self.win, {}, event, condition=condition, article_id=article_id))
        log.flush()

    def read_page(self, page, log, onset, event, article_id, page_index):
        def draw():
            self.draw_page(page, "condition1")

        self._wait(draw, lambda: self._page_on_flip(log, onset, "condition1", article_id, page_index))

    def show_baseline(self, log, condition, article_id):
        """Keep '+' visible until the first sentence's flip can reach 1500 ms.

        Return with the cross still on the front buffer; the caller replaces
        it directly with the sentence. Both ends are recorded on real flips.
        getFutureFlipTime(None) and timeOnFlip share PsychoPy's default clock.
        """
        self.keyboard.clearEvents()
        self.controller.check_recording()
        self.baseline_cross.draw()
        timing = {}
        self.win.timeOnFlip(timing, "timestamp")
        self.win.callOnFlip(lambda: self.data_viewer.start_baseline(
            log, condition, article_id, timing["timestamp"]))
        self.win.flip()
        deadline = timing["timestamp"] + self.config.article_baseline_s
        while True:
            self.controller.check_recording()
            if self.keyboard.getKeys(keyList=[self.config.quit_key], waitRelease=False, clear=True):
                raise ExperimentAborted("Escape pressed during article baseline")
            if self.win.getFutureFlipTime(clock=None) >= deadline - 1e-6:
                return
            self.baseline_cross.draw()
            self.win.flip()

    def clear_article(self, log, end, event, article_id, condition="condition1", page=None, page_status="completed"):
        self.win.clearBuffer()
        timing = {}
        self.win.timeOnFlip(timing, "timestamp")
        self.win.callOnFlip(lambda: self.data_viewer.end_phase(log, timing["timestamp"], status=page_status))
        log.on_flip(self.win, end, event, condition=condition, article_id=article_id)
        self.win.flip()

    def wait_for_audio(self, batch, log, article_id):
        """Release this article as soon as its sentences are verified locally."""
        self.keyboard.clearEvents()
        log.emit("AUDIO_WAIT", "condition2", article_id)
        log.flush()
        self.prompt.text = "Condition 2\n\nPreparing audio. Please wait."
        while True:
            self.controller.check_recording()
            keys = self.keyboard.getKeys(keyList=[self.config.quit_key], waitRelease=False, clear=True)
            if keys:
                raise ExperimentAborted("Escape pressed during audio preparation")
            batch.poll(log)
            error = batch.article_error(article_id)
            if error:
                raise RuntimeError(f"TTS failed for article {article_id}: {error}")
            if batch.article_ready(article_id):
                return
            if batch.done:
                raise RuntimeError(f"Audio for article {article_id} is unavailable ({batch.manifest['status']})")
            self.prompt.draw()
            self.win.flip()

    def play_page(self, page, playback, cached, log, onset, article_id, page_index):
        """Schedule a preloaded sentence on its first flip; wait for PTB EOS."""
        self.keyboard.clearEvents()
        self.controller.check_recording()
        page.draw()
        scheduled = self.win.getFutureFlipTime(clock="ptb")
        detail = f"scheduled_ptb_s={scheduled:.9f}; job_id={cached.job_id}; path={cached.path}"
        try:
            playback.play(when=scheduled)
            self._page_on_flip(log, onset, "condition2", article_id, page_index)
            log.on_flip(self.win, {}, "AUDIO_START", condition="condition2", article_id=article_id,
                        page=page_index, detail=detail, marker="AUDIO_START")
            self.win.flip()
            deadline = log.clock() + cached.metadata["duration_s"] + 10.0
            while True:
                self.controller.check_recording()
                if self.keyboard.getKeys(keyList=[self.config.quit_key], waitRelease=False, clear=True):
                    raise ExperimentAborted("Escape pressed during Condition 2 playback")
                if playback.isFinished:
                    log.emit("AUDIO_END", "condition2", article_id, page=page_index,
                             detail=f"PTB completion observed; job_id={cached.job_id}", marker="AUDIO_END")
                    return
                if log.clock() > deadline:
                    raise RuntimeError(f"Audio playback timed out for article {article_id}, sentence {page_index}")
                page.draw()
                self.win.flip()
        except BaseException:
            try:
                log.emit("AUDIO_ABORT", "condition2", article_id, page=page_index, detail=detail,
                         marker="AUDIO_ABORT")
            except Exception:
                pass  # Keep the original playback/recording failure.
            raise
        finally:
            playback.stop()
