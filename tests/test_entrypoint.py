import os
import subprocess
import sys
from pathlib import Path

from tests.helpers import ProjectTest


class EntrypointTests(ProjectTest):
    def test_script_and_module_entrypoints_work_outside_project_directory(self):
        project = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PYTHONPATH=str(project), PYTHONUTF8="1")
        for command in ([str(project / "main.py")], ["-m", "ai_butler"]):
            with self.subTest(command=command):
                result = subprocess.run(
                    [sys.executable, *command, "--help"],
                    cwd=self.root,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=15,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--channel", result.stdout)
                self.assertIn("--model", result.stdout)
