"""Проверки музыкальных ограничений уровней подбора аккордов."""

import random
import unittest

from melody_ear_trainer import (
    CHORD_LENGTH_OPTIONS,
    NOTATION_OPTIONS,
    SCALES,
    chord_name,
    chord_quality,
    make_chord_exercise,
)


class ChordDifficultyTests(unittest.TestCase):
    def test_easy_keeps_the_original_root_position_pattern(self):
        for mode in ("мажор", "минор"):
            for length in CHORD_LENGTH_OPTIONS:
                for bars in range(1, 17):
                    chords = make_chord_exercise(7, mode, bars, length, random.Random(20))
                    self.assertEqual(sum(chord.bars for chord in chords), bars)
                    self.assertEqual(chords[0].degree, 0)
                    if len(chords) > 2:
                        self.assertEqual(chords[-1].degree, 0)
                    self.assertTrue(all(chord.inversion == 0 for chord in chords))
                    self.assertTrue(all(chord.midis[0] == 55 + SCALES[mode][chord.degree]
                                        for chord in chords))

    def test_advanced_chords_are_diatonic_triads_with_bounded_bass_motion(self):
        for level, limit in (("Обычно", 12), ("Сложнее", 18)):
            for mode in ("мажор", "минор"):
                for tonic in range(12):
                    for seed in range(20):
                        chords = make_chord_exercise(
                            tonic, mode, 8, CHORD_LENGTH_OPTIONS[0], random.Random(seed), level
                        )
                        self.assertEqual(sum(chord.bars for chord in chords), 8)
                        self.assertTrue(all(a.degree != b.degree for a, b in zip(chords, chords[1:])))
                        self.assertTrue(all(chords[i].degree != chords[i + 2].degree
                                            or chords[i + 1].degree != chords[i + 3].degree
                                            for i in range(len(chords) - 3)))
                        for chord in chords:
                            self.assertIn(chord_quality(chord.midis),
                                          ("major", "minor", "diminished"))
                            expected = {(tonic + SCALES[mode][(chord.degree + step) % 7]) % 12
                                        for step in (0, 2, 4)}
                            self.assertEqual({midi % 12 for midi in chord.midis}, expected)
                            self.assertEqual(chord.midis, tuple(sorted(chord.midis)))
                            self.assertTrue(40 <= chord.midis[0] <= 68)
                            self.assertLessEqual(chord.midis[-1], 79)
                            expected_bass = (tonic + SCALES[mode][
                                (chord.degree + (0, 2, 4)[chord.inversion]) % 7]) % 12
                            self.assertEqual(chord.midis[0] % 12, expected_bass)
                        self.assertTrue(all(abs(a.midis[0] - b.midis[0]) <= limit
                                            for a, b in zip(chords, chords[1:])))
                        if level == "Обычно":
                            self.assertTrue(all(chord.inversion == 0 for chord in chords))
                        else:
                            self.assertTrue(any(chord.inversion != 0 for chord in chords))

    def test_advanced_progressions_can_start_and_end_away_from_tonic(self):
        for level in ("Обычно", "Сложнее"):
            for mode in ("мажор", "минор"):
                exercises = [make_chord_exercise(
                    0, mode, 8, CHORD_LENGTH_OPTIONS[0], random.Random(seed), level
                ) for seed in range(40)]
                self.assertTrue(any(chords[0].degree != 0 for chords in exercises))
                self.assertTrue(any(chords[-1].degree != 0 for chords in exercises))
                self.assertTrue(any(any(chord.midis[0] < 48 or chord.midis[0] >= 60
                                        for chord in chords) for chords in exercises))

    def test_inversion_names_keep_the_chord_root_and_show_the_bass(self):
        from melody_ear_trainer import ChordEvent

        chord = ChordEvent(0, (52, 55, 60), 1, 1)
        self.assertEqual(chord_name(chord, NOTATION_OPTIONS[1]), "C/E")
        self.assertEqual(chord_name(chord, NOTATION_OPTIONS[0]), "До маж./Ми")
        self.assertEqual(chord_quality(chord.midis), "major")


if __name__ == "__main__":
    unittest.main()
