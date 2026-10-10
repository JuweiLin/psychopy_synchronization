"""Main-thread PsychoPy reading UI; all layouts are prepared before recording."""

from .condition1 import ExperimentAborted


class ReadingDisplay:
    def __init__(self, win, config, controller):
        from psychopy import visual
        from psychopy.hardware.keyboard import Keyboard

        self.win, self.config, self.controller = win, config, controller
        self.visual = visual
        self.keyboard = Keyboard()
        self.text_width = int(win.size[0] * config.text_width_fraction)
        self.text_height = int(win.size[1] * config.text_height_fraction)
        self.prompt = visual.TextStim(win, text="", height=config.text_height_px, color="white",
                                      font=config.font, wrapWidth=self.text_width, autoLog=False)
        self.footer = visual.TextStim(win, text=f"{config.advance_key.upper()}: next page / finish", height=20, color="white",
                                      pos=(0, -win.size[1] * 0.44), autoLog=False)

    def prepare(self, articles):
        prepared = {}
        for article in articles:
            probe = self.visual.TextStim(self.win, text="", height=self.config.text_height_px,
                                         font=self.config.font, wrapWidth=self.text_width, autoLog=False)

            def fits(text):
                probe.text = text
                width, height = probe.boundingBox
                return width <= self.text_width and height <= self.text_height

            page_texts = article.pages
            for index, text in enumerate(page_texts, 1):
                if not fits(text):
                    raise ValueError(f"Article {article.title!r}, page {index} exceeds the configured display area; "
                                     "adjust the prepared CSV page or the text layout")
            prepared[article.article_id] = [self.visual.TextStim(
                self.win, text=text, height=self.config.text_height_px, font=self.config.font,
                wrapWidth=self.text_width, color="white", alignText="left", autoLog=False,
            ) for text in page_texts]
        return prepared

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

    def wait_screen(self, text, log, event="WAIT", article_id=""):
        self.prompt.text = text
        self._wait(self.prompt.draw, lambda: log.on_flip(
            self.win, {}, event, condition="condition1", article_id=article_id))
        log.flush()

    def read_page(self, page, log, onset, event, article_id, page_index):
        def draw():
            page.draw()
            self.footer.draw()

        self._wait(draw, lambda: log.on_flip(self.win, onset, event, condition="condition1",
                                            article_id=article_id, page=page_index))

    def clear_article(self, log, end, event, article_id):
        log.on_flip(self.win, end, event, condition="condition1", article_id=article_id)
        self.win.flip()

    def wait_for_audio(self, batch, log):
        self.keyboard.clearEvents()
        log.emit("AUDIO_WAIT", "condition2")
        log.flush()
        self.prompt.text = "Condition 1 complete.\n\nPreparing audio. Please wait."
        while not batch.done:
            self.controller.check_recording()
            keys = self.keyboard.getKeys(keyList=[self.config.quit_key], waitRelease=False, clear=True)
            if keys:
                raise ExperimentAborted("Escape pressed during audio preparation")
            batch.poll(log)
            self.prompt.draw()
            self.win.flip()
        if batch.failed:
            raise RuntimeError("TTS generation/download failed; see audio_error and the TTS manifest")
