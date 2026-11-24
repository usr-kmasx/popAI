"""Regression checks for prompt-enhancer mode registration and request routing."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prompt_enhancer import CORRECTOR_TEMPERATURE, ENHANCER_MODES, PromptEnhancer


class FakeResponse:
    status = 200

    def __init__(self, text='A cinematic illustration.', *, finish='stop', done=True,
                 reasoning=None):
        self.text = text
        self.finish = finish
        self.done = done
        self.reasoning = reasoning

    def __iter__(self):
        if self.reasoning:
            yield self.event({'reasoning_content': self.reasoning})
        if self.text:
            for part in (self.text[:len(self.text)//2], self.text[len(self.text)//2:]):
                yield self.event({'content': part})
        yield self.event({}, self.finish)
        if self.done:
            yield b'data: [DONE]\n'

    @staticmethod
    def event(delta, finish=None):
        data = {'choices': [{'delta': delta, 'finish_reason': finish}]}
        return ('data: ' + json.dumps(data) + '\n').encode()


class FakeConnection:
    requests = []
    responses = []
    corrected = 'A corrected English description.'

    def __init__(self, *args, **kwargs):
        self.sock = None

    def request(self, method, path, body, headers):
        self.body = json.loads(body)
        self.requests.append((method, path, self.body, headers))

    def getresponse(self):
        if self.responses:
            return self.responses.pop(0)
        system = self.body['messages'][0]['content']
        if 'private prompt corrector' in system:
            return FakeResponse(self.corrected)
        return FakeResponse()

    def close(self):
        pass


class PromptEnhancerModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.enhancer = PromptEnhancer(Path(self.temp.name))
        FakeConnection.requests.clear()
        FakeConnection.responses.clear()

    def tearDown(self):
        self.temp.cleanup()

    def run_prompt(self, prompt, *, editing=False, mode='cinematic'):
        with patch.object(self.enhancer, 'status', return_value={'state': 'ready'}):
            with patch('prompt_enhancer.http.client.HTTPConnection', FakeConnection):
                return list(self.enhancer.stream(prompt, editing=editing, mode=mode))

    def test_four_modes_registered_and_menu_matches(self):
        self.assertEqual(list(ENHANCER_MODES), ['simple', 'detailed', 'creative', 'cinematic'])
        menu = (Path(__file__).resolve().parents[1] / 'web/index.html').read_text()
        for mode in ENHANCER_MODES:
            self.assertIn(f'data-mode="{mode}"', menu)
        self.assertIn('cinematic', self.enhancer.systems)
        self.assertIn('DRAMATIC CHARACTER WALLPAPER', self.enhancer.systems['cinematic'])
        self.assertIn('premium dark anime wallpaper style', self.enhancer.systems['cinematic'])
        self.assertIn('Dramatic</button>', menu)

    def test_all_four_modes_receive_only_corrected_en_us(self):
        original = 'um homem agachado ao lado do carro, farol esquerdo apagado'
        corrected = 'A man crouches beside the car with its left headlight off.'
        for mode, (_, temperature, _) in ENHANCER_MODES.items():
            with self.subTest(mode=mode):
                FakeConnection.requests.clear()
                FakeConnection.responses[:] = [
                    FakeResponse(corrected, reasoning='hidden corrector thinking'),
                    FakeResponse('A finished visual prompt.', reasoning='hidden enhancer thinking'),
                ]
                events = self.run_prompt(original, mode=mode)
                self.assertEqual(events[0], {'state': 'started'})
                self.assertEqual([event['text'] for event in events if 'text' in event],
                                 ['A finished visual prompt.'])
                self.assertEqual(events[-1]['state'], 'done')
                self.assertEqual(len(FakeConnection.requests), 2)
                for method, path, body, headers in FakeConnection.requests:
                    self.assertEqual((method, path), ('POST', '/v1/chat/completions'))
                    self.assertEqual([m['role'] for m in body['messages']], ['system', 'user'])
                    self.assertFalse(body['cache_prompt'])
                    self.assertTrue(body['stream'])
                    self.assertEqual(headers['Authorization'], 'Bearer ' + self.enhancer.token)
                first, second = [r[2] for r in FakeConnection.requests]
                self.assertEqual(first['messages'][0]['content'], self.enhancer.corrector_system)
                self.assertIn('en-US', first['messages'][1]['content'])
                self.assertIn(original, first['messages'][1]['content'])
                self.assertEqual(first['temperature'], CORRECTOR_TEMPERATURE)
                self.assertEqual(first['reasoning_budget_tokens'], 1024)
                self.assertEqual(second['reasoning_budget_tokens'], 1024)
                self.assertEqual(second['messages'][0]['content'], self.enhancer.systems[mode])
                self.assertIn(corrected, second['messages'][1]['content'])
                self.assertNotIn(original, second['messages'][1]['content'])
                self.assertEqual(second['temperature'], temperature)
                self.assertEqual([e['stage'] for e in events if 'stage' in e], ['corrector', 'enhancer'])
                self.assertEqual(''.join(e.get('answer','') for e in events if e.get('phase')=='corrector'), corrected)
                self.assertEqual(''.join(e.get('answer','') for e in events if e.get('phase')=='enhancer'), 'A finished visual prompt.')
                self.assertEqual([e['thought'] for e in events if 'thought' in e], ['hidden corrector thinking','hidden enhancer thinking'])

    def test_corrector_rules_preserve_intent_and_literal_image_text(self):
        rules = self.enhancer.corrector_system
        for phrase in ('American English (en-US)', 'Do not embellish',
                       'left from right', 'everything else remains unchanged',
                       'do not translate that literal image text',
                       'No headings, bullets'):
            self.assertIn(phrase, rules)

    def test_reference_edit_preserves_edit_scope(self):
        original = 'muda só o fundo pra azul'
        corrected = 'Change only the background to blue; everything else remains unchanged.'
        FakeConnection.responses[:] = [FakeResponse(corrected), FakeResponse()]
        self.run_prompt(original, editing=True)
        first, second = [r[2]['messages'][1]['content'] for r in FakeConnection.requests]
        self.assertEqual(first,
                         'Interpret, correct, and translate this reference-image edit into en-US:\n\n' + original)
        self.assertEqual(second, 'Rewrite this image edit as an English instruction:\n\n' + corrected)
        self.assertIn('everything else stays unchanged', self.enhancer.systems['cinematic'])

    def test_failed_corrector_never_calls_enhancer(self):
        for bad in (FakeResponse('   '), FakeResponse('Partial.', done=False),
                    FakeResponse('Truncated.', finish='length'), FakeResponse('Partial.', finish='error')):
            with self.subTest(bad=bad):
                FakeConnection.requests.clear()
                FakeConnection.responses[:] = [bad]
                with patch.object(self.enhancer, 'status', return_value={'state': 'ready'}):
                    with patch('prompt_enhancer.http.client.HTTPConnection', FakeConnection):
                        events = []
                        with self.assertRaises(RuntimeError):
                            for event in self.enhancer.stream('Raw description.', mode='creative'):
                                events.append(event)
                self.assertEqual(len(FakeConnection.requests), 1)
                self.assertFalse(any('text' in event or event.get('state') == 'done' for event in events))
                self.assertFalse(self.enhancer.busy)

    def test_failed_enhancer_never_publishes_corrected_or_partial_prompt(self):
        FakeConnection.responses[:] = [
            FakeResponse('Corrected but private.'), FakeResponse('Unfinished final.', done=False),
        ]
        with patch.object(self.enhancer, 'status', return_value={'state': 'ready'}):
            with patch('prompt_enhancer.http.client.HTTPConnection', FakeConnection):
                events = []
                with self.assertRaises(RuntimeError):
                    for event in self.enhancer.stream('Original.', mode='simple'):
                        events.append(event)
        self.assertEqual(len(FakeConnection.requests), 2)
        self.assertFalse(any('text' in event or event.get('state') == 'done' for event in events))
        self.assertFalse(self.enhancer.busy)

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
        terminate.assert_called_once_with(process)
        self.assertEqual(len(FakeConnection.requests), 2)
        self.assertEqual(result[-1]['state'], 'done')
        self.assertEqual(self.enhancer.state, 'stopped')
        self.assertIsNone(self.enhancer.process)
        self.assertFalse(self.enhancer.busy)

    def test_disconnect_and_cancel_between_stages_release_process(self):
        class OwnedProcess:
            def poll(self):
                return None

        for cancel in (False, True):
            FakeConnection.requests.clear()
            process = OwnedProcess()
            def launch():
                self.enhancer.process = process
                self.enhancer.state = 'ready'
            with patch.object(self.enhancer, 'start', side_effect=launch):
                with patch('prompt_enhancer.terminate') as terminate:
                    with patch('prompt_enhancer.http.client.HTTPConnection', FakeConnection):
                        iterator = self.enhancer.stream('Blue cat.', mode='cinematic')
                        self.assertEqual(next(iterator), {'state': 'started'})
                        self.assertEqual(next(iterator), {'stage': 'corrector'})
                        for event in iterator:
                            if event == {'state': 'working'}: break
                        self.assertEqual(event, {'state': 'working'})
                        self.assertEqual(len(FakeConnection.requests), 1)
                        self.assertIs(self.enhancer.process, process)
                        if cancel:
                            self.enhancer.cancel_current()
                            with self.assertRaisesRegex(RuntimeError, 'canceled'):
                                next(iterator)
                        else:
                            iterator.close()
            terminate.assert_called_once_with(process)
            self.assertEqual(len(FakeConnection.requests), 1)
            self.assertIsNone(self.enhancer.process)
            self.assertEqual(self.enhancer.state, 'stopped')
            self.assertFalse(self.enhancer.busy)

    def test_cancel_during_each_private_completion(self):
        for canceled_stage in (1, 2):
            FakeConnection.requests.clear()
            enhancer = self.enhancer
            class CancelResponse(FakeResponse):
                def __iter__(self):
                    yield self.event({'reasoning_content': 'hidden thought'})
                    enhancer.cancel_current()
                    yield self.event({'content': 'Do not publish.'}, 'stop')
                    yield b'data: [DONE]\n'
            FakeConnection.responses[:] = (
                [CancelResponse()] if canceled_stage == 1 else
                [FakeResponse('Corrected English.'), CancelResponse()]
            )
            with patch.object(enhancer, 'status', return_value={'state': 'ready'}):
                with patch('prompt_enhancer.http.client.HTTPConnection', FakeConnection):
                    events = []
                    with self.assertRaisesRegex(RuntimeError, 'canceled'):
                        for event in enhancer.stream('Raw input.', mode='simple'):
                            events.append(event)
            self.assertEqual(len(FakeConnection.requests), canceled_stage)
            self.assertFalse(any('text' in event or event.get('state') == 'done' for event in events))
            self.assertFalse(enhancer.busy)

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
        self.assertEqual(settings['runtime']['reasoning_budget'], 1024)
        self.assertEqual(settings['runtime']['corrector_reasoning_budget'], 1024)
        self.assertEqual(settings['runtime']['reasoning_format'], 'deepseek')
        self.assertEqual(self.enhancer.binary.name, 'llama-server')
        self.assertEqual(self.enhancer.binary.parent.name, 'llama-vulkan')

    def test_unknown_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Dramatic'):
            list(self.enhancer.stream('image', mode='unknown'))


    def test_independent_stages_and_lite_mode(self):
        for lite in (False, True):
            for corrector, enhancer in ((True,True),(True,False),(False,True)):
                with self.subTest(lite=lite,corrector=corrector,enhancer=enhancer):
                    self.enhancer.options = dict(corrector=corrector,enhancer=enhancer,lite=lite)
                    FakeConnection.requests.clear()
                    events = self.run_prompt('Original input.',mode='cinematic' if enhancer else 'corrector')
                    expected = (['corrector'] if corrector else []) + (['enhancer'] if enhancer else [])
                    self.assertEqual([e['stage'] for e in events if 'stage' in e],expected)
                    self.assertEqual(len(FakeConnection.requests),len(expected))
                    self.assertEqual(self.enhancer.context_size,4096 if lite else 8192)
                    self.assertEqual([r[2]['reasoning_budget_tokens'] for r in FakeConnection.requests],
                        ([512 if lite else 1024] if corrector else [])+([192 if lite else 1024] if enhancer else []))
                    if enhancer and not corrector:
                        self.assertIn('Original input.',FakeConnection.requests[0][2]['messages'][1]['content'])
                    self.assertEqual([e['text'] for e in events if 'text' in e],
                        ['A cinematic illustration.' if enhancer else FakeConnection.corrected])
        self.enhancer.options = dict(corrector=True,enhancer=False,lite=False)
        for mode in ENHANCER_MODES:
            FakeConnection.requests.clear()
            with patch.object(self.enhancer,'start') as start:
                with self.assertRaisesRegex(ValueError,'Enhancer is disabled'):
                    list(self.enhancer.stream('Original input.',mode=mode))
            start.assert_not_called()
            self.assertFalse(FakeConnection.requests)
        self.enhancer.options = dict(corrector=False,enhancer=False,lite=True)
        FakeConnection.requests.clear()
        with patch.object(self.enhancer,'start') as start:
            with self.assertRaisesRegex(ValueError,'Enable Corrector or Enhancer'):
                list(self.enhancer.stream('Original input.'))
        start.assert_not_called()
        self.assertFalse(FakeConnection.requests)
        self.assertFalse(self.enhancer.busy)

if __name__ == '__main__':
    unittest.main()
