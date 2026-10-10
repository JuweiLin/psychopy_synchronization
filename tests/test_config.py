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
        module = self.load_config('dummy_mode = False\ncondition1_count = 3\n'
            'condition2_count = 5\neyelink_ip = "100.1.1.2"\n'
            'tts_server_url = "http://192.168.1.20:8765"\n')
        config = module["ExperimentConfig"]()
        self.assertEqual(required_modules(config),
                         ("psychopy", "wx", "pylink", "EyeLinkCoreGraphicsPsychoPy"))
        self.assertEqual((config.condition1_count, config.condition2_count), (3, 5))
        self.assertEqual(module["EyeLinkConfig"]().ip, "100.1.1.2")
        self.assertEqual(config.tts_server_url, "http://192.168.1.20:8765")
        self.assertEqual(replace(config, condition1_count=1).condition1_count, 1)

    def test_dummy_switch_and_empty_url_keep_hardware_and_service_optional(self):
        module = self.load_config('dummy_mode = True\ncondition1_count = 1\n'
            'condition2_count = 0\neyelink_ip = "100.1.1.1"\ntts_server_url = ""\n')
        config = module["ExperimentConfig"]()
        self.assertEqual(required_modules(config), ("psychopy", "wx"))
        self.assertIsNone(config.tts_server_url)
        self.assertEqual(config.condition2_count, 0)

    def test_invalid_user_count_is_rejected(self):
        module = self.load_config('dummy_mode = True\ncondition1_count = 0\n'
            'condition2_count = 2\neyelink_ip = "100.1.1.1"\ntts_server_url = ""\n')
        with self.assertRaisesRegex(ValueError, "condition1_count"):
            module["ExperimentConfig"]()


if __name__ == "__main__":
    unittest.main()
