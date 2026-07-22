"""Arcade View adapters used during the incremental scene migration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, cast

import arcade
from pyglet.event import EVENT_HANDLED

from perf_probe import PerfProbe
from .bootstrap import BootstrapRunner, BootstrapTaskLike


class LegacyGameWindow(Protocol):
    """Window surface consumed by :class:`GameRuntimeView`."""

    def apply_ui_viewport(self, width: int | None = None,
                          height: int | None = None) -> None: ...
    def on_draw(self) -> None: ...
    def on_update(self, delta_time: float) -> None: ...
    def on_resize(self, width: int, height: int) -> None: ...
    def on_mouse_scroll(self, x: float, y: float,
                        scroll_x: float, scroll_y: float) -> None: ...
    def on_mouse_motion(self, x: float, y: float,
                        dx: float, dy: float) -> None: ...
    def on_mouse_press(self, x: float, y: float,
                       button: int, modifiers: int) -> None: ...
    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float,
                      buttons: int, modifiers: int) -> None: ...
    def on_mouse_release(self, x: float, y: float,
                         button: int, modifiers: int) -> None: ...
    def on_key_press(self, symbol: int, modifiers: int) -> None: ...
    def on_key_release(self, symbol: int, modifiers: int) -> None: ...
    def on_joyhat_motion(self, joystick: object,
                         hat_x: int, hat_y: int) -> None: ...
    def on_joybutton_press(self, joystick: object, button: int) -> None: ...
    def on_text(self, text: str) -> None: ...


class GameRuntimeView(arcade.View):
    """Let a real Arcade View own draw/update while preserving RPGWindow APIs.

    The view is deliberately a thin compatibility boundary: saved games and
    button callbacks continue to target ``RPGWindow``, while future scenes can
    be moved behind their own views without another input or persistence
    rewrite.
    """

    @property
    def game(self) -> LegacyGameWindow:
        if self.window is None:
            raise RuntimeError("GameRuntimeView must be attached to a window")
        return cast(LegacyGameWindow, self.window)

    def on_show_view(self) -> None:
        self.game.apply_ui_viewport()

    def on_draw(self) -> bool:
        self.game.on_draw()
        # Window handlers remain registered underneath View handlers in
        # pyglet. Stop propagation so legacy on_draw runs exactly once.
        return EVENT_HANDLED

    def on_update(self, delta_time: float) -> bool:
        self.game.on_update(delta_time)
        return EVENT_HANDLED

    def on_resize(self, width: int, height: int) -> bool:
        self.game.on_resize(width, height)
        return EVENT_HANDLED

    # Arcade's base View implements input event stubs, so relying on pyglet to
    # fall through to the Window is not reliable. Explicit forwarding keeps
    # the existing input API working while this View owns the event stack.
    def on_mouse_scroll(self, x: float, y: float,
                        scroll_x: float, scroll_y: float) -> bool:
        self.game.on_mouse_scroll(x, y, scroll_x, scroll_y)
        return EVENT_HANDLED

    def on_mouse_motion(self, x: float, y: float,
                        dx: float, dy: float) -> bool:
        self.game.on_mouse_motion(x, y, dx, dy)
        return EVENT_HANDLED

    def on_mouse_press(self, x: float, y: float,
                       button: int, modifiers: int) -> bool:
        self.game.on_mouse_press(x, y, button, modifiers)
        return EVENT_HANDLED

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float,
                      buttons: int, modifiers: int) -> bool:
        self.game.on_mouse_drag(x, y, dx, dy, buttons, modifiers)
        return EVENT_HANDLED

    def on_mouse_release(self, x: float, y: float,
                         button: int, modifiers: int) -> bool:
        self.game.on_mouse_release(x, y, button, modifiers)
        return EVENT_HANDLED

    def on_key_press(self, symbol: int, modifiers: int) -> bool:
        self.game.on_key_press(symbol, modifiers)
        return EVENT_HANDLED

    def on_key_release(self, symbol: int, modifiers: int) -> bool:
        self.game.on_key_release(symbol, modifiers)
        return EVENT_HANDLED

    def on_joyhat_motion(self, joystick: object,
                         hat_x: int, hat_y: int) -> bool:
        self.game.on_joyhat_motion(joystick, hat_x, hat_y)
        return EVENT_HANDLED

    def on_joybutton_press(self, joystick: object, button: int) -> bool:
        self.game.on_joybutton_press(joystick, button)
        return EVENT_HANDLED

    def on_text(self, text: str) -> bool:
        self.game.on_text(text)
        return EVENT_HANDLED


class LoadingView(arcade.View):
    """Minimal responsive startup view for cooperative bootstrap tasks.

    The first task is not executed until this view has painted at least once,
    ensuring users see a responsive surface before heavyweight work begins.
    Input is intentionally ignored except for Escape-to-close; resize remains
    active throughout startup.
    """

    def __init__(
        self,
        tasks: Iterable[BootstrapTaskLike] | None = None,
        *,
        window: arcade.Window | None = None,
        runner: BootstrapRunner | None = None,
        total_tasks: int | None = None,
        step_budget_ms: float = 8.0,
        minimum_display_seconds: float = 0.0,
        on_complete: Callable[[], object] | None = None,
        on_error: Callable[[Exception], object] | None = None,
        probe: PerfProbe | None = None,
        title: str = "EMBER KINGDOM",
        subtitle: str = "Preparing your journey...",
        reduced_motion: bool = False,
    ) -> None:
        super().__init__(window)
        if runner is not None and tasks is not None:
            raise ValueError("pass tasks or runner, not both")
        if runner is None:
            if tasks is None:
                tasks = ()
            runner = BootstrapRunner(
                tasks, total_tasks=total_tasks, probe=probe,
            )
        self.runner = runner
        self.step_budget_ms = max(0.0, float(step_budget_ms))
        self.minimum_display_seconds = max(
            0.0, float(minimum_display_seconds)
        )
        self.on_complete_callback = on_complete
        self.on_error_callback = on_error
        self.probe = probe
        self.title = str(title)
        self.subtitle = str(subtitle)
        self.reduced_motion = bool(reduced_motion)
        self.elapsed = 0.0
        self._width = 1180
        self._height = 720
        self._has_drawn = False
        self._completion_dispatched = False
        self._error_dispatched = False
        self._callback_error: Exception | None = None
        self._title_text: arcade.Text | None = None
        self._subtitle_text: arcade.Text | None = None
        self._status_text: arcade.Text | None = None
        self._hint_text: arcade.Text | None = None

    @property
    def error(self) -> Exception | None:
        return self.runner.error or self._callback_error

    @property
    def progress(self) -> float | None:
        return self.runner.progress

    @property
    def current_label(self) -> str:
        return self.runner.current_label

    def on_show_view(self) -> None:
        if self.window is not None:
            self._width = max(1, self.window.width)
            self._height = max(1, self.window.height)
        if self.probe is not None:
            self.probe.mark("loading.show")

    def _dispatch_error(self, error: Exception) -> None:
        if self._error_dispatched:
            return
        self._error_dispatched = True
        if self.probe is not None:
            self.probe.mark(
                "loading.error", error_type=type(error).__name__,
            )
        if self.on_error_callback is not None:
            try:
                self.on_error_callback(error)
            except Exception as callback_error:
                self._callback_error = callback_error

    def _dispatch_completion(self) -> None:
        if self._completion_dispatched:
            return
        self._completion_dispatched = True
        if self.probe is not None:
            self.probe.mark("loading.complete")
        if self.on_complete_callback is not None:
            try:
                self.on_complete_callback()
            except Exception as error:
                self._callback_error = error
                self._dispatch_error(error)

    def on_update(self, delta_time: float) -> bool:
        self.elapsed += max(0.0, float(delta_time))
        if not self._has_drawn or self.error is not None:
            if self.error is not None:
                self._dispatch_error(self.error)
            return EVENT_HANDLED
        if self._title_text is None:
            # Build persistent glyph layouts only after the texture-free first
            # frame has been presented. arcade.draw_text would recreate these
            # objects on every loading frame and dominated startup latency.
            self._create_text_objects()
            return EVENT_HANDLED
        if not self.runner.done:
            self.runner.step(self.step_budget_ms)
        if self.runner.error is not None:
            self._dispatch_error(self.runner.error)
        elif (self.runner.done
              and self.elapsed >= self.minimum_display_seconds):
            self._dispatch_completion()
        return EVENT_HANDLED

    def on_draw(self) -> bool:
        width, height = float(self._width), float(self._height)
        arcade.draw_rect_filled(
            arcade.LBWH(0, 0, width, height), (5, 8, 14, 255),
        )
        center_x = width / 2
        center_y = height / 2
        error = self.error
        self._draw_progress(center_x, center_y - 12, width)
        if self._title_text is not None:
            assert self._subtitle_text is not None
            assert self._status_text is not None
            assert self._hint_text is not None
            if error is None:
                self._title_text.text = self.title
                self._title_text.color = (230, 190, 105, 255)
                self._title_text.font_size = 26
                self._subtitle_text.text = self.subtitle
                self._status_text.text = self.current_label
                self._hint_text.text = ""
            else:
                self._title_text.text = "STARTUP ERROR"
                self._title_text.color = (235, 105, 105, 255)
                self._title_text.font_size = 22
                self._subtitle_text.text = ""
                self._status_text.text = f"{type(error).__name__}: {error}"
                self._hint_text.text = "Press Esc to close"
            for label in (
                    self._title_text, self._subtitle_text,
                    self._status_text, self._hint_text):
                label.x = center_x
            self._title_text.y = center_y + 72
            self._subtitle_text.y = center_y + 28
            self._status_text.y = center_y - 48
            self._hint_text.y = center_y - 76
            self._title_text.draw()
            self._subtitle_text.draw()
            self._status_text.draw()
            self._hint_text.draw()
        if not self._has_drawn:
            self._has_drawn = True
            if self.probe is not None:
                self.probe.mark("loading.first_frame")
        return EVENT_HANDLED

    def _create_text_objects(self) -> None:
        common = dict(
            anchor_x="center", anchor_y="center",
            font_name=("Microsoft JhengHei", "Arial"),
        )
        self._title_text = arcade.Text(
            self.title, 0, 0, (230, 190, 105, 255), 26,
            bold=True, **common,
        )
        self._subtitle_text = arcade.Text(
            self.subtitle, 0, 0, (204, 210, 220, 255), 14, **common,
        )
        self._status_text = arcade.Text(
            self.current_label, 0, 0, (146, 158, 174, 255), 12,
            width=max(240, self._width - 160), multiline=True,
            align="center", **common,
        )
        self._hint_text = arcade.Text(
            "", 0, 0, (146, 158, 174, 255), 11, **common,
        )

    def _draw_progress(self, center_x: float, center_y: float,
                       window_width: float) -> None:
        width = max(180.0, min(520.0, window_width - 120.0))
        height = 8.0
        left = center_x - width / 2
        arcade.draw_rect_filled(
            arcade.LBWH(left, center_y - height / 2, width, height),
            (28, 35, 46, 255),
        )
        progress = self.progress
        if progress is not None:
            fill_width = width * max(0.0, min(1.0, progress))
            if fill_width > 0:
                arcade.draw_rect_filled(
                    arcade.LBWH(
                        left, center_y - height / 2, fill_width, height,
                    ),
                    (203, 145, 72, 255),
                )
            return
        marker_width = min(96.0, width * .24)
        if self.reduced_motion:
            marker_left = left
        else:
            travel = max(0.0, width - marker_width)
            phase = (self.elapsed * 0.8) % 2.0
            triangle = phase if phase <= 1.0 else 2.0 - phase
            marker_left = left + travel * triangle
        arcade.draw_rect_filled(
            arcade.LBWH(
                marker_left, center_y - height / 2, marker_width, height,
            ),
            (203, 145, 72, 255),
        )

    def on_resize(self, width: int, height: int) -> bool:
        self._width = max(1, int(width))
        self._height = max(1, int(height))
        return EVENT_HANDLED

    def on_key_press(self, symbol: int, modifiers: int) -> bool:
        del modifiers
        if symbol == arcade.key.ESCAPE and self.window is not None:
            self.window.close()
        return EVENT_HANDLED


__all__ = ["GameRuntimeView", "LegacyGameWindow", "LoadingView"]
