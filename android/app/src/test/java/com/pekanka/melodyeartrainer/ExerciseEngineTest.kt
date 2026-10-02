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
    fun advancedChordsStayDiatonicAndUseControlledRegisters() {
        for (difficulty in listOf(Difficulty.NORMAL, Difficulty.HARD)) {
            val limit = if (difficulty == Difficulty.NORMAL) 12 else 18
            for (scale in Scale.chordModes) {
                for (tonic in 0..11) {
                    repeat(20) { seed ->
                        val settings = ExerciseSettings(ExerciseType.CHORDS, tonic, scale, 4, 8, 100,
                            difficulty, ChordLength.EVERY_BAR)
                        val chords = ExerciseEngine.generate(settings, Random(seed.toLong())).chords
                        assertEquals(8, chords.sumOf { it.bars })
                        assertTrue(chords.zipWithNext().all { (a, b) -> a.degree != b.degree &&
                            kotlin.math.abs(a.midis.first() - b.midis.first()) <= limit })
                        assertTrue((0 until chords.size - 3).all { index ->
                            chords[index].degree != chords[index + 2].degree ||
                                chords[index + 1].degree != chords[index + 3].degree
                        })
                        chords.forEach { chord ->
                            assertTrue(ExerciseEngine.chordQuality(chord.midis) in
                                setOf("major", "minor", "diminished"))
                            val pitches = listOf(0, 2, 4).map { step ->
                                (tonic + scale.steps[(chord.degree + step) % 7]) % 12
                            }.toSet()
                            assertEquals(pitches, chord.midis.map { it % 12 }.toSet())
                            assertEquals(chord.midis.sorted(), chord.midis)
                            assertTrue(chord.midis.first() in 40..68)
                            assertTrue(chord.midis.last() <= 79)
                            val bassDegree = (chord.degree + listOf(0, 2, 4)[chord.inversion]) % 7
                            assertEquals((tonic + scale.steps[bassDegree]) % 12, chord.midis.first() % 12)
                        }
                        if (difficulty == Difficulty.NORMAL) assertTrue(chords.all { it.inversion == 0 })
                        else assertTrue(chords.any { it.inversion != 0 })
                    }
                }
            }
        }
    }

    @Test
    fun advancedChordsCanStartAndEndOutsideTheTonic() {
        for (difficulty in listOf(Difficulty.NORMAL, Difficulty.HARD)) {
            for (scale in Scale.chordModes) {
                val exercises = (0 until 40).map { seed ->
                    val settings = ExerciseSettings(ExerciseType.CHORDS, 0, scale, 4, 8, 100,
                        difficulty, ChordLength.EVERY_BAR)
                    ExerciseEngine.generate(settings, Random(seed.toLong())).chords
                }
                assertTrue(exercises.any { it.first().degree != 0 })
                assertTrue(exercises.any { it.last().degree != 0 })
                assertTrue(exercises.any { chords -> chords.any { it.midis.first() !in 48..59 } })
            }
        }
    }

    @Test
    fun inversionAnswerNamesTheRootAndBassSeparately() {
        val settings = ExerciseSettings(ExerciseType.CHORDS, 0, Scale.MAJOR, 4, 1, 80,
            Difficulty.HARD, ChordLength.EVERY_BAR)
        val chord = ChordEvent(0, listOf(52, 55, 60), 1, 1)
        val answer = ExerciseEngine.answer(Exercise(settings, 0, chords = listOf(chord)), Notation.LATIN)
        assertTrue(answer.contains("C/E · 1-е обращение"))
        assertEquals("major", ExerciseEngine.chordQuality(chord.midis))
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
