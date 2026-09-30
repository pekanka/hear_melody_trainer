"""Небольшой тренажёр подбора мелодий на слух для Windows.

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
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
import winsound


NOTES_RU = ("До", "До♯", "Ре", "Ре♯", "Ми", "Фа", "Фа♯", "Соль", "Соль♯", "Ля", "Ля♯", "Си")
SCALES = {"мажор": (0, 2, 4, 5, 7, 9, 11), "минор": (0, 2, 3, 5, 7, 8, 10)}
SAMPLE_RATE = 22050


@dataclass(frozen=True)
class Event:
    midi: int
    eighths: int


def note_name(midi: int) -> str:
    return f"{NOTES_RU[midi % 12]}{midi // 12 - 1}"


def duration_name(eighths: int) -> str:
    return {1: "⅛", 2: "¼", 4: "½"}[eighths]


def make_exercise(
    tonic: int, mode: str, numerator: int, bars: int, level: str, rng: random.Random
) -> list[list[Event]]:
    """Создаёт такты, каждый из которых заполнен ровно до границы размера."""
    if mode not in SCALES or numerator not in (2, 3, 4) or not 1 <= bars <= 16:
        raise ValueError("Недопустимые параметры упражнения")
    if level not in ("Легко", "Обычно", "Сложнее"):
        raise ValueError("Недопустимая сложность")

    # Тоника находится в удобном для электрогитары регистре G3–F#4.
    anchor = (60 if tonic <= 6 else 48) + tonic
    scale = SCALES[mode]
    max_degree = {"Легко": 4, "Обычно": 6, "Сложнее": 7}[level]
    degrees = [anchor + scale[d] if d < 7 else anchor + 12 for d in range(max_degree + 1)]
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


class Trainer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Мелодия на слух")
        self.geometry("720x570")
        self.minsize(620, 500)
        self.configure(padx=22, pady=18)
        self.rng = random.Random()
        self.exercise: list[list[Event]] | None = None
        self.actual_key: tuple[int, str] | None = None
        self.audio_path = Path(tempfile.gettempdir()) / f"melody-ear-{uuid.uuid4().hex}.wav"

        ttk.Label(self, text="Подбери мелодию на слух", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(self, text="Слушай, найди ноты на гитаре, затем открой ответ.").pack(anchor="w", pady=(2, 16))

        settings = ttk.Frame(self)
        settings.pack(fill="x")
        self.key_var = tk.StringVar(value="Случайная")
        self.mode_var = tk.StringVar(value="мажор")
        self.meter_var = tk.StringVar(value="4/4")
        self.bars_var = tk.StringVar(value="2")
        self.bpm_var = tk.StringVar(value="80")
        self.level_var = tk.StringVar(value="Легко")

        controls = [
            ("Тоника", self.key_var, ["Случайная", *NOTES_RU]),
            ("Лад", self.mode_var, ["мажор", "минор"]),
            ("Размер", self.meter_var, ["2/4", "3/4", "4/4"]),
            ("Тактов", self.bars_var, ["1", "2", "3", "4", "6", "8"]),
            ("Темп", self.bpm_var, ["50", "60", "70", "80", "90", "100", "120"]),
            ("Сложность", self.level_var, ["Легко", "Обычно", "Сложнее"]),
        ]
        for index, (label, variable, values) in enumerate(controls):
            row, column = divmod(index, 3)
            cell = ttk.Frame(settings, padding=(0, 0, 15, 12))
            cell.grid(row=row, column=column, sticky="ew")
            ttk.Label(cell, text=label).pack(anchor="w")
            ttk.Combobox(cell, textvariable=variable, values=values, state="readonly", width=17).pack(fill="x", pady=(3, 0))
        for column in range(3):
            settings.columnconfigure(column, weight=1)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(5, 12))
        ttk.Button(buttons, text="Новая мелодия", command=self.generate).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="▶ Слушать ещё", command=self.play).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="■ Стоп", command=self.stop).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Показать ответ", command=self.reveal).pack(side="left")

        self.status_var = tk.StringVar(value="Выбери настройки и нажми «Новая мелодия».")
        ttk.Label(self, textvariable=self.status_var, wraplength=650).pack(anchor="w", pady=(0, 9))
        self.answer = tk.Text(self, height=11, wrap="word", font=("Segoe UI", 11), padx=12, pady=10)
        self.answer.pack(fill="both", expand=True)
        self._set_answer("Ответ пока скрыт.")
        ttk.Label(
            self,
            text="Легко: до 5 ступеней, четверти и половины. Обычно: до 7 ступеней и восьмые. "
                 "Перед мелодией звучит один такт счётных щелчков.",
            wraplength=650,
        ).pack(anchor="w", pady=(9, 0))
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _set_answer(self, text: str) -> None:
        self.answer.configure(state="normal")
        self.answer.delete("1.0", "end")
        self.answer.insert("1.0", text)
        self.answer.configure(state="disabled")

    def generate(self) -> None:
        try:
            self.stop()
            tonic = self.rng.randrange(12) if self.key_var.get() == "Случайная" else NOTES_RU.index(self.key_var.get())
            mode = self.mode_var.get()
            meter = int(self.meter_var.get()[0])
            bars = int(self.bars_var.get())
            bpm = int(self.bpm_var.get())
            exercise = make_exercise(tonic, mode, meter, bars, self.level_var.get(), self.rng)
            make_wav(self.audio_path, exercise, bpm, meter)
            self.exercise = exercise
            self.actual_key = (tonic, mode)
            self._set_answer("Ответ пока скрыт. Попробуй напеть мелодию и затем найти её на гитаре.")
            key_hint = "Тональность скрыта" if self.key_var.get() == "Случайная" else f"{NOTES_RU[tonic]} {mode}"
            self.status_var.set(f"{key_hint} · {meter}/4 · {bars} такт(ов) · {bpm} ударов/мин")
            self.play()
        except (ValueError, OSError) as error:
            messagebox.showerror("Не получилось создать мелодию", str(error))

    def play(self) -> None:
        if not self.exercise:
            self.status_var.set("Сначала создай мелодию.")
            return
        winsound.PlaySound(str(self.audio_path), winsound.SND_FILENAME | winsound.SND_ASYNC)

    def stop(self) -> None:
        winsound.PlaySound(None, 0)

    def reveal(self) -> None:
        if not self.exercise or not self.actual_key:
            self.status_var.set("Сначала создай мелодию.")
            return
        tonic, mode = self.actual_key
        lines = [f"Тональность: {NOTES_RU[tonic]} {mode}", ""]
        for number, bar in enumerate(self.exercise, start=1):
            notes = "   ".join(f"{note_name(event.midi)} ({duration_name(event.eighths)})" for event in bar)
            lines.append(f"Такт {number}:  {notes}")
        lines.extend(["", "⅛ — восьмая, ¼ — четверть, ½ — половина. Октава указана после названия ноты."])
        self._set_answer("\n".join(lines))

    def close(self) -> None:
        self.stop()
        self.audio_path.unlink(missing_ok=True)
        self.destroy()


if __name__ == "__main__":
    Trainer().mainloop()
