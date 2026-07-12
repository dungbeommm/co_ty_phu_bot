from app.game.models import Tile, TileKind


def create_board() -> list[Tile]:
    """Bàn 24 ô, tối ưu cho ván Telegram 15–40 phút."""
    return [
        Tile("Xuất phát", TileKind.GO),
        Tile("Cà Mau", TileKind.PROPERTY, 600_000, 60_000, color_group=1),
        Tile("Cơ hội", TileKind.CHANCE),
        Tile("Bạc Liêu", TileKind.PROPERTY, 600_000, 60_000, color_group=1),
        Tile("Thuế", TileKind.TAX, tax=1_000_000),
        Tile("Ga Hà Nội", TileKind.RAILROAD, 2_000_000, 250_000),
        Tile("Nha Trang", TileKind.PROPERTY, 1_000_000, 100_000, color_group=2),
        Tile("Cơ hội", TileKind.CHANCE),
        Tile("Đà Nẵng", TileKind.PROPERTY, 1_200_000, 120_000, color_group=2),
        Tile("Thăm tù", TileKind.JAIL_VISIT),
        Tile("Huế", TileKind.PROPERTY, 1_400_000, 140_000, color_group=3),
        Tile("Điện lực", TileKind.UTILITY, 1_500_000, 400_000),
        Tile("Vinh", TileKind.PROPERTY, 1_400_000, 140_000, color_group=3),
        Tile("Hải Phòng", TileKind.PROPERTY, 1_600_000, 160_000, color_group=3),
        Tile("Ga Sài Gòn", TileKind.RAILROAD, 2_000_000, 250_000),
        Tile("Cần Thơ", TileKind.PROPERTY, 1_800_000, 180_000, color_group=4),
        Tile("Cơ hội", TileKind.CHANCE),
        Tile("Biên Hòa", TileKind.PROPERTY, 1_800_000, 180_000, color_group=4),
        Tile("Bãi đỗ", TileKind.FREE_PARKING),
        Tile("Vũng Tàu", TileKind.PROPERTY, 2_200_000, 220_000, color_group=5),
        Tile("Vào tù", TileKind.GO_TO_JAIL),
        Tile("Đà Lạt", TileKind.PROPERTY, 2_200_000, 220_000, color_group=5),
        Tile("Thuế xa xỉ", TileKind.TAX, tax=1_500_000),
        Tile("Hà Nội", TileKind.PROPERTY, 2_800_000, 280_000, color_group=6),
    ]
