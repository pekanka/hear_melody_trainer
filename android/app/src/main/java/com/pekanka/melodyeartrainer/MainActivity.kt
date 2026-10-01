package com.pekanka.melodyeartrainer

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Random

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) { TrainerScreen() }
            }
        }
    }
}

@Composable
private fun TrainerScreen() {
    var type by rememberSaveable { mutableStateOf(ExerciseType.MELODY) }
    var notation by rememberSaveable { mutableStateOf(Notation.LATIN) }
    var tonicIndex by rememberSaveable { mutableStateOf(-1) }
    var scale by rememberSaveable { mutableStateOf(Scale.MAJOR) }
    var lastMelodyScale by rememberSaveable { mutableStateOf(Scale.MAJOR) }
    var meter by rememberSaveable { mutableStateOf(4) }
    var barsText by rememberSaveable { mutableStateOf("2") }
    var bpmText by rememberSaveable { mutableStateOf("80") }
    var difficulty by rememberSaveable { mutableStateOf(Difficulty.EASY) }
    var chordLength by rememberSaveable { mutableStateOf(ChordLength.EVERY_BAR) }

    var current by remember { mutableStateOf<Exercise?>(null) }
    var samples by remember { mutableStateOf<ShortArray?>(null) }
    var answerVisible by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("Выбери настройки и создай новое упражнение.") }
    var generationJob by remember { mutableStateOf<Job?>(null) }
    val player = remember { ExercisePlayer() }
    val scope = rememberCoroutineScope()
    DisposableEffect(player) { onDispose { player.stop() } }

    fun changeType(newType: ExerciseType) {
        if (newType == type) return
        generationJob?.cancel()
        player.stop()
        current = null
        samples = null
        answerVisible = false
        busy = false
        message = "Выбери настройки и создай новое упражнение."
        if (type == ExerciseType.MELODY) lastMelodyScale = scale
        if (newType != ExerciseType.MELODY) {
            if (scale !in Scale.chordModes) scale = Scale.MAJOR
            if (barsText == "2") barsText = "4"
        } else {
            scale = lastMelodyScale
        }
        type = newType
    }

    val tonicNames = if (notation == Notation.LATIN) ExerciseEngine.latinNotes else ExerciseEngine.russianNotes
    val scaleOptions = if (type == ExerciseType.MELODY) Scale.entries else Scale.chordModes

    Column(
        modifier = Modifier.fillMaxSize().systemBarsPadding().imePadding()
            .verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Тренажёр слуха", style = MaterialTheme.typography.headlineSmall)
        Text(when (type) {
            ExerciseType.MELODY -> "Слушай и подбери мелодию на гитаре."
            ExerciseType.CHORDS -> "Слушай последовательность и подбери аккорды на гитаре."
            ExerciseType.BOTH -> "Слушай две партии одновременно и подбери их на гитаре."
        })

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp)) {
                Text("Что будем подбирать?", style = MaterialTheme.typography.titleMedium)
                Column {
                    ExerciseType.entries.forEach { option ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = type == option, onClick = { changeType(option) })
                            Text(option.label)
                        }
                    }
                }
            }
        }

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Настройки упражнения", style = MaterialTheme.typography.titleMedium)
                ChoiceField("Названия нот", notation.label, Notation.entries.map { it.label }) {
                    notation = Notation.entries[it]
                }
                ChoiceField("Тоника", if (tonicIndex == -1) "Случайная" else tonicNames[tonicIndex],
                    listOf("Случайная") + tonicNames) { tonicIndex = it - 1 }
                ChoiceField("Лад", scale.label, scaleOptions.map { it.label }) { scale = scaleOptions[it] }
                ChoiceField("Размер", "$meter/4", listOf("2/4", "3/4", "4/4")) { meter = it + 2 }
                OutlinedTextField(
                    value = barsText, onValueChange = { barsText = it },
                    label = { Text("Тактов (1–16)") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = bpmText, onValueChange = { bpmText = it },
                    label = { Text("Темп, BPM (40–240)") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )
                if (type != ExerciseType.CHORDS) {
                    ChoiceField("Сложность", difficulty.label, Difficulty.entries.map { it.label }) {
                        difficulty = Difficulty.entries[it]
                    }
                }
                if (type != ExerciseType.MELODY) {
                    ChoiceField("Смена аккордов", chordLength.label, ChordLength.entries.map { it.label }) {
                        chordLength = ChordLength.entries[it]
                    }
                }
            }
        }

        Button(
            onClick = {
                val bars = barsText.trim().toIntOrNull()
                val bpm = bpmText.trim().toIntOrNull()
                if (bars == null || bpm == null) {
                    message = "Введи целые числа для количества тактов и BPM."
                } else if (bars !in 1..16) {
                    message = "Количество тактов должно быть от 1 до 16."
                } else if (bpm !in 40..240) {
                    message = "BPM должен быть от 40 до 240."
                } else {
                    val settings = ExerciseSettings(type, tonicIndex.takeIf { it >= 0 }, scale,
                        meter, bars, bpm, difficulty, chordLength)
                    generationJob?.cancel()
                    player.stop()
                    busy = true
                    message = "Создаю упражнение…"
                    generationJob = scope.launch {
                        try {
                            val (generated, rendered) = withContext(Dispatchers.Default) {
                                val exercise = ExerciseEngine.generate(settings, Random())
                                exercise to AudioEngine.render(exercise)
                            }
                            current = generated
                            samples = rendered
                            answerVisible = false
                            busy = false
                            message = when (generated.settings.type) {
                                ExerciseType.MELODY -> "Ответ скрыт. Попробуй напеть мелодию и найти её на гитаре."
                                ExerciseType.CHORDS -> "Ответ скрыт. Попробуй услышать бас и качество каждого аккорда."
                                ExerciseType.BOTH -> "Ответ скрыт. Попробуй сначала услышать аккорды, затем мелодию."
                            }
                            player.play(rendered) { message = it }
                        } catch (cancelled: CancellationException) {
                            throw cancelled
                        } catch (error: Exception) {
                            busy = false
                            message = error.message ?: "Не получилось создать упражнение."
                        }
                    }
                }
            },
            enabled = !busy,
            modifier = Modifier.fillMaxWidth(),
        ) { Text(when (type) {
            ExerciseType.MELODY -> "Новая мелодия"
            ExerciseType.CHORDS -> "Новые аккорды"
            ExerciseType.BOTH -> "Новое упражнение"
        }) }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = {
                val audio = samples
                if (audio == null) message = "Сначала создай упражнение."
                else player.play(audio) { message = it }
            }, modifier = Modifier.weight(1f), enabled = !busy) { Text("▶ Слушать ещё") }
            OutlinedButton(onClick = { player.stop() }, modifier = Modifier.weight(1f)) { Text("■ Стоп") }
        }
        OutlinedButton(onClick = {
            if (current == null) message = "Сначала создай упражнение."
            else answerVisible = true
        }, modifier = Modifier.fillMaxWidth(), enabled = !busy) { Text("Показать ответ") }

        val exercise = current
        if (exercise != null) {
            val key = if (exercise.settings.tonic == null && !answerVisible) "Тональность скрыта"
                else "${ExerciseEngine.pitchName(exercise.tonic, notation)} ${exercise.settings.scale.label}"
            Text("${exercise.settings.type.label} · $key · ${exercise.settings.meter}/4 · " +
                "${exercise.settings.bars} такт(ов) · ${exercise.settings.bpm} BPM")
        }
        Text(message)

        Card(modifier = Modifier.fillMaxWidth()) {
            Text(
                if (answerVisible && exercise != null) ExerciseEngine.answer(exercise, notation)
                else "Ответ пока скрыт.",
                modifier = Modifier.padding(14.dp),
            )
        }
        Text(
            when (type) {
                ExerciseType.MELODY -> "Легко: до 5 ступеней, четверти и половины. Обычно: до 7 ступеней и восьмые. Перед мелодией звучит такт счёта."
                ExerciseType.CHORDS -> "Звучат трезвучия в выбранном ладу. Каждый аккорд держится целый блок тактов; перед началом звучит такт счёта."
                ExerciseType.BOTH -> "Мелодия опирается на ноты текущего аккорда на сильных долях. Перед обеими партиями звучит такт счёта."
            },
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

@Composable
private fun ChoiceField(label: String, selected: String, options: List<String>, onSelect: (Int) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Column {
        Text(label, style = MaterialTheme.typography.labelLarge)
        Box(modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth()) {
                Text("$selected  ▾")
            }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                options.forEachIndexed { index, option ->
                    DropdownMenuItem(text = { Text(option) }, onClick = {
                        expanded = false
                        onSelect(index)
                    })
                }
            }
        }
    }
}
