def format_vnd(amount: int) -> str:
    """Format integer đồng using Vietnamese thousands separators."""
    return f"{amount:,}".replace(",", ".") + "₫"
