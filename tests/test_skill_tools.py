"""Offline checks: complete installation and resumed generation isolation."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYNC = load('sync_skills', ROOT / 'scripts/sync-skills.py')
RUNNER = load('trajectory_runner', ROOT / 'skills/lifereview-trajectory-map/scripts/run_deepseek_resumable.py')


class SkillToolsTests(unittest.TestCase):
    def test_complete_install_detects_drift_and_keeps_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            workspace = base / 'workspace'
            target = workspace / 'skills/lifereview-daily-20260701'
            target.mkdir(parents=True)
            (target / 'SKILL.md').write_text('old local content')
            (target / 'stale.md').write_text('preserve in backup')
            argv = ['sync', '--workspace', str(workspace), '--apply', '--backup-dir', str(base / 'backup')]
            with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(SYNC.main(), 0)
            self.assertEqual((base / 'backup/workspace/lifereview-daily-20260701/stale.md').read_text(), 'preserve in backup')
            for source, installed in SYNC.PACKAGES.items():
                self.assertEqual(SYNC.differences(ROOT / 'skills' / source, workspace / 'skills' / installed), [])
            reference = target / 'references/analysis-contract.md'
            self.assertTrue(reference.exists())
            reference.write_text('drift')
            self.assertIn('references/analysis-contract.md', SYNC.differences(ROOT / 'skills/lifereview-daily', target))

    def test_resume_binds_input_model_and_generation_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / 'input.json'
            source.write_text('{"steps": 20}')
            argv = ['runner', '--input', str(source), '--outdir', str(base / 'out'),
                    '--model', 'test-model', '--api-root', 'https://example.invalid/v1']
            with patch.dict('os.environ', {'PROMA_API_KEY': 'synthetic-test-key'}), \
                 patch.object(sys, 'argv', argv), \
                 patch.object(RUNNER, 'request', return_value=('合成测试正文', {})) as request, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(RUNNER.main(), 0)
                self.assertEqual(RUNNER.main(), 0)
                self.assertEqual(request.call_count, 1)
                source.write_text('{"steps": 30}')
                self.assertEqual(RUNNER.main(), 0)
                self.assertEqual(request.call_count, 2)
                argv[argv.index('test-model')] = 'other-model'
                self.assertEqual(RUNNER.main(), 0)
                self.assertEqual(request.call_count, 3)
            self.assertEqual(len(list((base / 'out').iterdir())), 3)
            prompt = RUNNER.make_prompt({'steps': 20}, 6)
            self.assertNotIn('4991', prompt)
            self.assertIn('不凑下限', prompt)
            self.assertIn('整体省略', prompt)

    def test_partial_failure_is_nonzero_and_does_not_merge_stale_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / 'input.json'
            source.write_text('{}')
            argv = ['runner', '--input', str(source), '--outdir', str(base / 'out'),
                    '--model', 'test-model', '--api-root', 'https://example.invalid', '--variants', '2', '--workers', '1']
            with patch.dict('os.environ', {'PROMA_API_KEY': 'synthetic-test-key'}), \
                 patch.object(sys, 'argv', argv), \
                 patch.object(RUNNER, 'request', side_effect=[('成功正文', {}), ('', {'error': 'http_500'})]), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(RUNNER.main(), 2)
            merged = next((base / 'out').glob('*/merged.md')).read_text()
            self.assertEqual(merged.strip(), '成功正文')

    def test_truncation_is_failure(self):
        body = io.BytesIO(json.dumps({'content': [{'type': 'text', 'text': 'partial'}],
                                    'stop_reason': 'max_tokens'}).encode())
        with patch.object(RUNNER.urllib.request, 'urlopen', return_value=contextlib.closing(body)):
            text, meta = RUNNER.request('https://example.invalid/v1', 'fake', 'model', 10, '', '', 1)
        self.assertEqual(text, '')
        self.assertEqual(meta['error'], 'truncated')


if __name__ == '__main__':
    unittest.main()
