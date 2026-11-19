"""Native, interactive map board for the VTT panel."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PyQt6.QtWidgets import QSizePolicy, QWidget

from assistuff.visual.vtt import MapPoint, Position, VttScene

_TERRAIN_COLORS = {
    "field": QColor("#718657"),
    "forest": QColor("#315c43"),
    "water": QColor("#306a83"),
    "ridge": QColor("#78684d"),
    "road": QColor("#927d57"),
}
_TERRAIN_NAMES = {
    "field": "Open ground",
    "forest": "Forest · 2 MP",
    "water": "Water · blocked",
    "ridge": "Ridge · blocked",
    "road": "Road",
}


class VttMapWidget(QWidget):
    tile_selected = pyqtSignal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene: VttScene | None = None
        self._selected_position: Position | None = None
        self.setMinimumSize(520, 390)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    def set_scene(
        self,
        scene: VttScene,
        selected_position: Position | None = None,
    ) -> None:
        self._scene = scene
        self._selected_position = selected_position
        self.update()

    def set_selected_position(self, position: Position | None) -> None:
        self._selected_position = position
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(600, 440)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(event.rect(), QColor("#0b1710"))
        scene = self._scene
        if scene is None:
            painter.setPen(QColor("#9ac8aa"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No scene loaded")
            return

        game_map = scene.map
        x0, y0, cell = self._grid_geometry()
        painter.setPen(QColor("#eff7ed"))
        title_font = QFont(self.font())
        title_font.setBold(True)
        title_font.setPointSize(13)
        painter.setFont(title_font)
        painter.drawText(18, 27, "SCENE BOARD")

        subtitle_font = QFont(self.font())
        subtitle_font.setPointSize(9)
        painter.setFont(subtitle_font)
        painter.setPen(QColor("#aac3ae"))
        painter.drawText(
            18,
            46,
            f"Turn {scene.game.turn}  ·  "
            f"{scene.game.moves_remaining}/{scene.game.moves_per_turn} MP  ·  "
            f"Player {scene.game.player_label}",
        )

        reachable = scene.game.reachable_costs()
        points = {point.position: point for point in game_map.points}
        players_by_position = {}
        for index, player in enumerate(scene.game.players):
            players_by_position.setdefault(player.position, []).append((index, player))
        npcs_by_position = {}
        for npc in scene.npcs:
            npcs_by_position.setdefault(npc.position, []).append(npc)
        for y, row in enumerate(game_map.tiles):
            painter.setPen(QColor("#b7c9b5"))
            painter.drawText(
                QRectF(x0 - 27, y0 + y * cell, 22, cell),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                chr(65 + y),
            )
            for x, terrain in enumerate(row):
                position = (x, y)
                rect = QRectF(x0 + x * cell, y0 + y * cell, cell, cell)
                self._draw_tile(painter, rect, terrain, cell)
                if position in reachable:
                    self._draw_reachable(painter, rect, cell, reachable[position])
                if position == self._selected_position:
                    painter.setPen(QPen(QColor("#fff1a1"), 3))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 5, 5)
                if position == game_map.exit:
                    self._draw_marker(painter, rect, "E", QColor("#f5a46f"), cell, corner=True)
                point = points.get(position)
                if point:
                    discovered = point.point_id in scene.game.discovered_points
                    marker = point.kind[0].upper() if discovered else "?"
                    self._draw_marker(
                        painter,
                        rect,
                        marker,
                        QColor("#ffe39a"),
                        cell,
                        corner=True,
                    )
                for index, player in players_by_position.get(position, []):
                    if player.player_id != scene.game.active_player_id:
                        self._draw_marker(
                            painter,
                            rect,
                            str(index + 1),
                            QColor("#b9d8ff"),
                            cell,
                            corner=False,
                        )
                for _ in npcs_by_position.get(position, []):
                    self._draw_marker(
                        painter,
                        rect,
                        "N",
                        QColor("#f2adcb"),
                        cell,
                        corner=False,
                    )
                if position == scene.game.player_position:
                    self._draw_player(painter, rect, cell)
                painter.setPen(QColor("#d4dfca"))
                painter.drawText(
                    QRectF(rect.left(), y0 + game_map.height * cell + 2, cell, 18),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    str(x + 1),
                )

        legend_y = min(self.height() - 13, y0 + game_map.height * cell + 29)
        painter.setPen(QColor("#aac3ae"))
        painter.drawText(
            18,
            legend_y,
            "Field  ·  Forest 2 MP  ·  Road 1 MP  ·  "
            "Water / ridge blocked  ·  ? point  ·  P active  ·  N NPC  ·  E exit",
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._scene is None:
            return
        x0, y0, cell = self._grid_geometry()
        point = event.position()
        x = int((point.x() - x0) // cell)
        y = int((point.y() - y0) // cell)
        if 0 <= x < self._scene.map.width and 0 <= y < self._scene.map.height:
            self.tile_selected.emit(x, y)
        else:
            super().mousePressEvent(event)

    def _grid_geometry(self) -> tuple[int, int, int]:
        if self._scene is None:
            return 0, 0, 1
        game_map = self._scene.map
        usable_width = max(1, self.width() - 76)
        usable_height = max(1, self.height() - 105)
        cell = max(
            18,
            min(
                58,
                int(
                    min(
                        usable_width / game_map.width,
                        usable_height / game_map.height,
                    )
                ),
            ),
        )
        grid_width = cell * game_map.width
        grid_height = cell * game_map.height
        x0 = max(38, (self.width() - grid_width) // 2)
        y0 = 62 + max(0, (self.height() - 90 - grid_height) // 2)
        return x0, y0, cell

    def _draw_tile(
        self,
        painter: QPainter,
        rect: QRectF,
        terrain: str,
        cell: int,
    ) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_TERRAIN_COLORS[terrain])
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)
        inset = rect.adjusted(cell * 0.22, cell * 0.22, -cell * 0.22, -cell * 0.22)
        if terrain == "field":
            painter.setBrush(QColor("#a8bb7e"))
            painter.drawEllipse(QPointF(inset.center().x(), inset.center().y()), 2, 2)
            painter.drawEllipse(QPointF(inset.left(), inset.bottom()), 1.5, 1.5)
        elif terrain == "forest":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#72a66a"))
            path = QPainterPath()
            path.moveTo(inset.center().x(), inset.top())
            path.lineTo(inset.right(), inset.bottom())
            path.lineTo(inset.left(), inset.bottom())
            path.closeSubpath()
            painter.drawPath(path)
            painter.setPen(QPen(QColor("#c8b78b"), max(1, cell * 0.045)))
            painter.drawLine(
                QPointF(inset.center().x(), inset.bottom()),
                QPointF(inset.center().x(), rect.bottom() - 4),
            )
        elif terrain == "water":
            painter.setPen(QPen(QColor("#a3d8df"), max(1, cell * 0.045)))
            for offset in (-4, 3):
                y = inset.center().y() + offset
                painter.drawLine(
                    QPointF(inset.left(), y),
                    QPointF(inset.right(), y),
                )
        elif terrain == "ridge":
            painter.setPen(QPen(QColor("#d8c49b"), max(1, cell * 0.055)))
            path = QPainterPath()
            path.moveTo(inset.left(), inset.bottom())
            path.lineTo(inset.center().x(), inset.top())
            path.lineTo(inset.right(), inset.bottom())
            painter.drawPath(path)
        else:
            painter.setPen(QPen(QColor("#d6bd83"), max(2, cell * 0.12)))
            painter.drawLine(
                QPointF(rect.left() + 5, rect.center().y()),
                QPointF(rect.right() - 5, rect.center().y()),
            )
        painter.setPen(QPen(QColor("#17251b"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)

    def _draw_reachable(
        self,
        painter: QPainter,
        rect: QRectF,
        cell: int,
        cost: int,
    ) -> None:
        painter.setPen(QPen(QColor("#c6f4a8"), 2, Qt.PenStyle.DashLine))
        painter.setBrush(QColor(160, 223, 160, 30))
        painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 5, 5)
        painter.setPen(QColor("#f5ffe7"))
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(max(7, int(cell * 0.16)))
        painter.setFont(font)
        painter.drawText(
            QRectF(rect.left() + 2, rect.bottom() - cell * 0.36, cell - 4, cell * 0.26),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            str(cost),
        )

    def _draw_marker(
        self,
        painter: QPainter,
        rect: QRectF,
        label: str,
        color: QColor,
        cell: int,
        *,
        corner: bool,
    ) -> None:
        diameter = max(13, int(cell * 0.36))
        marker = QRectF(
            rect.right() - diameter - 2 if corner else rect.center().x() - diameter / 2,
            rect.top() + 2 if corner else rect.center().y() - diameter / 2,
            diameter,
            diameter,
        )
        painter.setPen(QPen(QColor("#1a241b"), 1))
        painter.setBrush(color)
        painter.drawEllipse(marker)
        painter.setPen(QColor("#1a241b"))
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(max(7, int(diameter * 0.48)))
        painter.setFont(font)
        painter.drawText(marker, Qt.AlignmentFlag.AlignCenter, label)

    def _draw_player(self, painter: QPainter, rect: QRectF, cell: int) -> None:
        diameter = max(19, int(cell * 0.58))
        marker = QRectF(
            rect.center().x() - diameter / 2,
            rect.center().y() - diameter / 2,
            diameter,
            diameter,
        )
        painter.setPen(QPen(QColor("#fff8cf"), 2))
        painter.setBrush(QColor("#f2d86c"))
        painter.drawEllipse(marker)
        painter.setPen(QColor("#1c2411"))
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(max(8, int(diameter * 0.45)))
        painter.setFont(font)
        painter.drawText(marker, Qt.AlignmentFlag.AlignCenter, "P")


def point_at(scene: VttScene, position: Position) -> MapPoint | None:
    return next(
        (point for point in scene.map.points if point.position == position),
        None,
    )


def terrain_name(terrain: str) -> str:
    return _TERRAIN_NAMES[terrain]
