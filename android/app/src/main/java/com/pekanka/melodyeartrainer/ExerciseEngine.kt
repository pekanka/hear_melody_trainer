package com.pekanka.melodyeartrainer

import java.util.Random
import kotlin.math.abs

enum class ExerciseType(val label: String) { MELODY("Мелодия"), CHORDS("Аккорды") }
enum class Notation(val label: String) { LATIN("C–D–E"), RUSSIAN("До–Ре–Ми") }
enum class Difficulty(val label: String) { EASY("Легко"), NORMAL("Обычно"), HARD("Сложнее") }
enum class ChordLength(val label: String) {
    EVERY_BAR("Каждый такт"), TWO_BARS("Каждые 2 такта"), RANDOM("Случайно: 1–2 такта")
}

enum class Scale(val label: String, val steps: IntArray) {
    MAJOR("мажор", intArrayOf(0, 2, 4, 5, 7, 9, 11)),
    DORIAN("дорийский", intArrayOf(0, 2, 3, 5, 7, 9, 10)),
    PHRYGIAN("фригийский", intArrayOf(0, 1, 3, 5, 7, 8, 10)),
    LYDIAN("лидийский", intArrayOf(0, 2, 4, 6, 7, 9, 11)),
    MIXOLYDIAN("миксолидийский", intArrayOf(0, 2, 4, 5, 7, 9, 10)),
    MINOR("минор", intArrayOf(0, 2, 3, 5, 7, 8, 10)),
    LOCRIAN("локрийский", intArrayOf(0, 1, 3, 5, 6, 8, 10));

    companion object {
        val chordModes = listOf(MAJOR, MINOR)
    }
}

data class ExerciseSettings(
    val type: ExerciseType,
    val tonic: Int?, // null = случайная тоника
    val scale: Scale,
    val meter: Int,
    val bars: Int,
    val bpm: Int,
    val difficulty: Difficulty,
    val chordLength: ChordLength,
)

data class NoteEvent(val midi: Int, val eighths: Int)
data class ChordEvent(val degree: Int, val midis: List<Int>, val bars: Int)

data class Exercise(
    val settings: ExerciseSettings,
    val tonic: Int,
    val melody: List<List<NoteEvent>> = emptyList(),
    val chords: List<ChordEvent> = emptyList(),
)

object ExerciseEngine {
    val latinNotes = listOf("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
    val russianNotes = listOf("До", "До♯", "Ре", "Ре♯", "Ми", "Фа", "Фа♯", "Соль", "Соль♯", "Ля", "Ля♯", "Си")

    fun generate(settings: ExerciseSettings, random: Random = Random()): Exercise {
        require(settings.tonic == null || settings.tonic in 0..11) { "Недопустимая тоника" }
        require(settings.meter in 2..4) { "Размер должен быть 2/4, 3/4 или 4/4" }
        require(settings.bars in 1..16) { "Количество тактов должно быть от 1 до 16" }
        require(settings.bpm in 40..240) { "BPM должен быть от 40 до 240" }
        require(settings.type != ExerciseType.CHORDS || settings.scale in Scale.chordModes) {
            "Для аккордов доступны только мажор и минор"
        }
        val tonic = settings.tonic ?: random.nextInt(12)
        return if (settings.type == ExerciseType.MELODY) {
            Exercise(settings, tonic, melody = makeMelody(tonic, settings, random))
        } else {
            Exercise(settings, tonic, chords = makeChords(tonic, settings, random))
        }
    }

    private fun makeMelody(tonic: Int, settings: ExerciseSettings, random: Random): List<List<NoteEvent>> {
        val anchor = (if (tonic <= 6) 60 else 48) + tonic
        val selectedDegrees = when {
            settings.difficulty != Difficulty.EASY -> (0..(if (settings.difficulty == Difficulty.NORMAL) 6 else 7)).toList()
            settings.scale == Scale.DORIAN -> listOf(0, 1, 2, 3, 5)
            settings.scale == Scale.MIXOLYDIAN -> listOf(0, 1, 2, 4, 6)
            else -> listOf(0, 1, 2, 3, 4)
        }
        val notes = selectedDegrees.map { degree ->
            anchor + if (degree == 7) 12 else settings.scale.steps[degree]
        }
        var current = 0
        return List(settings.bars) { barIndex ->
            var remaining = settings.meter * 2
            val bar = mutableListOf<NoteEvent>()
            while (remaining > 0) {
                val lengths = if (settings.difficulty == Difficulty.EASY) listOf(2, 4) else listOf(1, 2, 4)
                val possible = lengths.filter { it <= remaining }
                val duration = possible[random.nextInt(possible.size)]
                current = when {
                    barIndex == 0 && bar.isEmpty() -> listOf(0, 0, minOf(2, notes.lastIndex))[random.nextInt(3)]
                    barIndex == settings.bars - 1 && duration == remaining -> 0
                    else -> {
                        val reach = when (settings.difficulty) {
                            Difficulty.EASY -> 1
                            Difficulty.NORMAL -> 2
                            Difficulty.HARD -> 3
                        }
                        val options = notes.indices.filter { abs(it - current) <= reach }
                        val weights = options.map { degree ->
                            when (abs(degree - current)) { 1 -> 4; 0 -> 2; else -> 1 }
                        }
                        options[weightedIndex(weights, random)]
                    }
                }
                bar += NoteEvent(notes[current], duration)
                remaining -= duration
            }
            bar
        }
    }

    private fun makeChords(tonic: Int, settings: ExerciseSettings, random: Random): List<ChordEvent> {
        val anchor = 48 + tonic
        fun scaleMidi(index: Int): Int = anchor + 12 * (index / 7) + settings.scale.steps[index % 7]
        val durations = mutableListOf<Int>()
        var remaining = settings.bars
        while (remaining > 0) {
            val length = when (settings.chordLength) {
                ChordLength.EVERY_BAR -> 1
                ChordLength.TWO_BARS -> minOf(2, remaining)
                ChordLength.RANDOM -> minOf(1 + random.nextInt(2), remaining)
            }
            durations += length
            remaining -= length
        }
        var previous = -1
        return durations.mapIndexed { index, length ->
            val degree = if (index == 0 || (index == durations.lastIndex && durations.size > 2)) {
                0
            } else {
                val options = (0..6).filter { it != previous &&
                    !(index == durations.size - 2 && durations.size > 2 && it == 0) }
                val weights = options.map { if (it in listOf(0, 3, 4, 5)) 3 else 1 }
                options[weightedIndex(weights, random)]
            }
            previous = degree
            ChordEvent(degree, listOf(scaleMidi(degree), scaleMidi(degree + 2), scaleMidi(degree + 4)), length)
        }
    }

    private fun weightedIndex(weights: List<Int>, random: Random): Int {
        var selection = random.nextInt(weights.sum())
        weights.forEachIndexed { index, weight ->
            selection -= weight
            if (selection < 0) return index
        }
        error("Пустой набор весов")
    }

    fun pitchName(pitchClass: Int, notation: Notation): String =
        (if (notation == Notation.LATIN) latinNotes else russianNotes)[pitchClass.mod(12)]

    fun noteName(midi: Int, notation: Notation): String =
        "${pitchName(midi, notation)}${midi / 12 - 1}"

    fun chordQuality(midis: List<Int>): String = when (listOf(midis[1] - midis[0], midis[2] - midis[0])) {
        listOf(4, 7) -> "major"
        listOf(3, 7) -> "minor"
        listOf(3, 6) -> "diminished"
        else -> error("Неизвестное трезвучие")
    }

    fun answer(exercise: Exercise, notation: Notation): String = buildString {
        appendLine("Тональность: ${pitchName(exercise.tonic, notation)} ${exercise.settings.scale.label}")
        appendLine()
        if (exercise.settings.type == ExerciseType.MELODY) {
            exercise.melody.forEachIndexed { index, bar ->
                append("Такт ${index + 1}:  ")
                appendLine(bar.joinToString("   ") { event ->
                    val duration = when (event.eighths) { 1 -> "⅛"; 2 -> "¼"; else -> "½" }
                    "${noteName(event.midi, notation)} ($duration)"
                })
            }
            append("\n⅛ — восьмая, ¼ — четверть, ½ — половина. Октава указана после названия ноты.")
        } else {
            var barNumber = 1
            exercise.chords.forEach { chord ->
                val quality = chordQuality(chord.midis)
                var roman = listOf("I", "II", "III", "IV", "V", "VI", "VII")[chord.degree]
                if (quality != "major") roman = roman.lowercase()
                if (quality == "diminished") roman += "°"
                val root = pitchName(chord.midis.first(), notation)
                val chordName = if (notation == Notation.LATIN) {
                    root + mapOf("major" to "", "minor" to "m", "diminished" to "dim").getValue(quality)
                } else {
                    root + mapOf("major" to " маж.", "minor" to " мин.", "diminished" to " ум.").getValue(quality)
                }
                val label = if (chord.bars == 1) "$barNumber" else "$barNumber–${barNumber + chord.bars - 1}"
                appendLine("Такт(ы) $label:  $roman · $chordName · ${chord.midis.joinToString(" – ") { noteName(it, notation) }}")
                barNumber += chord.bars
            }
            append("\nСтупень указана римской цифрой; «°» означает уменьшённое трезвучие.")
        }
    }
}
