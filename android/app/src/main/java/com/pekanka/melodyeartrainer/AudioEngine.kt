package com.pekanka.melodyeartrainer

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.Handler
import android.os.Looper
import kotlin.math.PI
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin

/** Тот же синтез нот, счёта и аккордов, что используется в версии для Windows. */
object AudioEngine {
    const val SAMPLE_RATE = 22_050

    fun render(exercise: Exercise): ShortArray {
        if (exercise.settings.type == ExerciseType.BOTH) return renderCombined(exercise)
        val beatSeconds = 60.0 / exercise.settings.bpm
        val clicks = exercise.settings.meter * frameCount(beatSeconds)
        val music = if (exercise.settings.type == ExerciseType.MELODY) {
            exercise.melody.sumOf { bar -> bar.sumOf { frameCount(it.eighths * beatSeconds / 2) } }
        } else {
            exercise.chords.sumOf { frameCount(it.bars * exercise.settings.meter * beatSeconds) }
        }
        val samples = ShortArray(clicks + music)
        var offset = 0
        repeat(exercise.settings.meter) {
            offset = tone(samples, offset, 880.0, beatSeconds * 0.17, beatSeconds, 0.14)
        }
        if (exercise.settings.type == ExerciseType.MELODY) {
            exercise.melody.forEach { bar ->
                bar.forEach { event ->
                    val seconds = event.eighths * beatSeconds / 2
                    offset = tone(samples, offset, frequency(event.midi), seconds * 0.88, seconds, 0.42)
                }
            }
        } else {
            exercise.chords.forEach { chord ->
                val seconds = chord.bars * exercise.settings.meter * beatSeconds
                offset = chordTone(samples, offset, chord.midis, seconds)
            }
        }
        return samples
    }

    private fun renderCombined(exercise: Exercise): ShortArray {
        val beatSeconds = 60.0 / exercise.settings.bpm
        val barFrames = frameCount(exercise.settings.meter * beatSeconds)
        val countInFrames = exercise.settings.meter * frameCount(beatSeconds)
        val music = IntArray(exercise.settings.bars * barFrames)

        fun add(segment: ShortArray, start: Int, gain: Double) {
            for (index in segment.indices) {
                val position = start + index
                if (position >= music.size) break
                music[position] += (segment[index] * gain).toInt()
            }
        }

        var firstBar = 0
        exercise.chords.forEach { chord ->
            val duration = chord.bars * exercise.settings.meter * beatSeconds
            val segment = ShortArray(frameCount(duration))
            chordTone(segment, 0, chord.midis, duration)
            add(segment, firstBar * barFrames, 0.6)
            firstBar += chord.bars
        }
        exercise.melody.forEachIndexed { barIndex, bar ->
            var elapsedEighths = 0
            bar.forEach { event ->
                val seconds = event.eighths * beatSeconds / 2
                val segment = ShortArray(frameCount(seconds))
                tone(segment, 0, frequency(event.midi), seconds * 0.88, seconds, 0.42)
                val start = barIndex * barFrames + frameCount(elapsedEighths * beatSeconds / 2)
                add(segment, start, 0.9)
                elapsedEighths += event.eighths
            }
        }

        val result = ShortArray(countInFrames + music.size)
        var offset = 0
        repeat(exercise.settings.meter) {
            offset = tone(result, offset, 880.0, beatSeconds * 0.17, beatSeconds, 0.14)
        }
        music.forEachIndexed { index, sample ->
            result[countInFrames + index] = sample.coerceIn(
                Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt()
            ).toShort()
        }
        return result
    }

    private fun frameCount(seconds: Double): Int = (seconds * SAMPLE_RATE).toInt()

    private fun frequency(midi: Int): Double = 440.0 * 2.0.pow((midi - 69) / 12.0)

    private fun tone(
        target: ShortArray, start: Int, frequency: Double, sounding: Double, total: Double, volume: Double,
    ): Int {
        val count = frameCount(total)
        val soundingCount = frameCount(sounding)
        for (index in 0 until count) {
            if (index >= soundingCount) continue
            val time = index.toDouble() / SAMPLE_RATE
            val attack = min(1.0, index / (SAMPLE_RATE * 0.012))
            val release = min(1.0, (soundingCount - index) / (SAMPLE_RATE * 0.045))
            val envelope = min(attack, release).coerceAtLeast(0.0)
            val phase = 2 * PI * frequency * time
            val sound = sin(phase) + 0.22 * sin(2 * phase) + 0.07 * sin(3 * phase)
            target[start + index] = (23_000 * volume * envelope * sound).toInt().toShort()
        }
        return start + count
    }

    private fun chordTone(target: ShortArray, start: Int, midis: List<Int>, duration: Double): Int {
        val voices = listOf(midis.first() - 12) + midis
        val frequencies = voices.map(::frequency)
        val count = frameCount(duration)
        val sounding = duration - min(0.09, duration * 0.04)
        for (index in 0 until count) {
            val time = index.toDouble() / SAMPLE_RATE
            if (time >= sounding) continue
            val release = min(1.0, (sounding - time) / 0.08)
            val decay = 1.0 - 0.25 * time / duration
            var mixed = 0.0
            frequencies.forEachIndexed { voiceIndex, frequency ->
                val localTime = time - voiceIndex * 0.018
                if (localTime >= 0) {
                    val attack = min(1.0, localTime / 0.012)
                    val phase = 2 * PI * frequency * localTime
                    val sound = sin(phase) + 0.18 * sin(2 * phase)
                    mixed += (if (voiceIndex == 0) 0.8 else 1.0) * attack * sound
                }
            }
            target[start + index] = (5_200 * release * decay * mixed).toInt()
                .coerceIn(Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt()).toShort()
        }
        return start + count
    }
}

class ExercisePlayer {
    private val lock = Any()
    private var generation = 0L
    private var track: AudioTrack? = null

    fun play(samples: ShortArray, onError: (String) -> Unit = {}) {
        stop()
        val playbackId = synchronized(lock) { generation }
        Thread {
            var localTrack: AudioTrack? = null
            try {
                val minimum = AudioTrack.getMinBufferSize(
                    AudioEngine.SAMPLE_RATE,
                    AudioFormat.CHANNEL_OUT_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                )
                require(minimum > 0) { "Устройство не поддерживает воспроизведение звука" }
                val newTrack = AudioTrack.Builder()
                    .setAudioAttributes(
                        AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build()
                    )
                    .setAudioFormat(
                        AudioFormat.Builder().setSampleRate(AudioEngine.SAMPLE_RATE)
                            .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                            .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build()
                    )
                    .setTransferMode(AudioTrack.MODE_STREAM)
                    .setBufferSizeInBytes(maxOf(minimum, 8_192))
                    .build()
                localTrack = newTrack
                synchronized(lock) {
                    if (playbackId != generation) return@Thread
                    track = newTrack
                }
                newTrack.play()
                var offset = 0
                while (offset < samples.size && synchronized(lock) { playbackId == generation }) {
                    val written = newTrack.write(
                        samples, offset, minOf(4_096, samples.size - offset), AudioTrack.WRITE_BLOCKING
                    )
                    if (written <= 0) break
                    offset += written
                }
                // AudioTrack может ещё держать последний буфер после write().
                if (offset == samples.size && synchronized(lock) { playbackId == generation }) {
                    val deadline = System.nanoTime() + 2_000_000_000L
                    while (synchronized(lock) { playbackId == generation } && System.nanoTime() < deadline) {
                        val remainingFrames = samples.size - newTrack.playbackHeadPosition.toLong()
                        if (remainingFrames <= 0) break
                        Thread.sleep(100)
                    }
                }
            } catch (error: Exception) {
                if (synchronized(lock) { playbackId == generation }) {
                    Handler(Looper.getMainLooper()).post { onError(error.message ?: "Ошибка воспроизведения") }
                }
            } finally {
                synchronized(lock) {
                    if (track === localTrack) track = null
                }
                try { localTrack?.stop() } catch (_: IllegalStateException) { }
                localTrack?.release()
            }
        }.start()
    }

    fun stop() {
        val active = synchronized(lock) {
            generation++
            track.also { track = null }
        }
        try {
            active?.pause()
            active?.flush()
        } catch (_: IllegalStateException) { }
    }
}
