"""Vẽ bàn cờ Cờ Tỷ Phú 2D thành ảnh PNG bằng Pillow.

Dùng cho bot Telegram: mỗi lượt sinh một ảnh bàn cờ cho người chơi nhìn.
"""
from __future__ import annotations

import io
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from app.game.models import GameRoom, PlayerStatus, Tile, TileKind
from app.game.money import format_vnd

# ----- Kích thước -----
GRID = 7                       # 7x7 ô => viền 24 ô
CELL = 118                     # kích thước mỗi ô (px)
MARGIN = 22                    # lề ngoài
BOARD = GRID * CELL
SIZE = BOARD + MARGIN * 2

# ----- Màu -----
BG = (247, 244, 236)
INK = (33, 33, 33)
GREY = (120, 120, 120)
TILE_BG = (255, 255, 255)
CENTER_BG = (233, 242, 235)

GROUP_COLORS = {
    1: (140, 90, 60),
    2: (120, 190, 235),
    3: (215, 70, 145),
    4: (240, 150, 60),
    5: (225, 70, 70),
    6: (70, 175, 110),
}

PLAYER_COLORS = [
    (220, 50, 50),
    (40, 110, 220),
    (35, 165, 95),
    (240, 175, 30),
    (150, 70, 200),
    (30, 190, 200),
]

SPECIAL_LABEL = {
    TileKind.GO: ("XUẤT PHÁT", "★"),
    TileKind.CHANCE: ("Cơ hội", "?"),
    TileKind.TAX: ("Thuế", "¤"),
    TileKind.JAIL_VISIT: ("Thăm tù", "☞"),
    TileKind.GO_TO_JAIL: ("Vào tù", "→"),
    TileKind.FREE_PARKING: ("Bãi đỗ", "P"),
    TileKind.RAILROAD: ("", "▣"),
    TileKind.UTILITY: ("", "⚙"),
}


@lru_cache(maxsize=16)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = (
        ["DejaVuSans-Bold.ttf", "arialbd.ttf", "NotoSans-Bold.ttf"]
        if bold
        else ["DejaVuSans.ttf", "arial.ttf", "NotoSans-Regular.ttf"]
    )
    paths = [
        "/usr/share/fonts/truetype/dejavu/",
        "/usr/share/fonts/dejavu-sans-fonts/",
        "/usr/share/fonts/truetype/noto/",
        "C:/Windows/Fonts/",
        "",
    ]
    for name in names:
        for base in paths:
            try:
                return ImageFont.truetype(base + name, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _perimeter() -> list[tuple[int, int]]:
    """24 ô viền theo chiều kim đồng hồ, bắt đầu góc trên-trái (Xuất phát)."""
    pos: list[tuple[int, int]] = []
    for c in range(GRID):
        pos.append((0, c))
    for r in range(1, GRID):
        pos.append((r, GRID - 1))
    for c in range(GRID - 2, -1, -1):
        pos.append((GRID - 1, c))
    for r in range(GRID - 2, 0, -1):
        pos.append((r, 0))
    return pos


POSITIONS = _perimeter()


def _cell_xy(index: int) -> tuple[int, int]:
    row, col = POSITIONS[index % len(POSITIONS)]
    return MARGIN + col * CELL, MARGIN + row * CELL


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines[:3]


def _owner_index(room: GameRoom, tile: Tile) -> int | None:
    if tile.owner_id is None:
        return None
    for i, p in enumerate(room.players):
        if p.user_id == tile.owner_id:
            return i
    return None


def _draw_tile(draw: ImageDraw.ImageDraw, room: GameRoom, index: int, tile: Tile) -> None:
    x, y = _cell_xy(index)
    draw.rectangle([x, y, x + CELL, y + CELL], fill=TILE_BG, outline=INK, width=2)

    body_top = y + 6
    # Dải màu nhóm cho đất
    if tile.kind is TileKind.PROPERTY and tile.color_group in GROUP_COLORS:
        draw.rectangle(
            [x + 2, y + 2, x + CELL - 2, y + 24],
            fill=GROUP_COLORS[tile.color_group],
        )
        body_top = y + 28

    # Viền thể hiện chủ sở hữu
    owner = _owner_index(room, tile)
    if owner is not None:
        draw.rectangle(
            [x + 2, y + 2, x + CELL - 2, y + CELL - 2],
            outline=PLAYER_COLORS[owner % len(PLAYER_COLORS)],
            width=4,
        )

    # Nhà được vẽ thành các ô vuông xanh ngay dưới dải màu.
    if tile.kind is TileKind.PROPERTY and tile.houses == 5:
        draw.rectangle([x + 42, y + 27, x + 76, y + 43], fill=(205, 45, 45), outline=INK)
        draw.text((x + 53, y + 26), "H", font=_font(12, bold=True), fill=(255, 255, 255))
    elif tile.kind is TileKind.PROPERTY and tile.houses:
        for house in range(tile.houses):
            hx = x + 8 + house * 24
            hy = y + 27
            draw.rectangle([hx, hy, hx + 17, hy + 13], fill=(45, 165, 85), outline=INK)

    name_font = _font(13, bold=True)
    small = _font(12)
    label, symbol = SPECIAL_LABEL.get(tile.kind, ("", ""))
    title = tile.name

    lines = _wrap(draw, title, name_font, CELL - 12)
    ty = body_top
    for ln in lines:
        w = draw.textlength(ln, font=name_font)
        draw.text((x + (CELL - w) / 2, ty), ln, font=name_font, fill=INK)
        ty += 15

    if tile.kind in (TileKind.PROPERTY, TileKind.RAILROAD, TileKind.UTILITY) and tile.price:
        price = format_vnd(tile.price)
        w = draw.textlength(price, font=small)
        draw.text((x + (CELL - w) / 2, y + CELL - 20), price, font=small, fill=GREY)
    elif tile.kind is TileKind.TAX and tile.tax:
        price = "-" + format_vnd(tile.tax)
        w = draw.textlength(price, font=small)
        draw.text((x + (CELL - w) / 2, y + CELL - 20), price, font=small, fill=(200, 60, 60))

    if symbol:
        big = _font(26, bold=True)
        w = draw.textlength(symbol, font=big)
        draw.text((x + (CELL - w) / 2, y + CELL / 2 - 14), symbol, font=big, fill=GREY)


def _draw_players(draw: ImageDraw.ImageDraw, room: GameRoom) -> None:
    # Gồm nhiều quân trên cùng ô: xếp lưới nhỏ
    by_tile: dict[int, list[int]] = {}
    for i, p in enumerate(room.players):
        if p.status is PlayerStatus.BANKRUPT:
            continue
        by_tile.setdefault(p.position, []).append(i)

    r = 13
    token_font = _font(13, bold=True)
    for tile_index, players in by_tile.items():
        x, y = _cell_xy(tile_index)
        for slot, pidx in enumerate(players):
            ox = x + 16 + (slot % 3) * 34
            oy = y + CELL - 40 + (slot // 3) * 26
            color = PLAYER_COLORS[pidx % len(PLAYER_COLORS)]
            draw.ellipse([ox, oy, ox + 2 * r, oy + 2 * r], fill=color, outline=(255, 255, 255), width=2)
            num = str(pidx + 1)
            w = draw.textlength(num, font=token_font)
            draw.text((ox + r - w / 2, oy + r - 8), num, font=token_font, fill=(255, 255, 255))


def _draw_center(draw: ImageDraw.ImageDraw, room: GameRoom) -> None:
    left = MARGIN + CELL + 8
    top = MARGIN + CELL + 8
    right = MARGIN + BOARD - CELL - 8
    bottom = MARGIN + BOARD - CELL - 8
    draw.rectangle([left, top, right, bottom], fill=CENTER_BG, outline=(180, 200, 185), width=2)

    title_font = _font(34, bold=True)
    t = "CỜ TỶ PHÚ"
    w = draw.textlength(t, font=title_font)
    draw.text((left + (right - left - w) / 2, top + 16), t, font=title_font, fill=(60, 120, 80))

    sub_font = _font(15)
    cur = room.current_player.name if room.players else ""
    sub = f"➡ Lượt: {cur}"
    w = draw.textlength(sub, font=sub_font)
    draw.text((left + (right - left - w) / 2, top + 58), sub, font=sub_font, fill=INK)

    # Danh sách người chơi + tiền
    row_font = _font(14, bold=True)
    cash_font = _font(13)
    ly = top + 92
    for i, p in enumerate(room.players):
        color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        draw.ellipse([left + 18, ly, left + 36, ly + 18], fill=color, outline=(255, 255, 255), width=2)
        num = str(i + 1)
        w = draw.textlength(num, font=cash_font)
        draw.text((left + 27 - w / 2, ly + 2), num, font=cash_font, fill=(255, 255, 255))
        state = "💀" if p.status is PlayerStatus.BANKRUPT else "🔒" if p.status is PlayerStatus.JAILED else ""
        if p.rent_shields:
            state = f"{state} 🛡".strip()
        name = f"{p.name} {state}".strip()
        draw.text((left + 44, ly), name, font=row_font, fill=INK)
        houses = sum(min(room.board[index].houses, 4) for index in p.property_indexes)
        hotels = sum(room.board[index].houses == 5 for index in p.property_indexes)
        cash = f"{format_vnd(p.cash)} · {len(p.property_indexes)} đất · {houses}N/{hotels}KS"
        draw.text((left + 44, ly + 18), cash, font=cash_font, fill=GREY)
        ly += 46


def render_board(room: GameRoom) -> bytes:
    """Trả về ảnh PNG (bytes) của bàn cờ hiện tại."""
    img = Image.new("RGB", (SIZE, SIZE), BG)
    draw = ImageDraw.Draw(img)

    _draw_center(draw, room)
    for index, tile in enumerate(room.board):
        _draw_tile(draw, room, index, tile)
    _draw_players(draw, room)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
