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

    def wait_screen(self, text, log, event="WAIT", article_id="", condition="condition1"):
        self.prompt.text = text
        self._wait(self.prompt.draw, lambda: log.on_flip(
            self.win, {}, event, condition=condition, article_id=article_id))
        log.flush()

    def read_page(self, page, log, onset, event, article_id, page_index):
        def draw():
            page.draw()
            self.footer.draw()

        self._wait(draw, lambda: log.on_flip(self.win, onset, event, condition="condition1",
                                            article_id=article_id, page=page_index))

    def clear_article(self, log, end, event, article_id, condition="condition1", page=None):
        if page is not None:
            log.on_flip(self.win, {}, "PAGE_END", condition=condition, article_id=article_id, page=page)
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
            if page_index > 1:
                log.on_flip(self.win, {}, "PAGE_END", condition="condition2", article_id=article_id, page=page_index - 1)
            else:
                log.on_flip(self.win, onset, "ARTICLE_ONSET", condition="condition2", article_id=article_id, page=1)
            log.on_flip(self.win, {}, "PAGE_ONSET", condition="condition2", article_id=article_id, page=page_index)
            log.on_flip(self.win, {}, "AUDIO_START", condition="condition2", article_id=article_id,
                        page=page_index, detail=detail)
            self.win.flip()
            deadline = log.clock() + cached.metadata["duration_s"] + 10.0
            while True:
                self.controller.check_recording()
                if self.keyboard.getKeys(keyList=[self.config.quit_key], waitRelease=False, clear=True):
                    raise ExperimentAborted("Escape pressed during Condition 2 playback")
                if playback.isFinished:
                    log.emit("AUDIO_END", "condition2", article_id, page=page_index,
                             detail=f"PTB completion observed; job_id={cached.job_id}")
                    return
                if log.clock() > deadline:
                    raise RuntimeError(f"Audio playback timed out for article {article_id}, sentence {page_index}")
                page.draw()
                self.win.flip()
        except BaseException:
            try:
                log.emit("AUDIO_ABORT", "condition2", article_id, page=page_index, detail=detail)
            except Exception:
                pass  # Keep the original playback/recording failure.
            raise
        finally:
            playback.stop()
