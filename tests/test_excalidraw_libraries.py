"""Excalidraw library parsing stays offline and conservative."""

from __future__ import annotations

from engine import excalidraw_libraries as ex


def test_parse_excalidrawlib_items_and_preview():
    data = {
        "type": "excalidrawlib",
        "version": 2,
        "source": "https://excalidraw.com",
        "libraryItems": [
            {
                "id": "heart",
                "name": "Heart",
                "status": "published",
                "elements": [
                    {
                        "type": "rectangle",
                        "x": 10,
                        "y": 20,
                        "width": 80,
                        "height": 40,
                        "strokeColor": "#c92a2a",
                        "backgroundColor": "#ffc9c9",
                    },
                    {
                        "type": "line",
                        "x": 10,
                        "y": 20,
                        "points": [[0, 0], [30, 20], [60, 0]],
                        "strokeColor": "#c92a2a",
                    },
                    {
                        "type": "text",
                        "x": 15,
                        "y": 75,
                        "fontSize": 18,
                        "text": "love",
                        "strokeColor": "#e6edf3",
                    },
                ],
            }
        ],
    }
    pack = ex.parse(data, path="libraries/excalidraw/valentine.excalidrawlib")
    assert pack.name == "valentine"
    assert pack.items[0].elements == 3
    assert pack.items[0].types == {"rectangle": 1, "line": 1, "text": 1}
    svg = ex.preview_svg(data["libraryItems"][0]["elements"])
    assert "<rect" in svg and "<polyline" in svg and "love" in svg


def test_excalidraw_paths_are_confined_to_libraries():
    try:
        ex.files("../secrets")
    except ValueError as e:
        assert "libraries" in str(e)
    else:
        raise AssertionError("unsafe path should fail before any network call")
