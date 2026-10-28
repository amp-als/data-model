"""Offline regression tests for the package move (no Synapse calls)."""

import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from synapse_dataset_manager import cli

ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def test_entrypoint_help_parity(self):
        for arguments in (['--help'], ['update', '--help'], ['create', '--help']):
            with self.subTest(arguments=arguments):
                legacy = subprocess.run(
                    [sys.executable, 'synapse_dataset_manager.py', *arguments],
                    cwd=ROOT, capture_output=True, text=True, timeout=60,
                )
                package = subprocess.run(
                    [sys.executable, '-m', 'synapse_dataset_manager', *arguments],
                    cwd=ROOT, capture_output=True, text=True, timeout=60,
                )
                self.assertEqual(legacy.returncode, 0, legacy.stderr)
                self.assertEqual(package.returncode, 0, package.stderr)
                self.assertEqual(
                    legacy.stdout.split(),
                    package.stdout.replace('__main__.py', 'synapse_dataset_manager.py').split(),
                )

    def test_package_import_is_lightweight(self):
        result = subprocess.run(
            [sys.executable, '-c',
             'import sys; import synapse_dataset_manager; '
             'assert "synapseclient" not in sys.modules; '
             'assert "synapse_dataset_manager.cli" not in sys.modules'],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_config_paths_still_use_working_directory(self):
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                with patch.dict(os.environ, {}, clear=True):
                    config = cli.Config()
                self.assertEqual(config.BASE_DIR, directory)
                self.assertEqual(config.SCHEMA_BASE_PATH, str(Path(directory) / 'json-schemas'))
                self.assertEqual(config.ANNOTATIONS_DIR, str(Path(directory) / 'annotations'))
                self.assertTrue(Path(config.ANNOTATIONS_DIR).is_dir())
            finally:
                os.chdir(previous)

    def test_entrypoint_handles_failures_consistently(self):
        for error in (KeyboardInterrupt(), RuntimeError('test failure')):
            with self.subTest(error=type(error).__name__):
                with patch.object(cli, 'main', side_effect=error):
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as raised:
                            cli.entrypoint()
                self.assertEqual(raised.exception.code, 1)

    def test_followup_commands_support_module_invocation(self):
        with patch.object(sys, 'argv', ['/some/path/synapse_dataset_manager/__main__.py']):
            self.assertEqual(cli.cli_invocation(), 'python -m synapse_dataset_manager')
        with patch.object(sys, 'argv', ['synapse_dataset_manager.py']):
            self.assertEqual(cli.cli_invocation(), 'python synapse_dataset_manager.py')


if __name__ == '__main__':
    unittest.main()
