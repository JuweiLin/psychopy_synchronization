"""Native options dialog for dummy-only audio onset checks."""

import csv
from dataclasses import asdict
from pathlib import Path

from .audio_debug import DebugOptions


def show_audio_debug_dialog(parent, config):
    import wx

    articles = {}
    folder = Path(config.assets_dir) / config.articles_folder
    for path in sorted(folder.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        if rows and all(len(row) <= 1 for row in rows):
            pages = [row[0] for row in rows[1:] if row and row[0].strip()]
            if pages:
                articles[path.stem] = pages
    if not articles:
        raise ValueError("No article pages are available for audio debug.")
    dialog = wx.Dialog(parent, title="Audio Onset Debug — Dummy Mode", size=(680, 650),
                       style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    layout = wx.BoxSizer(wx.VERTICAL)
    layout.Add(wx.StaticText(dialog, label="Test the same text at several generated speaking speeds."), 0, wx.ALL, 16)
    source_row = wx.BoxSizer(wx.HORIZONTAL)
    source_row.Add(wx.StaticText(dialog, label="Article"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
    article = wx.Choice(dialog, choices=list(articles))
    article.SetSelection(0)
    source_row.Add(article, 1, wx.RIGHT, 12)
    source_row.Add(wx.StaticText(dialog, label="Body page"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
    page = wx.SpinCtrl(dialog, min=1, max=len(articles[article.GetStringSelection()]), initial=1, size=(80, -1))
    source_row.Add(page, 0, wx.RIGHT, 12)
    load = wx.Button(dialog, label="Load page")
    source_row.Add(load, 0)
    layout.Add(source_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 16)
    layout.Add(wx.StaticText(dialog, label="Text (editable)"), 0, wx.LEFT | wx.TOP, 16)
    text = wx.TextCtrl(dialog, style=wx.TE_MULTILINE)
    layout.Add(text, 1, wx.EXPAND | wx.ALL, 16)
    source = {}

    def load_page(event=None):
        identifier = article.GetStringSelection()
        index = page.GetValue()
        text.ChangeValue(articles[identifier][index - 1])
        source.update(source_article_id=identifier, source_page=index)

    def article_changed(event):
        page.SetRange(1, len(articles[article.GetStringSelection()]))
        page.SetValue(1)
        load_page()

    article.Bind(wx.EVT_CHOICE, article_changed)
    load.Bind(wx.EVT_BUTTON, load_page)
    load_page()
    layout.Add(wx.StaticText(dialog, label="WPM values (commas or spaces; tested in this order)"), 0, wx.LEFT | wx.RIGHT, 16)
    wpms = wx.TextCtrl(dialog, value="100, 150, 200, 250, 300, 400")
    layout.Add(wpms, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 16)
    repeat_row = wx.BoxSizer(wx.HORIZONTAL)
    repeat_row.Add(wx.StaticText(dialog, label="Plays per speed"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)
    repeats = wx.SpinCtrl(dialog, min=1, max=10, initial=2, size=(80, -1))
    repeat_row.Add(repeats, 0)
    layout.Add(repeat_row, 0, wx.ALL, 16)
    explanation = wx.StaticText(dialog, label="Each speed generates one WAV. Replays use that exact file.\n"
        "After playback: C = complete, M = missing beginning, U = unsure, R = replay.\n"
        "Uses Condition 2 playback. No Condition 1 reading or EyeLink is needed.")
    explanation.Wrap(630)
    layout.Add(explanation, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 16)
    error = wx.StaticText(dialog, label="")
    error.SetForegroundColour("#B42318")
    layout.Add(error, 0, wx.EXPAND | wx.ALL, 16)
    buttons = wx.BoxSizer(wx.HORIZONTAL)
    cancel = wx.Button(dialog, id=wx.ID_CANCEL, label="Cancel")
    begin = wx.Button(dialog, label="Generate and listen")
    begin.SetDefault()
    buttons.AddStretchSpacer()
    buttons.Add(cancel, 0, wx.RIGHT, 8)
    buttons.Add(begin, 0)
    layout.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
    selected = {}

    def start(event):
        try:
            if not config.tts_server_url:
                raise ValueError("Set tts_server_url in config.py first.")
            options = DebugOptions.from_dict(dict(text=text.GetValue(), wpms=wpms.GetValue(),
                                                 repeats=repeats.GetValue(), **source))
        except ValueError as exc:
            error.SetLabel(str(exc))
            error.Wrap(630)
            dialog.Layout()
            return
        selected.update(asdict(options))
        dialog.EndModal(wx.ID_OK)

    begin.Bind(wx.EVT_BUTTON, start)
    dialog.SetSizer(layout)
    dialog.CentreOnParent()
    try:
        return selected if dialog.ShowModal() == wx.ID_OK else None
    finally:
        dialog.Destroy()
