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
        self.assertIn('DRAMATIC CHARACTER WALLPAPER', self.enhancer.systems['cinematic'])
        self.assertIn('premium dark anime wallpaper style', self.enhancer.systems['cinematic'])
        self.assertIn('Dramatic</button>', menu)

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
        self.assertEqual(body['temperature'], 0.3)

    def test_thinking_tokens_remain_hidden_in_all_modes(self):
        class ThoughtResponse(FakeResponse):
            def __iter__(self):
                yield b'data: {"choices":[{"delta":{"reasoning_content":"private analysis"}}]}\n'
                yield b'data: {"choices":[{"delta":{"content":"Final visible prompt."},"finish_reason":"stop"}]}\n'
                yield b'data: [DONE]\n'

        class ThoughtConnection(FakeConnection):
            def getresponse(self):
                return ThoughtResponse()

        with patch.object(self.enhancer, 'status', return_value={'state': 'ready'}):
            with patch('prompt_enhancer.http.client.HTTPConnection', ThoughtConnection):
                for mode in ENHANCER_MODES:
                    events = list(self.enhancer.stream('A person beside a car.', mode=mode))
                    self.assertEqual([event['text'] for event in events if 'text' in event],
                                     ['Final visible prompt.'])
                    self.assertEqual(events[-1]['state'], 'done')

    def test_reference_edit_preserves_edit_scope(self):
        self.run_prompt('Change only the background to blue', editing=True)
        message = FakeConnection.requests[-1][2]['messages'][1]['content']
        self.assertIn('Rewrite this image edit', message)
        self.assertEqual(message,
                         'Rewrite this image edit as an English instruction:\n\nChange only the background to blue')
        self.assertIn('everything else stays unchanged', self.enhancer.systems['cinematic'])

    def test_on_demand_load_and_unload(self):
        class OwnedProcess:
            def poll(self):
                return None

        process = OwnedProcess()
        def launch():
            self.enhancer.process = process
            self.enhancer.state = 'ready'

        self.assertEqual(self.enhancer.state, 'stopped')
        self.assertIsNone(self.enhancer.process)
        with patch.object(self.enhancer, 'start', side_effect=launch) as start:
            with patch('prompt_enhancer.terminate') as terminate:
                with patch('prompt_enhancer.http.client.HTTPConnection', FakeConnection):
                    result = list(self.enhancer.stream('A purple fox.', mode='cinematic'))
        start.assert_called_once()
        terminate.assert_any_call(process)
        self.assertEqual(result[-1]['state'], 'done')
        self.assertEqual(self.enhancer.state, 'stopped')
        self.assertIsNone(self.enhancer.process)
        self.assertFalse(self.enhancer.busy)

    def test_disconnect_and_cancel_release_process(self):
        class OwnedProcess:
            def poll(self):
                return None

        for cancel in (False, True):
            process = OwnedProcess()
            def launch():
                self.enhancer.process = process
                self.enhancer.state = 'ready'
            with patch.object(self.enhancer, 'start', side_effect=launch):
                with patch('prompt_enhancer.terminate') as terminate:
                    with patch('prompt_enhancer.http.client.HTTPConnection', FakeConnection):
                        iterator = self.enhancer.stream('Blue cat.', mode='cinematic')
                        self.assertEqual(next(iterator), {'state': 'started'})
                        self.assertIn('text', next(iterator))
                        if cancel:
                            self.enhancer.cancel_current()
                        iterator.close()
            terminate.assert_any_call(process)
            self.assertIsNone(self.enhancer.process)
            self.assertEqual(self.enhancer.state, 'stopped')
            self.assertFalse(self.enhancer.busy)

    def test_cancel_while_loading_stops_owned_process(self):
        from threading import Event, Thread

        class OwnedProcess:
            def poll(self):
                return None

        process = OwnedProcess()
        loading = Event()
        result = []
        def launch():
            self.enhancer.process = process
            self.enhancer.state = 'loading'
            loading.set()
        def run():
            try:
                result.extend(self.enhancer.stream('A blue cat.', mode='cinematic'))
            except RuntimeError as exc:
                result.append(str(exc))

        with patch.object(self.enhancer, 'start', side_effect=launch):
            with patch('prompt_enhancer.terminate') as terminate:
                thread = Thread(target=run)
                thread.start()
                self.assertTrue(loading.wait(2))
                self.enhancer.cancel_current()
                thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(any('canceled' in str(item) for item in result))
        terminate.assert_any_call(process)
        self.assertEqual(self.enhancer.state, 'stopped')
        self.assertIsNone(self.enhancer.process)
        self.assertFalse(self.enhancer.busy)

    def test_vulkan_backend_configured(self):
        root = Path(__file__).resolve().parents[1]
        settings = json.loads((root / 'prompt-enhancer.json').read_text())
        self.assertEqual(settings['backend']['gpu_backend'], 'vulkan')
        self.assertEqual(settings['runtime']['load_policy'], 'per_request')
        self.assertEqual(settings['runtime']['gpu_layers'], 999)
        self.assertEqual(settings['runtime']['reasoning'], 'on')
        self.assertEqual(settings['runtime']['reasoning_budget'], 192)
        self.assertEqual(settings['runtime']['reasoning_format'], 'deepseek')
        self.assertEqual(self.enhancer.binary.name, 'llama-server')
        self.assertEqual(self.enhancer.binary.parent.name, 'llama-vulkan')

    def test_unknown_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Dramatic'):
            list(self.enhancer.stream('image', mode='unknown'))


if __name__ == '__main__':
    unittest.main()
