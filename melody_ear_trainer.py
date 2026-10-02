"""Небольшой тренажёр подбора мелодий и аккордов на слух для Windows.

Запуск: python melody_ear_trainer.py
Зависимости: только стандартная библиотека Python (Tkinter и winsound).
"""

from __future__ import annotations

import math
import random
import struct
import tempfile
import tkinter as tk
import uuid
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from typing import BinaryIO
import winsound


NOTES_RU = ("До", "До♯", "Ре", "Ре♯", "Ми", "Фа", "Фа♯", "Соль", "Соль♯", "Ля", "Ля♯", "Си")
NOTES_EN = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
SCALES = {
    "мажор": (0, 2, 4, 5, 7, 9, 11),       # ионийский
    "дорийский": (0, 2, 3, 5, 7, 9, 10),
    "фригийский": (0, 1, 3, 5, 7, 8, 10),
    "лидийский": (0, 2, 4, 6, 7, 9, 11),
    "миксолидийский": (0, 2, 4, 5, 7, 9, 10),
    "минор": (0, 2, 3, 5, 7, 8, 10),       # эолийский
    "локрийский": (0, 1, 3, 5, 6, 8, 10),
}
MELODY_MODES = tuple(SCALES)
CHORD_MODES = ("мажор", "минор")
NOTATION_OPTIONS = ("До–Ре–Ми", "C–D–E")
CHORD_LENGTH_OPTIONS = ("Каждый такт", "Каждые 2 такта", "Случайно: 1–2 такта")
SAMPLE_RATE = 22050


@dataclass(frozen=True)
class Event:
    midi: int
    eighths: int


@dataclass(frozen=True)
class ChordEvent:
    degree: int
    midis: tuple[int, int, int]
    bars: int
    inversion: int = 0


def pitch_name(pitch_class: int, notation: str) -> str:
    names = NOTES_EN if notation == NOTATION_OPTIONS[1] else NOTES_RU
    return names[pitch_class % 12]


def note_name(midi: int, notation: str = NOTATION_OPTIONS[1]) -> str:
    return f"{pitch_name(midi, notation)}{midi // 12 - 1}"


def duration_name(eighths: int) -> str:
    return {1: "⅛", 2: "¼", 4: "½"}[eighths]


def make_exercise(
    tonic: int, mode: str, numerator: int, bars: int, level: str, rng: random.Random
) -> list[list[Event]]:
    """Создаёт такты, каждый из которых заполнен ровно до границы размера."""
    if not 0 <= tonic < 12 or mode not in SCALES or numerator not in (2, 3, 4) or not 1 <= bars <= 16:
        raise ValueError("Недопустимые параметры упражнения")
    if level not in ("Легко", "Обычно", "Сложнее"):
        raise ValueError("Недопустимая сложность")

    # Тоника находится в удобном для электрогитары регистре G3–F#4.
    anchor = (60 if tonic <= 6 else 48) + tonic
    scale = SCALES[mode]
    if level == "Легко":
        # Даже короткие упражнения могут затронуть характерную ступень лада.
        selected_degrees = {
            "дорийский": (0, 1, 2, 3, 5),
            "миксолидийский": (0, 1, 2, 4, 6),
        }.get(mode, (0, 1, 2, 3, 4))
    else:
        selected_degrees = tuple(range(7 if level == "Обычно" else 8))
    degrees = [anchor + scale[d] if d < 7 else anchor + 12 for d in selected_degrees]
    max_degree = len(degrees) - 1
    current = 0
    result: list[list[Event]] = []

    for bar_index in range(bars):
        remaining = numerator * 2
        current_bar: list[Event] = []
        while remaining:
            lengths = [2, 4] if level == "Легко" else [1, 2, 4]
            possible = [length for length in lengths if length <= remaining]
            if not possible:  # На лёгком уровне остаток всегда чётный.
                possible = [remaining]
            duration = rng.choice(possible)

            if bar_index == 0 and not current_bar:
                current = rng.choice([0, 0, min(2, max_degree)])
            elif bar_index == bars - 1 and duration == remaining:
                current = 0
            else:
                reach = 1 if level == "Легко" else (3 if level == "Сложнее" else 2)
                options = [d for d in range(max_degree + 1) if abs(d - current) <= reach]
                # Соседние ступени встречаются чаще скачков.
                weights = [4 if abs(d - current) == 1 else 2 if d == current else 1 for d in options]
                current = rng.choices(options, weights=weights, k=1)[0]

            current_bar.append(Event(degrees[current], duration))
            remaining -= duration
        result.append(current_bar)
    return result


def make_chord_exercise(
    tonic: int, mode: str, bars: int, chord_length: str, rng: random.Random, level: str = "Легко"
) -> list[ChordEvent]:
    """Собирает последовательность диатонических трезвучий целыми тактами."""
    if not 0 <= tonic < 12 or mode not in CHORD_MODES or not 1 <= bars <= 16:
        raise ValueError("Недопустимые параметры упражнения")
    if chord_length not in CHORD_LENGTH_OPTIONS:
        raise ValueError("Недопустимая длительность аккорда")
    if level not in ("Легко", "Обычно", "Сложнее"):
        raise ValueError("Недопустимая сложность")

    anchor = 48 + tonic  # C3–B3: корни аккордов остаются в гитарном диапазоне.
    scale = SCALES[mode]

    def scale_midi(index: int) -> int:
        octave, degree = divmod(index, 7)
        return anchor + 12 * octave + scale[degree]

    durations: list[int] = []
    remaining = bars
    while remaining:
        if chord_length == CHORD_LENGTH_OPTIONS[0]:
            length = 1
        elif chord_length == CHORD_LENGTH_OPTIONS[1]:
            length = min(2, remaining)
        else:
            length = min(rng.choice((1, 2)), remaining)
        durations.append(length)
        remaining -= length

    if level != "Легко":
        return _make_varied_chords(anchor, scale, mode, durations, level, rng)

    # Старый алгоритм лёгкого уровня: та же последовательность и те же вызовы RNG.
    result: list[ChordEvent] = []
    previous = -1
    for index, length in enumerate(durations):
        if index == 0 or (index == len(durations) - 1 and len(durations) > 2):
            degree = 0  # Тоника даёт понятное начало и завершение длинной фразы.
        else:
            options = [degree for degree in range(7) if degree != previous]
            if index == len(durations) - 2 and len(durations) > 2:
                options = [degree for degree in options if degree != 0]
            weights = [3 if degree in (0, 3, 4, 5) else 1 for degree in options]
            degree = rng.choices(options, weights=weights, k=1)[0]
        result.append(
            ChordEvent(
                degree=degree,
                midis=(scale_midi(degree), scale_midi(degree + 2), scale_midi(degree + 4)),
                bars=length,
            )
        )
        previous = degree
    return result


def _make_varied_chords(
    anchor: int, scale: tuple[int, ...], mode: str, durations: list[int],
    level: str, rng: random.Random,
) -> list[ChordEvent]:
    """Связные ступени; регистр выбирается по движению баса и голосов."""
    if mode == "мажор":
        starts = (0, 0, 3, 4, 5)
        next_degrees = (
            (3, 4, 5, 1), (4, 4, 0, 5, 6), (5, 3, 1),
            (0, 4, 1, 4), (0, 0, 5, 3), (3, 1, 4, 0), (0, 2, 4),
        )
    else:
        starts = (0, 0, 3, 5, 6)
        next_degrees = (
            (3, 5, 6, 4, 2), (4, 0), (5, 6, 3, 0),
            (0, 6, 4, 5), (0, 0, 5, 3), (2, 6, 3, 0), (0, 2, 5, 3),
        )

    def scale_midi(index: int) -> int:
        octave, degree = divmod(index, 7)
        return anchor + 12 * octave + scale[degree]

    result: list[ChordEvent] = []
    degree = rng.choice(starts)
    for index, length in enumerate(durations):
        if index:
            options = next_degrees[degree]
            if len(result) >= 3 and result[-3].degree == result[-1].degree:
                varied = tuple(next_degree for next_degree in options
                               if next_degree != result[-2].degree)
                if varied:
                    options = varied
            degree = rng.choice(options)
        root = scale_midi(degree)
        third = scale_midi(degree + 2) - root
        fifth = scale_midi(degree + 4) - root
        candidates: list[tuple[int, tuple[int, int, int]]] = []
        for shift in (-24, -12, 0, 12):
            base = root + shift
            voicings = (
                (base, base + third, base + fifth),
                (base + third, base + fifth, base + 12),
                (base + fifth, base + 12, base + 12 + third),
            )
            for inversion, midis in enumerate(voicings[:1 if level == "Обычно" else 3]):
                low, high = (43, 64) if level == "Обычно" else (40, 68)
                if low <= midis[0] <= high and midis[-1] <= 79:
                    candidates.append((inversion, midis))

        if level == "Сложнее" and index == len(durations) - 1 and len(durations) > 1 \
                and all(chord.inversion == 0 for chord in result):
            candidates = [candidate for candidate in candidates if candidate[0] != 0]
        if level == "Обычно" and len(durations) >= 4 and index == len(durations) // 2 \
                and all(anchor <= chord.midis[0] < anchor + 12 for chord in result):
            outside = [candidate for candidate in candidates
                       if not anchor <= candidate[1][0] < anchor + 12
                       and abs(candidate[1][0] - result[-1].midis[0]) <= 12]
            if outside:
                candidates = outside

        previous = result[-1].midis if result else None
        if previous is not None:
            limit = 12 if level == "Обычно" else 18
            nearby = [candidate for candidate in candidates
                      if abs(candidate[1][0] - previous[0]) <= limit]
            if nearby:
                candidates = nearby
        weights: list[int] = []
        for inversion, midis in candidates:
            if previous is None:
                weight = max(1, 11 - abs(midis[0] - 54))
            else:
                bass_motion = abs(midis[0] - previous[0])
                voice_motion = sum(abs(a - b) for a, b in zip(midis, previous))
                weight = max(1, 12 - bass_motion) * (3 if voice_motion <= 15 else 2 if voice_motion <= 27 else 1)
            if level == "Сложнее":
                weight *= (5, 4, 2)[inversion]
            if index and not anchor <= midis[0] < anchor + 12:
                weight *= 2
            weights.append(weight)
        inversion, midis = rng.choices(candidates, weights=weights, k=1)[0]
        result.append(ChordEvent(degree, midis, length, inversion))
    return result


def make_accompanied_melody(
    tonic: int, mode: str, numerator: int, bars: int, level: str,
    chords: list[ChordEvent], rng: random.Random,
) -> list[list[Event]]:
    """Строит мелодию в ладу с опорой на звуки аккорда на сильных долях."""
    if mode not in CHORD_MODES or sum(chord.bars for chord in chords) != bars:
        raise ValueError("Аккорды не соответствуют мелодии")
    # Используем те же длительности, что в самостоятельном упражнении.
    rhythm = make_exercise(tonic, mode, numerator, bars, level, rng)
    anchor = (60 if tonic <= 6 else 48) + tonic
    scale = SCALES[mode]
    active_chords = [chord for chord in chords for _ in range(chord.bars)]
    current = 0
    result: list[list[Event]] = []
    for bar_index, bar in enumerate(rhythm):
        chord = active_chords[bar_index]
        chord_degrees = {(chord.degree + step) % 7 for step in (0, 2, 4)}
        elapsed = 0
        arranged: list[Event] = []
        for event_index, event in enumerate(bar):
            final = bar_index == bars - 1 and event_index == len(bar) - 1
            if final and chord.degree == 0:
                options = [0]
            elif final or elapsed % 2 == 0:
                options = [degree for degree in range(8) if degree % 7 in chord_degrees]
            else:
                options = list(range(8))
            reach = {"Легко": 2, "Обычно": 3, "Сложнее": 4}[level]
            nearby = [degree for degree in options if abs(degree - current) <= reach]
            if nearby:
                options = nearby
            weights = [
                (4 if abs(degree - current) == 1 else 2 if degree == current else 1)
                * (3 if degree % 7 in chord_degrees else 1)
                for degree in options
            ]
            current = rng.choices(options, weights=weights, k=1)[0]
            midi = anchor + (scale[current] if current < 7 else 12)
            arranged.append(Event(midi, event.eighths))
            elapsed += event.eighths
        result.append(arranged)
    return result


def _triad_identity(midis: tuple[int, int, int]) -> tuple[int, str]:
    qualities = {(0, 4, 7): "major", (0, 3, 7): "minor", (0, 3, 6): "diminished"}
    for root in midis:
        intervals = tuple(sorted((note - root) % 12 for note in midis))
        if intervals in qualities:
            return root % 12, qualities[intervals]
    raise ValueError("Неизвестное трезвучие")


def chord_quality(midis: tuple[int, int, int]) -> str:
    return _triad_identity(midis)[1]


def chord_name(chord: ChordEvent, notation: str) -> str:
    root_pc, quality = _triad_identity(chord.midis)
    root = pitch_name(root_pc, notation)
    if notation == NOTATION_OPTIONS[1]:
        name = root + {"major": "", "minor": "m", "diminished": "dim"}[quality]
    else:
        name = root + {"major": " маж.", "minor": " мин.", "diminished": " ум."}[quality]
    return f"{name}/{pitch_name(chord.midis[0], notation)}" if chord.inversion else name


def make_wav(path: Path, exercise: list[list[Event]], bpm: int, numerator: int) -> None:
    """Синтезирует слышимый, но простой тон с коротким затуханием."""
    beat_seconds = 60.0 / bpm
    frames = bytearray()
    # Отсчёт в один такт помогает различать доли, не выдавая ноты.
    for _ in range(numerator):
        frames.extend(_tone(880, beat_seconds * 0.17, beat_seconds, 0.14))
    for bar in exercise:
        for event in bar:
            seconds = event.eighths * beat_seconds / 2
            frequency = 440.0 * 2 ** ((event.midi - 69) / 12)
            frames.extend(_tone(frequency, seconds * 0.88, seconds, 0.42))

    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(frames)


def make_chord_wav(path: Path, exercise: list[ChordEvent], bpm: int, numerator: int) -> None:
    """Проигрывает каждый аккорд одним мягким ударом на весь его блок тактов."""
    beat_seconds = 60.0 / bpm
    frames = bytearray()
    for _ in range(numerator):
        frames.extend(_tone(880, beat_seconds * 0.17, beat_seconds, 0.14))
    for chord in exercise:
        duration = chord.bars * numerator * beat_seconds
        frames.extend(_chord_tone(chord.midis, duration))

    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(frames)


def make_combined_wav(
    path: Path | BinaryIO, melody: list[list[Event]], chords: list[ChordEvent], bpm: int, numerator: int,
) -> None:
    """Смешивает обе партии по общей сетке тактов после одного такта счёта."""
    if sum(chord.bars for chord in chords) != len(melody):
        raise ValueError("Аккорды не соответствуют мелодии")
    beat_seconds = 60.0 / bpm
    bar_samples = int(numerator * beat_seconds * SAMPLE_RATE)
    music = array("i", [0]) * (len(melody) * bar_samples)

    def add_sound(sound: bytes, start_sample: int, volume: float) -> None:
        for offset, (sample,) in enumerate(struct.iter_unpack("<h", sound)):
            position = start_sample + offset
            if position >= len(music):
                break
            music[position] += int(sample * volume)

    bar_number = 0
    for chord in chords:
        add_sound(_chord_tone(chord.midis, chord.bars * numerator * beat_seconds),
                  bar_number * bar_samples, 0.6)
        bar_number += chord.bars
    for bar_number, bar in enumerate(melody):
        elapsed_eighths = 0
        for event in bar:
            seconds = event.eighths * beat_seconds / 2
            frequency = 440.0 * 2 ** ((event.midi - 69) / 12)
            start = bar_number * bar_samples + int(elapsed_eighths * beat_seconds * SAMPLE_RATE / 2)
            add_sound(_tone(frequency, seconds * 0.88, seconds, 0.42), start, 0.9)
            elapsed_eighths += event.eighths

    frames = bytearray()
    for _ in range(numerator):
        frames.extend(_tone(880, beat_seconds * 0.17, beat_seconds, 0.14))
    for sample in music:
        frames.extend(struct.pack("<h", max(-32768, min(32767, sample))))
    # wave.open в Python 3.10–3.11 не принимает pathlib.Path напрямую.
    with wave.open(str(path) if isinstance(path, Path) else path, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(frames)


def _tone(frequency: float, sounding: float, total: float, volume: float) -> bytes:
    samples = int(total * SAMPLE_RATE)
    sounding_samples = int(sounding * SAMPLE_RATE)
    data = bytearray()
    for index in range(samples):
        if index >= sounding_samples:
            value = 0
        else:
            t = index / SAMPLE_RATE
            attack = min(1.0, index / (SAMPLE_RATE * 0.012))
            release = min(1.0, (sounding_samples - index) / (SAMPLE_RATE * 0.045))
            envelope = max(0.0, min(attack, release))
            # Несколько обертонов помогают слышать ноту на небольших колонках.
            sound = math.sin(2 * math.pi * frequency * t)
            sound += 0.22 * math.sin(4 * math.pi * frequency * t)
            sound += 0.07 * math.sin(6 * math.pi * frequency * t)
            value = int(23000 * volume * envelope * sound)
        data.extend(struct.pack("<h", value))
    return data


def _chord_tone(midis: tuple[int, int, int], duration: float) -> bytes:
    voices = (midis[0] - 12, *midis)
    frequencies = [440.0 * 2 ** ((midi - 69) / 12) for midi in voices]
    samples = int(duration * SAMPLE_RATE)
    sounding = duration - min(0.09, duration * 0.04)
    data = bytearray()
    for index in range(samples):
        t = index / SAMPLE_RATE
        if t >= sounding:
            value = 0
        else:
            release = min(1.0, (sounding - t) / 0.08)
            decay = 1.0 - 0.25 * t / duration
            mixed = 0.0
            for voice_index, frequency in enumerate(frequencies):
                local_time = t - voice_index * 0.018  # Небольшое арпеджио, как удар по струнам.
                if local_time < 0:
                    continue
                attack = min(1.0, local_time / 0.012)
                phase = 2 * math.pi * frequency * local_time
                sound = math.sin(phase) + 0.18 * math.sin(2 * phase)
                mixed += (0.8 if voice_index == 0 else 1.0) * attack * sound
            value = int(5200 * release * decay * mixed)
        data.extend(struct.pack("<h", value))
    return data


class Trainer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Тренажёр слуха")
        icon_dir = Path(__file__).resolve().parent
        # Windows сам выбирает подходящий размер из ICO для окна и панели задач.
        self.iconbitmap(str(icon_dir / "logo.ico"))
        self.geometry("780x700")
        self.minsize(700, 670)
        self.configure(padx=22, pady=18)
        self.rng = random.Random()
        self.exercise: list[list[Event]] | None = None
        self.chords: list[ChordEvent] | None = None
        self.actual_key: tuple[int, str] | None = None
        self.random_key = True
        self.answer_visible = False
        self.audio_path = Path(tempfile.gettempdir()) / f"melody-ear-{uuid.uuid4().hex}.wav"

        self.heading_var = tk.StringVar(value="Подбери мелодию на слух")
        self.description_var = tk.StringVar(value="Слушай, найди ноты на гитаре, затем открой ответ.")
        ttk.Label(self, textvariable=self.heading_var, font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(self, textvariable=self.description_var).pack(anchor="w", pady=(2, 12))

        self.exercise_var = tk.StringVar(value="Мелодия")
        self.notation_var = tk.StringVar(value=NOTATION_OPTIONS[1])
        self.key_var = tk.StringVar(value="Случайная")
        self.mode_var = tk.StringVar(value="мажор")
        self.last_melody_mode = "мажор"
        self.previous_exercise_mode = "Мелодия"
        self.meter_var = tk.StringVar(value="4/4")
        self.bars_var = tk.StringVar(value="2")
        self.bpm_var = tk.StringVar(value="80")
        self.level_var = tk.StringVar(value="Легко")
        self.chord_length_var = tk.StringVar(value=CHORD_LENGTH_OPTIONS[0])

        mode_panel = ttk.LabelFrame(self, text="Что будем подбирать?", padding=(12, 7))
        mode_panel.pack(fill="x", pady=(0, 10))
        for column, (label, value) in enumerate(
            (("Мелодию", "Мелодия"), ("Аккорды", "Аккорды"),
             ("Аккорды + мелодию", "Вместе"))
        ):
            ttk.Radiobutton(
                mode_panel,
                text=label,
                variable=self.exercise_var,
                value=value,
                command=self._mode_changed,
            ).grid(row=0, column=column, sticky="w", padx=(0, 28))

        settings = ttk.LabelFrame(self, text="Настройки упражнения", padding=(12, 8))
        settings.pack(fill="x")
        controls = [
            ("Названия нот", self.notation_var, NOTATION_OPTIONS),
            ("Тоника", self.key_var, ["Случайная", *NOTES_EN]),
            ("Лад", self.mode_var, MELODY_MODES),
            ("Размер", self.meter_var, ["2/4", "3/4", "4/4"]),
            ("Тактов (1–16)", self.bars_var, None),
            ("Темп, BPM (40–240)", self.bpm_var, None),
            ("Сложность", self.level_var, ["Легко", "Обычно", "Сложнее"]),
            ("Смена аккордов", self.chord_length_var, CHORD_LENGTH_OPTIONS),
        ]
        for index, (label, variable, values) in enumerate(controls):
            row, column = divmod(index, 3)
            cell = ttk.Frame(settings, padding=(0, 0, 15, 8))
            cell.grid(row=row, column=column, sticky="ew")
            ttk.Label(cell, text=label).pack(anchor="w")
            if values is None:
                control = ttk.Entry(cell, textvariable=variable, width=23)
            else:
                control = ttk.Combobox(cell, textvariable=variable, values=values, state="readonly", width=20)
            control.pack(fill="x", pady=(3, 0))
            if index == 0:
                control.bind("<<ComboboxSelected>>", self._notation_changed)
            elif index == 1:
                self.key_combo = control
            elif index == 2:
                self.scale_combo = control
            elif index == 6:
                self.level_combo = control
            elif index == 7:
                self.chord_length_combo = control
        for column in range(3):
            settings.columnconfigure(column, weight=1)
        self.chord_length_combo.configure(state="disabled")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(3, 8))
        self.new_button = ttk.Button(buttons, text="Новая мелодия", command=self.generate)
        self.new_button.pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="▶ Слушать ещё", command=self.play).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="■ Стоп", command=self.stop).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Показать ответ", command=self.reveal).pack(side="left")

        self.status_var = tk.StringVar(value="Выбери настройки и нажми «Новая мелодия».")
        ttk.Label(self, textvariable=self.status_var, wraplength=710).pack(anchor="w", pady=(0, 9))
        self.answer = tk.Text(self, height=8, wrap="word", font=("Segoe UI", 11), padx=12, pady=10)
        self.answer.pack(fill="both", expand=True)
        self._set_answer("Ответ пока скрыт.")
        self.hint_var = tk.StringVar(
            value="Легко: до 5 ступеней, четверти и половины. Обычно: до 7 ступеней и восьмые. "
                  "Перед мелодией звучит один такт счётных щелчков."
        )
        ttk.Label(self, textvariable=self.hint_var, wraplength=710).pack(anchor="w", pady=(9, 0))
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _set_answer(self, text: str) -> None:
        self.answer.configure(state="normal")
        self.answer.delete("1.0", "end")
        self.answer.insert("1.0", text)
        self.answer.configure(state="disabled")

    def _mode_changed(self, _event: object = None) -> None:
        self.stop()
        self.exercise = None
        self.chords = None
        self.actual_key = None
        self.answer_visible = False
        self._set_answer("Ответ пока скрыт.")
        selected = self.exercise_var.get()
        if self.previous_exercise_mode == "Мелодия":
            self.last_melody_mode = self.mode_var.get()
        if selected in ("Аккорды", "Вместе"):
            self.scale_combo.configure(values=CHORD_MODES)
            if self.mode_var.get() not in CHORD_MODES:
                self.mode_var.set("мажор")
            if self.bars_var.get() == "2":
                self.bars_var.set("4")
            self.chord_length_combo.configure(state="readonly")
        else:
            self.scale_combo.configure(values=MELODY_MODES)
            self.mode_var.set(self.last_melody_mode)
            self.chord_length_combo.configure(state="disabled")

        if selected == "Аккорды":
            self.heading_var.set("Подбери аккорды на слух")
            self.description_var.set("Слушай последовательность и найди аккорды на гитаре.")
            self.new_button.configure(text="Новые аккорды")
            self.level_combo.configure(state="readonly")
            self.hint_var.set("Легко: аккорды в одном регистре, начало на I ступени. "
                              "Обычно: разные регистры и связные переходы. "
                              "Сложнее: шире диапазон и обращения трезвучий.")
        elif selected == "Вместе":
            self.heading_var.set("Подбери аккорды и мелодию")
            self.description_var.set("Слушай две партии одновременно и подбери их на гитаре.")
            self.new_button.configure(text="Новое упражнение")
            self.level_combo.configure(state="readonly")
            self.hint_var.set("Мелодия опирается на ноты текущего аккорда на сильных долях. "
                              "Перед обеими партиями звучит один такт счёта.")
        else:
            self.heading_var.set("Подбери мелодию на слух")
            self.description_var.set("Слушай, найди ноты на гитаре, затем открой ответ.")
            self.new_button.configure(text="Новая мелодия")
            self.level_combo.configure(state="readonly")
            self.hint_var.set("Легко: до 5 ступеней, четверти и половины. Обычно: до 7 ступеней и восьмые. "
                              "Перед мелодией звучит один такт счётных щелчков.")
        self.previous_exercise_mode = selected
        self.status_var.set("Выбери настройки и создай новое упражнение.")

    def _notation_changed(self, _event: object = None) -> None:
        selected = self.key_combo.current()
        names = NOTES_EN if self.notation_var.get() == NOTATION_OPTIONS[1] else NOTES_RU
        self.key_combo.configure(values=("Случайная", *names))
        self.key_combo.current(max(0, selected))
        self._update_status()
        if self.answer_visible:
            self.reveal()

    def _update_status(self) -> None:
        if not self.actual_key:
            return
        tonic, mode = self.actual_key
        key_hint = "Тональность скрыта" if self.random_key and not self.answer_visible else (
            f"{pitch_name(tonic, self.notation_var.get())} {mode}"
        )
        category = {"Мелодия": "Мелодия", "Аккорды": "Аккорды",
                    "Вместе": "Аккорды + мелодия"}[self.exercise_var.get()]
        self.status_var.set(
            f"{category} · {key_hint} · {self.meter_var.get()} · "
            f"{self.bars_var.get()} такт(ов) · {self.bpm_var.get()} ударов/мин"
        )

    def generate(self) -> None:
        try:
            selected_key = self.key_combo.current()
            if selected_key < 0:
                raise ValueError("Выбери тональность")
            random_key = selected_key == 0
            tonic = self.rng.randrange(12) if random_key else selected_key - 1
            mode = self.mode_var.get()
            meter = int(self.meter_var.get()[0])
            try:
                bars = int(self.bars_var.get())
                bpm = int(self.bpm_var.get())
            except ValueError as error:
                raise ValueError("Введи целые числа для количества тактов и BPM") from error
            if not 1 <= bars <= 16:
                raise ValueError("Количество тактов должно быть от 1 до 16")
            if not 40 <= bpm <= 240:
                raise ValueError("BPM должен быть от 40 до 240")
            self.stop()
            self.random_key = random_key
            if self.exercise_var.get() == "Аккорды":
                self.chords = make_chord_exercise(
                    tonic, mode, bars, self.chord_length_var.get(), self.rng, self.level_var.get()
                )
                make_chord_wav(self.audio_path, self.chords, bpm, meter)
                self.exercise = None
                self._set_answer("Ответ пока скрыт. Попробуй услышать басовую ноту и качество каждого аккорда.")
            elif self.exercise_var.get() == "Вместе":
                self.chords = make_chord_exercise(tonic, mode, bars, self.chord_length_var.get(), self.rng)
                self.exercise = make_accompanied_melody(
                    tonic, mode, meter, bars, self.level_var.get(), self.chords, self.rng
                )
                make_combined_wav(self.audio_path, self.exercise, self.chords, bpm, meter)
                self._set_answer("Ответ пока скрыт. Попробуй сначала услышать аккорды, затем мелодию.")
            else:
                self.exercise = make_exercise(tonic, mode, meter, bars, self.level_var.get(), self.rng)
                make_wav(self.audio_path, self.exercise, bpm, meter)
                self.chords = None
                self._set_answer("Ответ пока скрыт. Попробуй напеть мелодию и затем найти её на гитаре.")
            self.actual_key = (tonic, mode)
            self.answer_visible = False
            self._update_status()
            self.play()
        except (ValueError, OSError, KeyError) as error:
            messagebox.showerror("Не получилось создать упражнение", str(error))
        except Exception as error:
            # В pythonw.exe у Tkinter нет видимой консоли для ошибок обработчиков кнопок.
            messagebox.showerror("Ошибка приложения", f"Не получилось создать упражнение: {error}")

    def play(self) -> None:
        if self.exercise is None and self.chords is None:
            self.status_var.set("Сначала создай упражнение.")
            return
        winsound.PlaySound(str(self.audio_path), winsound.SND_FILENAME | winsound.SND_ASYNC)

    def stop(self) -> None:
        winsound.PlaySound(None, 0)

    def reveal(self) -> None:
        if (self.exercise is None and self.chords is None) or not self.actual_key:
            self.status_var.set("Сначала создай упражнение.")
            return
        tonic, mode = self.actual_key
        notation = self.notation_var.get()
        lines = [f"Тональность: {pitch_name(tonic, notation)} {mode}", ""]
        if self.chords is not None:
            if self.exercise is not None:
                lines.extend(["Аккорды:", ""])
            bar_number = 1
            for chord in self.chords:
                quality = chord_quality(chord.midis)
                roman = ("I", "II", "III", "IV", "V", "VI", "VII")[chord.degree]
                if quality != "major":
                    roman = roman.lower()
                if quality == "diminished":
                    roman += "°"
                inversion = ("", " · 1-е обращение", " · 2-е обращение")[chord.inversion]
                bar_label = str(bar_number) if chord.bars == 1 else f"{bar_number}–{bar_number + chord.bars - 1}"
                tones = " – ".join(note_name(midi, notation) for midi in chord.midis)
                lines.append(f"Такт(ы) {bar_label}:  {roman} · {chord_name(chord, notation)}{inversion} · {tones}")
                bar_number += chord.bars
            explanation = "Ступень указана римской цифрой; «°» означает уменьшённое трезвучие."
            if any(chord.inversion for chord in self.chords):
                explanation += " После / указана басовая нота обращения."
            lines.extend(["", explanation])
        if self.exercise is not None:
            if self.chords is not None:
                lines.extend(["", "Мелодия:", ""])
            for number, bar in enumerate(self.exercise or [], start=1):
                notes = "   ".join(f"{note_name(event.midi, notation)} ({duration_name(event.eighths)})" for event in bar)
                lines.append(f"Такт {number}:  {notes}")
            lines.extend(["", "⅛ — восьмая, ¼ — четверть, ½ — половина. Октава указана после названия ноты."])
        self.answer_visible = True
        self._update_status()
        self._set_answer("\n".join(lines))

    def close(self) -> None:
        self.stop()
        self.audio_path.unlink(missing_ok=True)
        self.destroy()


if __name__ == "__main__":
    Trainer().mainloop()
