"""Root user settings reach runtime selection and experiment defaults."""

from dataclasses import replace
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest

from psychopy_sync.config import PROJECT_ROOT
from psychopy_sync.launcher_bootstrap import required_modules


class UserConfigTests(unittest.TestCase):
    def load_config(self, settings):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        internal = root / "psychopy_sync" / "config.py"
        internal.parent.mkdir()
        shutil.copyfile(PROJECT_ROOT / "psychopy_sync" / "config.py", internal)
        (root / "config.py").write_text(settings, encoding="utf-8")
        return runpy.run_path(str(internal))

    def test_edited_settings_control_real_mode_counts_tracker_and_tts(self):
        module = self.load_config('condition1_count = 3\n'
            'condition2_count = 5\neyelink_ip = "100.1.1.2"\n'
            'tts_server_url = "http://192.168.1.20:8765"\n')
        config = module["ExperimentConfig"]()
        self.assertEqual(required_modules(config),
                         ("psychopy", "wx", "psychtoolbox", "soundfile", "pylink", "EyeLinkCoreGraphicsPsychoPy"))
        self.assertEqual((config.condition1_count, config.condition2_count), (3, 5))
        self.assertEqual(module["EyeLinkConfig"]().ip, "100.1.1.2")
        self.assertEqual(config.tts_server_url, "http://192.168.1.20:8765")
        self.assertEqual(replace(config, condition1_count=1).condition1_count, 1)

    def test_dummy_override_and_empty_url_keep_hardware_and_service_optional(self):
        module = self.load_config('condition1_count = 1\n'
            'condition2_count = 0\neyelink_ip = "100.1.1.1"\ntts_server_url = ""\n')
        config = module["ExperimentConfig"](dummy_mode=True)
        self.assertEqual(required_modules(config), ("psychopy", "wx"))
        self.assertIsNone(config.tts_server_url)
        self.assertEqual(config.condition2_count, 0)

    def test_invalid_user_count_is_rejected(self):
        module = self.load_config('condition1_count = 0\n'
            'condition2_count = 2\neyelink_ip = "100.1.1.1"\ntts_server_url = ""\n')
        with self.assertRaisesRegex(ValueError, "condition1_count"):
            module["ExperimentConfig"]()

    def test_tts_cap_limits_fast_reading_and_preserves_slower_reading(self):
        from psychopy_sync.config import ExperimentConfig
        for setting, cap in ((True, 210), (190, 190), (205.5, 205.5)):
            with self.subTest(setting=setting):
                config = ExperimentConfig(speed_cap=setting)
                self.assertEqual(config.tts_speed_cap_wpm, cap)
                self.assertEqual(config.tts_target_wpm(300), cap)
                self.assertEqual(config.tts_target_wpm(150), 150)

    def test_false_removes_tts_cap(self):
        from psychopy_sync.config import ExperimentConfig
        config = ExperimentConfig(speed_cap=False)
        self.assertIsNone(config.tts_speed_cap_wpm)
        self.assertEqual(config.tts_target_wpm(300), 300)

    def test_invalid_speed_cap_is_rejected(self):
        from psychopy_sync.config import ExperimentConfig
        for value in (0, -1, "210", None, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "speed_cap"):
                ExperimentConfig(speed_cap=value)

    def test_root_speed_cap_reaches_runtime(self):
        module = self.load_config('condition1_count = 4\ncondition2_count = 4\n'
            'eyelink_ip = "100.1.1.1"\ntts_server_url = ""\nspeed_cap = 195\n')
        config = module["ExperimentConfig"]()
        self.assertEqual(config.tts_target_wpm(300), 195)


if __name__ == "__main__":
    unittest.main()
