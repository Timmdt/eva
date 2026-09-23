from __future__ import annotations

import subprocess
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

from interfaces.voice import TextToSpeech, VoiceConfig, prepare_spoken_text


class VoiceTest(unittest.TestCase):
    def test_prepare_spoken_text_removes_markdown_urls_and_code(self):
        fence = chr(96) * 3
        text = (
            "## Titel\n"
            "[Dokument](https://example.test) und "
            + chr(96) + "Wert" + chr(96) + ".\n"
            f"{fence}python\nprint('x')\n{fence}"
        )
        spoken = prepare_spoken_text(text)
        self.assertEqual(
            spoken,
            "Titel Dokument und Wert. Codebeispiel im Terminal.",
        )

    def test_disabled_voice_does_not_start_a_process(self):
        runner = Mock()
        voice = TextToSpeech(VoiceConfig(enabled=False), runner=runner)
        self.assertFalse(voice.speak("Hallo"))
        runner.assert_not_called()

    def test_piper_synthesizes_and_plays_without_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory, "voice.onnx")
            model.touch()
            model.with_suffix(".onnx.json").touch()
            calls: list[list[str]] = []

            def runner(command, **_kwargs):
                calls.append(command)
                if "piper" in command:
                    Path(command[command.index("-f") + 1]).touch()
                return subprocess.CompletedProcess(command, 0, "", "")

            voice = TextToSpeech(
                VoiceConfig(enabled=True, model=model, pitch=1.0),
                runner=runner,
                which=lambda name: f"/usr/bin/{name}",
                python_executable="/venv/python",
            )

            self.assertTrue(voice.speak("Hallo, Tim."))
            self.assertEqual(calls[0][:3], ["/venv/python", "-m", "piper"])
            self.assertIn("--length-scale", calls[0])
            self.assertEqual(calls[1][0], "/usr/bin/aplay")

    def test_chatterbox_synthesizes_without_audio_player(self):
        with tempfile.TemporaryDirectory() as directory:
            chatterbox_python = Path(directory, "python")
            chatterbox_python.touch()
            saved_output = Path(directory, "result.wav")
            calls: list[list[str]] = []

            def runner(command, **_kwargs):
                calls.append(command)
                output = Path(command[command.index("--output") + 1])
                with wave.open(str(output), "wb") as target:
                    target.setnchannels(1)
                    target.setsampwidth(2)
                    target.setframerate(24_000)
                    target.writeframes(b"\x00\x00" * 160)
                return subprocess.CompletedProcess(command, 0, "", "")

            voice = TextToSpeech(
                VoiceConfig(
                    enabled=True,
                    engine="chatterbox",
                    chatterbox_python=chatterbox_python,
                    output_file=saved_output,
                ),
                runner=runner,
            )

            self.assertTrue(voice.speak("Hallo, Tim."))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], str(chatterbox_python))
            self.assertIn("tools/chatterbox_synthesize.py", calls[0][1])
            self.assertIn("--model-version", calls[0])
            self.assertNotIn("--reference", calls[0])
            self.assertTrue(saved_output.is_file())

    def test_qwen_synthesizes_with_fixed_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            qwen_python = Path(directory, "python")
            qwen_python.touch()
            reference = Path(directory, "reference.wav")
            reference.touch()
            reference_text = Path(directory, "reference.txt")
            reference_text.write_text("Good morning, Tim.", encoding="utf-8")
            saved_output = Path(directory, "result.wav")
            calls: list[list[str]] = []

            def runner(command, **_kwargs):
                calls.append(command)
                output = Path(command[command.index("--output") + 1])
                with wave.open(str(output), "wb") as target:
                    target.setnchannels(1)
                    target.setsampwidth(2)
                    target.setframerate(24_000)
                    target.writeframes(b"\x00\x00" * 160)
                return subprocess.CompletedProcess(command, 0, "", "")

            voice = TextToSpeech(
                VoiceConfig(
                    enabled=True,
                    engine="qwen",
                    qwen_python=qwen_python,
                    reference_audio=reference,
                    qwen_reference_text=reference_text,
                    qwen_release_ollama=False,
                    output_file=saved_output,
                ),
                runner=runner,
            )

            self.assertTrue(voice.speak("Hallo, Tim."))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], str(qwen_python))
            self.assertIn("tools/qwen_clone_synthesize.py", calls[0][1])
            self.assertIn("--reference", calls[0])
            self.assertIn("--reference-text-file", calls[0])
            self.assertTrue(saved_output.is_file())

    def test_pitch_adjustment_updates_wav_sample_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            audio_file = Path(directory, "voice.wav")
            with wave.open(str(audio_file), "wb") as target:
                target.setnchannels(1)
                target.setsampwidth(2)
                target.setframerate(16_000)
                target.writeframes(b"\x00\x00" * 160)

            voice = TextToSpeech(VoiceConfig(enabled=True, pitch=1.06))

            self.assertTrue(voice._adjust_wav_pitch(audio_file))
            with wave.open(str(audio_file), "rb") as adjusted:
                self.assertEqual(adjusted.getframerate(), 16_960)
                self.assertEqual(adjusted.getnframes(), 160)

    def test_mp3_output_is_encoded_locally(self):
        with tempfile.TemporaryDirectory() as directory:
            audio_file = Path(directory, "voice.wav")
            output_file = Path(directory, "voice.mp3")
            with wave.open(str(audio_file), "wb") as target:
                target.setnchannels(1)
                target.setsampwidth(2)
                target.setframerate(16_000)
                target.writeframes(b"\x00\x00" * 160)

            encoder = Mock()
            encoder.encode.return_value = b"mp3"
            encoder.flush.return_value = b"-data"
            lameenc = types.SimpleNamespace(Encoder=lambda: encoder)
            voice = TextToSpeech(
                VoiceConfig(enabled=True, output_file=output_file),
            )

            with patch.dict("sys.modules", {"lameenc": lameenc}):
                self.assertTrue(voice._save_output(audio_file))
            self.assertEqual(output_file.read_bytes(), b"mp3-data")

    def test_eva_speak_can_skip_duplicate_terminal_echo(self):
        from core.eva import EVA

        eva = EVA.__new__(EVA)
        eva.name = "EVA"
        eva.voice = Mock()
        with patch("builtins.print") as output:
            eva.speak("Antwort", echo=False)
        output.assert_not_called()
        eva.voice.speak.assert_called_once_with("Antwort")


if __name__ == "__main__":
    unittest.main()
