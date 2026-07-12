from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Item:
    item_id: str
    name: str
    cost: int
    description: str


ITEMS = {
    item.item_id: item
    for item in [
        Item("CAP200", "💵 Vốn dày", 40, "Đầu ván +2.000.000₫ (mở rộng sau)"),
        Item("SHIELD1", "🛡 Lá chắn thuê", 50, "Miễn một lần thuê (mở rộng sau)"),
        Item("JAILKEY", "🔓 Thẻ ra tù", 35, "Ra tù miễn phí (mở rộng sau)"),
        Item("REROLL", "🎲 Xúc xắc lại", 45, "Xúc xắc lại một lần (mở rộng sau)"),
        Item("SKIN_CAR", "🚗 Skin xe", 30, "Vật phẩm trang trí"),
    ]
}


def shop_text() -> str:
    lines = ["🛒 SHOP NGOÀI VÁN", "Mua bằng: /buy ITEM_ID", ""]
    lines.extend(f"• {i.item_id} — {i.name} — {i.cost}⭐\n  {i.description}" for i in ITEMS.values())
    return "\n".join(lines)
