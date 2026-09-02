import sys
import unittest
from unittest.mock import patch, MagicMock

# Mock faster_whisper before importing the module
mock_fw = MagicMock()
sys.modules["faster_whisper"] = mock_fw

from whisper.transcriber import get_model, convert_to_wav, transcribe_audio, _model


class TestWhisperTranscriber(unittest.TestCase):
    def test_get_model_singleton(self):
        mock_fw.WhisperModel.reset_mock()
        m1 = get_model()
        m2 = get_model()
        self.assertIs(m1, m2)

    @patch("subprocess.Popen")
    def test_convert_to_wav_success(self, mock_popen):
        process_mock = MagicMock()
        process_mock.communicate.return_value = (b"RIFF_WAV_BYTES", b"")
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        wav = convert_to_wav(b"OGG_BYTES")
        self.assertEqual(wav, b"RIFF_WAV_BYTES")
        mock_popen.assert_called_once()

    @patch("subprocess.Popen")
    def test_convert_to_wav_failure(self, mock_popen):
        process_mock = MagicMock()
        process_mock.communicate.return_value = (b"", b"Invalid audio stream")
        process_mock.returncode = 1
        mock_popen.return_value = process_mock

        with self.assertRaises(RuntimeError) as ctx:
            convert_to_wav(b"CORRUPTED_BYTES")
        self.assertIn("Invalid audio stream", str(ctx.exception))

    @patch("whisper.transcriber.convert_to_wav")
    @patch("whisper.transcriber.get_model")
    def test_transcribe_audio_success(self, mock_get_model, mock_convert):
        mock_convert.return_value = b"RIFF_WAV"
        model_instance = MagicMock()
        seg1 = MagicMock()
        seg1.text = "Hola "
        seg2 = MagicMock()
        seg2.text = "Otto"
        model_instance.transcribe.return_value = ([seg1, seg2], None)
        mock_get_model.return_value = model_instance

        text = transcribe_audio(b"AUDIO_INPUT")
        self.assertEqual(text, "Hola Otto")


if __name__ == "__main__":
    unittest.main()
