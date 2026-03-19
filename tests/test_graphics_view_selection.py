from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QPixmap
from pytestqt.qtbot import QtBot

from vsview.app.views.video import GraphicsView


def _view_pos_for_image_point(view: GraphicsView, point: QPointF) -> QPointF:
    return QPointF(view.mapFromScene(view.pixmap_item.mapToScene(point)))


def test_map_to_image_is_stable_with_sar(qtbot: QtBot) -> None:
    view = GraphicsView()
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()

    pixmap = QPixmap(100, 80)
    pixmap.fill(Qt.GlobalColor.white)
    view.set_pixmap(pixmap)
    view.set_sar(2.0)
    view._set_sar_applied(True)

    qtbot.waitUntil(view.isVisible, timeout=5000)

    image_point = QPointF(25, 30)
    mapped = view.map_to_image(_view_pos_for_image_point(view, image_point))

    assert mapped.toPoint() == image_point.toPoint()


def test_rect_selection_drag_creates_pixel_rect(qtbot: QtBot) -> None:
    view = GraphicsView()
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()

    pixmap = QPixmap(120, 90)
    pixmap.fill(Qt.GlobalColor.white)
    view.set_pixmap(pixmap)
    view.rect_selection_enabled = True

    qtbot.waitUntil(view.isVisible, timeout=5000)

    start = _view_pos_for_image_point(view, QPointF(10, 12)).toPoint()
    end = _view_pos_for_image_point(view, QPointF(42, 36)).toPoint()

    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)  # type: ignore[no-untyped-call]
    qtbot.mouseMove(view.viewport(), pos=end)  # type: ignore[no-untyped-call]
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)  # type: ignore[no-untyped-call]

    assert view.rect_selection == QRect(10, 12, 32, 24)
