package com.pekanka.melodyeartrainer

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Random

class ExerciseEngineTest {
    @Test
    fun melodyFillsEveryBarInEveryScaleAndMeter() {
        val random = Random(12345)
        for (scale in Scale.entries) {
            for (meter in 2..4) {
                for (difficulty in Difficulty.entries) {
                    repeat(20) {
                        val settings = ExerciseSettings(ExerciseType.MELODY, null, scale, meter, 5, 87,
                            difficulty, ChordLength.EVERY_BAR)
                        val exercise = ExerciseEngine.generate(settings, random)
                        assertEquals(5, exercise.melody.size)
                        assertTrue(exercise.melody.all { bar -> bar.sumOf { it.eighths } == meter * 2 })
                        assertTrue(exercise.melody.flatten().all { event ->
                            (event.midi - exercise.tonic).mod(12) in scale.steps
                        })
                    }
                }
            }
        }
    }

    @Test
    fun chordsUseOnlyDiatonicTriadsAndCoverTheRequestedBars() {
        val random = Random(67890)
        for (scale in Scale.chordModes) {
            for (length in ChordLength.entries) {
                for (bars in 1..16) {
                    val settings = ExerciseSettings(ExerciseType.CHORDS, 7, scale, 4, bars, 100,
                        Difficulty.EASY, length)
                    val chords = ExerciseEngine.generate(settings, random).chords
                    assertEquals(bars, chords.sumOf { it.bars })
                    assertEquals(0, chords.first().degree)
                    if (chords.size > 2) assertEquals(0, chords.last().degree)
                    assertTrue(chords.all { it.bars in 1..2 })
                    assertTrue(chords.all { ExerciseEngine.chordQuality(it.midis) in
                        setOf("major", "minor", "diminished") })
                }
            }
        }
    }

    @Test
    fun answerCanSwitchNotationWithoutChangingExercise() {
        val settings = ExerciseSettings(ExerciseType.CHORDS, 0, Scale.MAJOR, 4, 4, 80,
            Difficulty.EASY, ChordLength.EVERY_BAR)
        val exercise = ExerciseEngine.generate(settings, Random(1))
        val latin = ExerciseEngine.answer(exercise, Notation.LATIN)
        val russian = ExerciseEngine.answer(exercise, Notation.RUSSIAN)
        assertTrue(latin.contains("Тональность: C мажор"))
        assertTrue(russian.contains("Тональность: До мажор"))
        assertFalse(latin == russian)
    }

    @Test
    fun allExerciseTypesProduceAudibleSamplesWithCountIn() {
        for (type in ExerciseType.entries) {
            val settings = ExerciseSettings(type, 0, Scale.MAJOR, 3, 2, 120,
                Difficulty.EASY, ChordLength.EVERY_BAR)
            val samples = AudioEngine.render(ExerciseEngine.generate(settings, Random(12)))
            val expectedSeconds = (settings.bars + 1) * settings.meter * 60.0 / settings.bpm
            assertTrue(samples.size > (expectedSeconds * AudioEngine.SAMPLE_RATE * 0.99).toInt())
            assertTrue(samples.any { it.toInt() != 0 })
        }
    }

    @Test
    fun combinedModeAlignsMelodyWithEveryActiveChord() {
        val random = Random(24680)
        for (scale in Scale.chordModes) {
            for (meter in 2..4) {
                for (length in ChordLength.entries) {
                    for (difficulty in Difficulty.entries) {
                        repeat(12) {
                            val settings = ExerciseSettings(ExerciseType.BOTH, null, scale, meter, 7, 92,
                                difficulty, length)
                            val exercise = ExerciseEngine.generate(settings, random)
                            assertEquals(7, exercise.melody.size)
                            assertEquals(7, exercise.chords.sumOf { chord -> chord.bars })
                            val activeChords = exercise.chords.flatMap { chord -> List(chord.bars) { chord } }
                            exercise.melody.forEachIndexed { barIndex, bar ->
                                assertEquals(meter * 2, bar.sumOf { note -> note.eighths })
                                val chordPitches = activeChords[barIndex].midis.map { it % 12 }.toSet()
                                var elapsed = 0
                                bar.forEach { note ->
                                    if (elapsed % 2 == 0) assertTrue(note.midi % 12 in chordPitches)
                                    elapsed += note.eighths
                                }
                            }
                            val answer = ExerciseEngine.answer(exercise, Notation.LATIN)
                            assertTrue(answer.contains("Аккорды:"))
                            assertTrue(answer.contains("Мелодия:"))
                        }
                    }
                }
            }
        }
    }

    @Test
    fun combinedAudioContainsBothParts() {
        val settings = ExerciseSettings(ExerciseType.BOTH, 0, Scale.MAJOR, 4, 4, 100,
            Difficulty.NORMAL, ChordLength.TWO_BARS)
        val exercise = ExerciseEngine.generate(settings, Random(42))
        val mixed = AudioEngine.render(exercise)
        val melodyOnly = AudioEngine.render(exercise.copy(settings = settings.copy(type = ExerciseType.MELODY)))
        val chordsOnly = AudioEngine.render(exercise.copy(settings = settings.copy(type = ExerciseType.CHORDS)))
        assertFalse(mixed.contentEquals(melodyOnly))
        assertFalse(mixed.contentEquals(chordsOnly))
    }
}
