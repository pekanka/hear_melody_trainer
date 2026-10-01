"""Проверки ритма и гармонии для режима с двумя партиями."""

import io
import random
import unittest
import uuid
import wave
from pathlib import Path

from melody_ear_trainer import (
    CHORD_LENGTH_OPTIONS,
    make_accompanied_melody,
    make_chord_exercise,
    make_combined_wav,
)


class CombinedExerciseTests(unittest.TestCase):
    def test_strong_beats_follow_current_chord(self):
        rng = random.Random(24680)
        for mode in ("мажор", "минор"):
            for meter in (2, 3, 4):
                for chord_length in CHORD_LENGTH_OPTIONS:
                    for level in ("Легко", "Обычно", "Сложнее"):
                        with self.subTest(mode=mode, meter=meter, chord_length=chord_length, level=level):
                            chords = make_chord_exercise(7, mode, 7, chord_length, rng)
                            melody = make_accompanied_melody(7, mode, meter, 7, level, chords, rng)
                            self.assertEqual(len(melody), 7)
                            active = [chord for chord in chords for _ in range(chord.bars)]
                            for bar, chord in zip(melody, active):
                                self.assertEqual(sum(event.eighths for event in bar), meter * 2)
                                chord_pitches = {midi % 12 for midi in chord.midis}
                                elapsed = 0
                                for event in bar:
                                    if elapsed % 2 == 0:
                                        self.assertIn(event.midi % 12, chord_pitches)
                                    elapsed += event.eighths

    def test_audio_covers_both_parts_and_count_in(self):
        rng = random.Random(42)
        chords = make_chord_exercise(0, "мажор", 2, CHORD_LENGTH_OPTIONS[0], rng)
        melody = make_accompanied_melody(0, "мажор", 3, 2, "Обычно", chords, rng)
        buffer = io.BytesIO()
        make_combined_wav(buffer, melody, chords, bpm=120, numerator=3)
        buffer.seek(0)
        with wave.open(buffer, "rb") as audio:
            self.assertEqual(audio.getnchannels(), 1)
            self.assertEqual(audio.getsampwidth(), 2)
            self.assertAlmostEqual(audio.getnframes() / audio.getframerate(), 4.5, delta=0.01)
            self.assertNotEqual(audio.readframes(1000), b"\x00" * 2000)

    def test_combined_audio_can_be_saved_to_a_path(self):
        rng = random.Random(7)
        chords = make_chord_exercise(0, "мажор", 1, CHORD_LENGTH_OPTIONS[0], rng)
        melody = make_accompanied_melody(0, "мажор", 2, 1, "Легко", chords, rng)
        path = Path(__file__).parent / f"melody-ear-{uuid.uuid4().hex}.wav"
        try:
            make_combined_wav(path, melody, chords, bpm=120, numerator=2)
            with wave.open(str(path), "rb") as audio:
                self.assertGreater(audio.getnframes(), 0)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
