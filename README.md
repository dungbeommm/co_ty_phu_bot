# 🎲 Cờ Tỷ Phú Telegram Bot — Python

Bot nhóm Telegram viết bằng **Python 3.11+ / aiogram 3 / SQLite**.

## Có sẵn

- Phòng theo từng nhóm: `/newgame`, `/join`, `/startgame`, `/cancel`
- Xúc xắc, qua Start, mua đất bằng nút, tiền thuê, thuế, Cơ hội, tù, phá sản
- Xếp hạng cuối ván và quy đổi tài sản thành ⭐
- Hồ sơ, leaderboard, shop và inventory ngoài ván
- Lock riêng mỗi phòng để tránh hai người thao tác cùng lúc
- Tiền Việt Nam (VNĐ): ví dụ `15.000.000₫`
- SQLite WAL + transaction khi mua item
- Docker, CI, GHCR và workflow smoke test 10 phút

## Bảo mật

Token từng dán vào chat/GitHub phải được thu hồi bằng `/revoke` trong @BotFather. Chỉ dùng token mới qua `.env` hoặc GitHub Actions Secret. Không commit `.env`.

## Chạy local

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
# điền BOT_TOKEN mới vào .env
python -m app.main
```

## Docker

```bash
cp .env.example .env
# điền BOT_TOKEN mới
docker compose up -d --build
docker compose logs -f bot
```

## GitHub

```bash
git init
git add .
git commit -m "feat: complete Python Telegram ty-phu bot"
git branch -M main
git remote add origin https://github.com/USERNAME/ty-phu-bot-python.git
git push -u origin main
```

- Chỉ có một workflow `bot.yml`: push/PR tự chạy kiểm thử.
- `Actions → Test and smoke-test bot → Run workflow` chạy thử bot 30 giây. Trước đó tạo Secret `BOT_TOKEN` trong `Settings → Secrets and variables → Actions`.
- Docker image có thể build trực tiếp bằng `docker compose`; workflow này không publish image.

> GitHub Actions không phải hosting 24/7. Dùng image GHCR trên VPS/Render/Railway/Fly.io. Chỉ chạy một instance khi dùng long polling + SQLite.

## Kinh tế VNĐ

- Vốn đầu ván: `15.000.000₫`
- Qua Xuất phát: `+2.000.000₫`
- Giá đất: `600.000₫`–`2.800.000₫`
- Phí ra tù: `500.000₫`
- Mỗi `1.000.000₫` tài sản quy đổi thêm `1⭐` cuối ván.

## Lệnh

`/help`, `/newgame`, `/join`, `/startgame`, `/roll`, `/status`, `/cancel`, `/profile`, `/shop`, `/buy ITEM_ID`, `/leaderboard`

## Giới hạn hiện tại

Ván active lưu trong RAM nên restart sẽ hủy ván đang chơi. Ví ⭐, inventory và leaderboard được giữ trong SQLite.
