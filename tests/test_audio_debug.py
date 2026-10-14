"""Debug option validation and isolated launcher outcomes, without audio hardware."""

import unittest

from psychopy_sync.audio_debug import DebugOptions
from psychopy_sync.launcher import audio_debug_command, result_message


class AudioDebugOptionsTests(unittest.TestCase):
    def test_speed_sweep_preserves_order_and_replays_are_separate_from_generation(self):
        options = DebugOptions.from_dict(dict(text="Listen to the first words.", wpms="300, 150 225.5", repeats=3))
        self.assertEqual(options.wpms, (300, 150, 225.5))
        self.assertEqual(options.repeats, 3)

    def test_unusable_speeds_text_and_repetition_counts_are_rejected(self):
        for values in ("", "0", "-10", "nan", "inf", "120,120", "fast", [True], None):
            with self.subTest(values=values), self.assertRaises(ValueError):
                DebugOptions.from_dict(dict(text="First words.", wpms=values))
        for repeat in (0, 11, 1.5, True):
            with self.subTest(repeat=repeat), self.assertRaises(ValueError):
                DebugOptions.from_dict(dict(text="First words.", wpms="120", repeats=repeat))
        with self.assertRaises(ValueError):
            DebugOptions.from_dict(dict(text=" ", wpms="120"))

    def test_debug_launch_is_explicitly_dummy_and_does_not_need_reading_speed_results(self):
        command = audio_debug_command("options.json", "result.json")
        self.assertEqual(command[1:5], ["-m", "psychopy_sync.audio_debug", "--participant-id", "0"])
        title, text = result_message(dict(audio_debug=True, status="completed", generated=3, rated=6,
                                         generation_failures=1, directory="data/dummy/audio_debug/run"))
        self.assertEqual(title, "Audio debug complete")
        self.assertIn("Generated WAVs: 3", text)
        self.assertIn("Failed speeds: 1", text)
        self.assertIn("data/dummy/audio_debug/run", text)


if __name__ == "__main__":
    unittest.main()
