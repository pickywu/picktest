"""Incremental runtime adapters for scenes, responsive layout, and sprite batches.

The game can keep its existing enum dispatch while screens migrate one by one
to registered views.  These adapters intentionally have no knowledge of RPG
state, so they are safe to reuse in future ``arcade.View`` classes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Hashable, Protocol, TypeVar

import arcade

from .bootstrap import (
    AssetWarmupQueue,
    WarmupStepResult,
    WarmupTask,
)


SceneKey = TypeVar("SceneKey", bound=Hashable)


class SceneView(Protocol):
    """Small compatibility surface shared by enum scenes and Arcade views."""

    def on_enter(self, previous: object | None) -> None: ...
    def on_exit(self, upcoming: object) -> None: ...
    def on_update(self, delta_time: float) -> None: ...
    def on_draw(self) -> None: ...


class SceneController(Generic[SceneKey]):
    """Own the active scene while allowing gradual view registration."""

    def __init__(self, initial: SceneKey) -> None:
        self.current = initial
        self.previous: SceneKey | None = None
        self._views: dict[SceneKey, SceneView] = {}

    def register(self, scene: SceneKey, view: SceneView) -> None:
        self._views[scene] = view

    def change(self, scene: SceneKey) -> bool:
        if scene == self.current:
            return False
        old_scene = self.current
        old_view = self._views.get(old_scene)
        if old_view is not None:
            old_view.on_exit(scene)
        self.previous = old_scene
        self.current = scene
        new_view = self._views.get(scene)
        if new_view is not None:
            new_view.on_enter(old_scene)
        return True

    def update_registered_view(self, delta_time: float) -> bool:
        view = self._views.get(self.current)
        if view is None:
            return False
        view.on_update(delta_time)
        return True

    def draw_registered_view(self) -> bool:
        view = self._views.get(self.current)
        if view is None:
            return False
        view.on_draw()
        return True


@dataclass(frozen=True)
class CanvasViewport:
    left: float
    bottom: float
    width: float
    height: float
    scale: float


@dataclass(frozen=True)
class ResponsiveCanvas:
    """Map one authored canvas into any client area without cropping."""

    width: float
    height: float

    def fit(self, client_width: float, client_height: float) -> CanvasViewport:
        client_width = max(1.0, float(client_width))
        client_height = max(1.0, float(client_height))
        scale = min(client_width / self.width, client_height / self.height)
        width = self.width * scale
        height = self.height * scale
        return CanvasViewport(
            (client_width - width) / 2,
            (client_height - height) / 2,
            width,
            height,
            scale,
        )

    @staticmethod
    def to_canvas(x: float, y: float,
                  viewport: CanvasViewport) -> tuple[float, float]:
        return (
            (x - viewport.left) / viewport.scale,
            (y - viewport.bottom) / viewport.scale,
        )


class SpriteBatchLayer:
    """Named sprites backed by one ``SpriteList`` batch draw."""

    def __init__(self) -> None:
        self.sprites = arcade.SpriteList(use_spatial_hash=False)
        self._named: dict[str, arcade.Sprite] = {}

    def begin_frame(self) -> None:
        """Hide retained sprites; ``set_texture`` opts active ones back in."""
        for sprite in self._named.values():
            sprite.visible = False

    def set_texture(self, name: str, texture: arcade.Texture, *,
                    center_x: float, center_y: float,
                    width: float, height: float) -> arcade.Sprite:
        sprite = self._named.get(name)
        if sprite is None:
            sprite = arcade.Sprite(texture)
            self._named[name] = sprite
            self.sprites.append(sprite)
        elif sprite.texture is not texture:
            sprite.texture = texture
        # Avoid marking retained vertex buffers dirty when a frame reuses the
        # exact same scene geometry.
        if sprite.center_x != center_x:
            sprite.center_x = center_x
        if sprite.center_y != center_y:
            sprite.center_y = center_y
        if sprite.width != width:
            sprite.width = width
        if sprite.height != height:
            sprite.height = height
        sprite.visible = True
        return sprite

    def draw(self) -> None:
        self.sprites.draw()


__all__ = [
    "AssetWarmupQueue", "CanvasViewport", "ResponsiveCanvas",
    "SceneController", "SceneView", "SpriteBatchLayer", "WarmupStepResult",
    "WarmupTask",
]
