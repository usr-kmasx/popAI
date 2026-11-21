"""Regression checks for prompt-enhancer mode registration and request routing."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prompt_enhancer import ENHANCER_MODES, PromptEnhancer


class FakeResponse:
    status = 200

    def __iter__(self):
        yield b'data: {"choices":[{"delta":{"content":"A cinematic illustration."},"finish_reason":"stop"}]}\n'
        yield b'data: [DONE]\n'


class FakeConnection:
    requests = []

    def __init__(self, *args, **kwargs):
        self.sock = None

    def request(self, method, path, body, headers):
        self.requests.append((method, path, json.loads(body), headers))

    def getresponse(self):
        return FakeResponse()

    def close(self):
        pass


class PromptEnhancerModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.enhancer = PromptEnhancer(Path(self.temp.name))
        FakeConnection.requests.clear()

    def tearDown(self):
        self.temp.cleanup()

    def run_prompt(self, prompt, *, editing=False):
        with patch.object(self.enhancer, 'status', return_value={'state': 'ready'}):
            with patch('prompt_enhancer.http.client.HTTPConnection', FakeConnection):
                return list(self.enhancer.stream(prompt, editing=editing, mode='cinematic'))

    def test_four_modes_registered_and_menu_matches(self):
        self.assertEqual(list(ENHANCER_MODES), ['simple', 'detailed', 'creative', 'cinematic'])
        menu = (Path(__file__).resolve().parents[1] / 'web/index.html').read_text()
        for mode in ENHANCER_MODES:
            self.assertIn(f'data-mode="{mode}"', menu)
        self.assertIn('cinematic', self.enhancer.systems)
        self.assertIn('semi-realistic anime illustration', self.enhancer.systems['cinematic'])

    def test_generation_sends_cinematic_system_prompt(self):
        events = self.run_prompt('A white-haired girl looking at the sky')
        self.assertEqual(events[0], {'state': 'started'})
        self.assertEqual(events[1], {'text': 'A cinematic illustration.'})
        self.assertEqual(events[-1]['state'], 'done')
        method, path, body, _ = FakeConnection.requests[-1]
        self.assertEqual((method, path), ('POST', '/v1/chat/completions'))
        self.assertEqual(body['messages'][0]['content'], self.enhancer.systems['cinematic'])
        self.assertIn('A white-haired girl looking at the sky', body['messages'][1]['content'])
        self.assertEqual(body['messages'][1]['content'],
                         'Rewrite this image description as an English prompt:\n\nA white-haired girl looking at the sky')
        self.assertEqual(body['temperature'], ENHANCER_MODES['cinematic'][1])

    def test_reference_edit_preserves_edit_scope(self):
        self.run_prompt('Change only the background to blue', editing=True)
        message = FakeConnection.requests[-1][2]['messages'][1]['content']
        self.assertIn('Rewrite this image edit', message)
        self.assertEqual(message,
                         'Rewrite this image edit as an English instruction:\n\nChange only the background to blue')
        self.assertIn('preserve everything else', self.enhancer.systems['cinematic'])

    def test_unknown_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Cinematic Art'):
            list(self.enhancer.stream('image', mode='unknown'))


if __name__ == '__main__':
    unittest.main()
