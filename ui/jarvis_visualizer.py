"""
JarvisVoiceVisualizer - Globo de particulas animado reagindo a voz.
Janela flutuante movel que inicia na area do top bar.
"""

import logging
import math
import random
import threading
import time

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

try:
    import numpy as np
    import sounddevice as sd

    _HAS_AUDIO = True
except ImportError:
    _HAS_AUDIO = False

logger = logging.getLogger(__name__)


class AudioLevelMonitor:
    """Captura nivel de audio do microfone em tempo real."""

    def __init__(self):
        self._level = 0.0
        self._running = False
        self._thread = None
        self._stream = None

    @property
    def level(self) -> float:
        return self._level

    def start(self):
        if self._running or not _HAS_AUDIO:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug("Falha ao fechar stream de audio do Jarvis: %s", e)
            self._stream = None

    def _capture(self):
        try:

            def callback(indata, frames, time_info, status):
                if not self._running:
                    return
                volume = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
                self._level = min(1.0, volume * 8.0)

            self._stream = sd.InputStream(
                channels=1,
                samplerate=16000,
                blocksize=512,
                callback=callback,
                dtype="int16",
            )
            self._stream.start()
            while self._running:
                time.sleep(0.05)
        except Exception as e:
            logger.warning("Monitor de audio do Jarvis falhou: %s", e)
            self._level = 0.0

    def reset(self):
        self._level = 0.0


_DEFAULT_PARTICLE_COUNT = 800
_LISTENING_LABELS = ["ouvindo", "ouvindo .", "ouvindo ..", "ouvindo ..."]


class JarvisVoiceVisualizer(QWidget):
    """Globo flutuante de particulas que reage a voz."""

    VISUALIZATION_STOPPED = Signal()

    def __init__(
        self,
        parent=None,
        assistant_name: str = "Celsius",
        particle_count: int = _DEFAULT_PARTICLE_COUNT,
        fps: int = 60,
        use_internal_audio: bool = False,
    ):
        super().__init__(parent)
        self._assistant_name = assistant_name
        self._particle_count = max(200, min(1600, particle_count))
        fps = max(1, min(120, fps))
        idle_fps = min(30, fps)
        self._active_interval_ms = max(8, int(1000 / fps))
        self._idle_interval_ms = max(self._active_interval_ms, int(1000 / idle_fps))
        self._use_internal_audio = use_internal_audio

        self.setWindowTitle(f"{self._assistant_name} Voice")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(220, 260)

        self._px = [0.0] * self._particle_count
        self._py = [0.0] * self._particle_count
        self._pz = [0.0] * self._particle_count
        self._base_sizes = [0.0] * self._particle_count
        self._disp_x = [0.0] * self._particle_count
        self._disp_y = [0.0] * self._particle_count
        self._disp_z = [0.0] * self._particle_count

        self._rotation_y = 0.0
        self._rotation_x = 0.0
        self._rotation_z = 0.0
        self._energy = 0.0
        self._target_energy = 0.0
        self._mic_energy = 0.0
        self._target_mic_energy = 0.0
        self._idle_energy = 0.45
        self._is_speaking = False
        self._isListening = False
        self._isIdle = True
        self._pulse_phase = 0.0
        self._alive = True
        self._drag_pos = None
        self._listening_label_idx = 0
        self._listening_tick = 0

        self._mic_monitor = AudioLevelMonitor()

        self._init_particles()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.setInterval(self._idle_interval_ms)
        self._timer.start()

    def _init_particles(self):
        golden_angle = math.pi * (3.0 - math.sqrt(5.0))
        for i in range(self._particle_count):
            t = i / (self._particle_count - 1)
            y = 1.0 - t * 2.0
            r = math.sqrt(max(0.0, 1.0 - y * y))
            theta = golden_angle * i
            self._px[i] = math.cos(theta) * r
            self._py[i] = y
            self._pz[i] = math.sin(theta) * r
            self._base_sizes[i] = 0.6 + (i % 7) * 0.15

    def position_at_topbar(self, parent_widget):
        if parent_widget:
            px = parent_widget.x()
            py = parent_widget.y() + 30
            pw = parent_widget.width()
            cx = px + (pw - self.width()) // 2
            self.move(cx, py)
        else:
            self.move(200, 30)

    def start_speaking(self):
        self._isIdle = False
        self._is_speaking = True
        self._target_energy = 1.0
        self._timer.setInterval(self._active_interval_ms)
        if not self._timer.isActive():
            self._timer.start(self._active_interval_ms)
        self.show()
        self.raise_()

    def stop_speaking(self):
        self._is_speaking = False
        self._target_energy = 0.0
        if not self._isListening:
            self._isIdle = True

    def start_listening(self):
        self._isIdle = False
        self._isListening = True
        self._listening_label_idx = 0
        self._listening_tick = 0
        if self._use_internal_audio:
            self._mic_monitor.start()
        self._timer.setInterval(self._active_interval_ms)
        if not self._timer.isActive():
            self._timer.start(self._active_interval_ms)
        self.show()

    def stop_listening(self):
        self._isListening = False
        self._mic_monitor.stop()
        self._mic_monitor.reset()
        self._target_mic_energy = 0.0
        self._mic_energy = 0.0
        if not self._is_speaking:
            self._isIdle = True

    def set_energy(self, level: float):
        self._target_energy = max(0.0, min(1.0, level))

    def set_mic_level(self, level: float):
        self._target_mic_energy = max(0.0, min(1.0, level))

    def _animate(self):
        if not self._alive:
            return

        desired_interval = self._idle_interval_ms if self._isIdle else self._active_interval_ms
        if self._timer.interval() != desired_interval:
            self._timer.setInterval(desired_interval)

        if self._is_speaking:
            self._energy += (self._target_energy - self._energy) * 0.18
        elif not self._isListening:
            self._energy *= 0.93

        if self._isListening:
            raw_mic = (
                self._mic_monitor.level if self._use_internal_audio else self._target_mic_energy
            )
            self._mic_energy += (raw_mic - self._mic_energy) * 0.25
            self._target_mic_energy *= 0.92
            self._listening_tick += 1
            if self._listening_tick % 12 == 0:
                self._listening_label_idx = (self._listening_label_idx + 1) % len(_LISTENING_LABELS)
        else:
            self._mic_energy *= 0.90

        total_energy = max(self._energy, self._mic_energy)

        if self._isIdle:
            total_energy = self._idle_energy
            self._energy = self._idle_energy

        self._rotation_y += 0.005 + total_energy * 0.035
        self._rotation_x += 0.003 + total_energy * 0.015
        self._rotation_z += 0.002 + total_energy * 0.010
        self._pulse_phase += 0.08

        for i in range(self._particle_count):
            strength = total_energy * 0.8

            if self._mic_energy > 0.05:
                noise = math.sin(self._pulse_phase * 3.0 + self._px[i] * 8.0 + self._py[i] * 6.0)
                strength += self._mic_energy * 0.8 * max(0.0, noise)

            if self._energy > 0.1:
                wave = math.sin(self._pulse_phase * 2.0 + self._pz[i] * 7.0)
                strength += self._energy * 0.6 * max(0.0, wave)

            self._disp_x[i] += (random.random() - 0.5) * strength * 0.06
            self._disp_y[i] += (random.random() - 0.5) * strength * 0.06
            self._disp_z[i] += (random.random() - 0.5) * strength * 0.06

            self._disp_x[i] *= 0.82
            self._disp_y[i] *= 0.82
            self._disp_z[i] *= 0.82

        self.update()

    def paintEvent(self, event):
        if not self._alive:
            return

        try:
            total = max(self._energy, self._mic_energy)
            if self._isIdle:
                total = self._idle_energy
            if total < 0.001:
                return

            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, False)

            p.setCompositionMode(QPainter.CompositionMode_Clear)
            p.setPen(Qt.NoPen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.rect())

            p.setCompositionMode(QPainter.CompositionMode_Plus)

            globe_cy = self.height() * 0.42
            cx = self.width() * 0.5
            cy = globe_cy
            base_r = min(self.width() * 0.5, globe_cy) * 0.72

            pulse = math.sin(self._pulse_phase) * 0.02 * total
            scale = 1.0 + pulse + total * 0.20
            radius = base_r * scale

            cos_y = math.cos(self._rotation_y)
            sin_y = math.sin(self._rotation_y)
            cos_x = math.cos(self._rotation_x)
            sin_x = math.sin(self._rotation_x)
            cos_z = math.cos(self._rotation_z)
            sin_z = math.sin(self._rotation_z)

            tr = 60
            tg = 100
            tb = 180

            if self._is_speaking and self._energy > 0.15:
                warm = self._energy * 80
                tr = min(255, int(tr + warm))
                tg = min(255, int(tg + warm * 0.2))
                tb = max(0, int(tb - warm * 0.8))

            n = len(self._px)
            for i in range(n):
                bx = self._px[i] + self._disp_x[i]
                by = self._py[i] + self._disp_y[i]
                bz = self._pz[i] + self._disp_z[i]

                rx = bx * cos_y - bz * sin_y
                rz = bx * sin_y + bz * cos_y
                ry = by * cos_x - rz * sin_x
                rz2 = by * sin_x + rz * cos_x
                fx = rx * cos_z - ry * sin_z
                fy = rx * sin_z + ry * cos_z

                sx = cx + fx * radius
                sy = cy + fy * radius

                nz = (rz2 + 1.0) * 0.5
                alpha = (0.3 + nz * 0.7) * (0.5 + total * 0.5)
                if alpha > 1.0:
                    alpha = 1.0

                sz = self._base_sizes[i] * (0.3 + nz * 0.7) * scale + total * 0.5

                rc = int(tr * alpha)
                gc = int(tg * alpha)
                bc = int(tb * alpha)
                if rc < 0:
                    rc = 0
                elif rc > 255:
                    rc = 255
                if gc < 0:
                    gc = 0
                elif gc > 255:
                    gc = 255
                if bc < 0:
                    bc = 0
                elif bc > 255:
                    bc = 255

                p.setPen(Qt.NoPen)
                p.setBrush(QColor(rc, gc, bc))
                p.drawEllipse(QPointF(sx, sy), sz, sz)

            if total > 0.15:
                ring_alpha = int(total * 150)
                if ring_alpha > 255:
                    ring_alpha = 255
                rp = QPen(QColor(tr, tg, tb, ring_alpha))
                rp.setWidthF(1.2)
                p.setPen(rp)
                p.setBrush(Qt.NoBrush)
                ring_r = radius * (1.0 + total * 0.15)
                p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

            if self._isListening:
                dot_alpha = int(min(200, self._mic_energy * 300 + 60))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(40, 200, 80, dot_alpha))
                p.drawEllipse(QPointF(18, self.height() - 55), 4, 4)

                label = _LISTENING_LABELS[self._listening_label_idx]
                font = QFont("Segoe UI", 10)
                p.setFont(font)
                p.setPen(QColor(tr, tg, tb, min(255, int(total * 300 + 80))))
                p.drawText(QPointF(0, self.height() - 18), self.width(), Qt.AlignHCenter, label)

            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 1))
            hit_r = radius * 1.3
            p.drawEllipse(QPointF(cx, cy), hit_r, hit_r)
            if self._isListening:
                p.drawRect(0, self.height() - 60, self.width(), 60)

            p.end()
        except Exception as e:
            logger.debug("Falha ao desenhar Jarvis: %s", e)

    def closeEvent(self, event):
        self._alive = False
        self._timer.stop()
        self._mic_monitor.stop()
        self.VISUALIZATION_STOPPED.emit()
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
