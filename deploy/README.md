# Triển khai server

Hai cách chạy bot 24/7 trên server Linux.

## Cách A — Docker (khuyến nghị)

Yêu cầu Docker và Docker Compose.

```bash
cp .env.example .env
# điền BOT_TOKEN mới
docker compose up -d --build
docker compose logs -f bot
```

Dữ liệu SQLite lưu trong volume `bot-data`, không mất khi container khởi động lại.

Cập nhật phiên bản mới:

```bash
git pull
docker compose up -d --build
```

## Cách B — systemd (không dùng Docker)

Chạy trực tiếp bằng Python + systemd.

```bash
sudo bash deploy/install-server.sh
sudo nano /opt/ty-phu-bot/.env   # điền BOT_TOKEN mới
sudo systemctl start ty-phu-bot
sudo systemctl status ty-phu-bot
journalctl -u ty-phu-bot -f
```

Cập nhật phiên bản mới:

```bash
sudo bash deploy/install-server.sh
sudo systemctl restart ty-phu-bot
```

## Lưu ý quan trọng

- Chỉ chạy **một instance** cho mỗi token khi dùng long polling.
- Không commit file `.env`.
- Thu hồi token cũ bằng `/revoke` trong @BotFather nếu đã lộ.
- Sao lưu định kỳ file SQLite (`data/ty_phu.db`) để giữ ⭐, inventory và leaderboard.
