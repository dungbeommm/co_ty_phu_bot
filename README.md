# 🎲 Cờ Tỷ Phú Telegram Bot — Python

Bot nhóm Telegram viết bằng **Python 3.11+ / aiogram 3 / SQLite**.

## Có sẵn

- Phòng theo từng nhóm: `/newgame`, `/join`, `/startgame`, `/cancel`
- Menu nút bấm theo từng giai đoạn: tham gia, bắt đầu, xúc xắc, mua/bỏ và trạng thái
- Mỗi topic có ván riêng; có thể giới hạn topic bằng `ALLOWED_TOPIC_IDS`
- Chỉ người chơi được bấm nút game; menu cũ tự biến mất sau thao tác hợp lệ
- Mỗi lượt chỉ gửi một ảnh kèm kết quả/menu để tránh giới hạn tin nhắn Telegram
- Tự chờ theo `retry_after` khi Telegram bật flood control; menu cũ không thể bấm lặp
- Bot chỉ tự xoá menu do chính bot gửi, không cần quyền admin
- Xúc xắc, qua Start, mua đất bằng nút, tiền thuê, thuế, Cơ hội, tù, phá sản
- **Bàn cờ 2D**: mỗi lượt /roll, /status, /startgame bot gửi ảnh bàn cờ (vị trí quân, chủ đất, tiền mặt)
- Xếp hạng cuối ván và quy đổi tài sản thành ⭐
- Hồ sơ, leaderboard, shop và inventory ngoài ván
- Lock riêng mỗi phòng để tránh hai người thao tác cùng lúc
- Tiền Việt Nam (VNĐ): ví dụ `15.000.000₫`
- SQLite WAL + transaction khi mua item
- Docker, CI, GHCR và workflow smoke test 10 phút

## Bảo mật

Không cần Secret Manager hay biến môi trường chứa token. Chạy `python setup-token.py` để
lưu token vào `bot_token.txt` trên máy chạy bot. File này được bỏ qua bởi Git và nên đặt
quyền `600` trên Linux. Token từng bị lộ phải được `/revoke` trong @BotFather.

## Chạy local

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python setup-token.py
python -m app.main
```

## Test và chạy trong VS Code

1. Mở thư mục project bằng VS Code.
2. Cài các extension được đề xuất: Python, Pylance, Debugpy.
3. Mở Command Palette (`Ctrl+Shift+P`) → `Python: Create Environment` → chọn `.venv`.
4. Mở Terminal và chạy `pip install -r requirements-dev.txt`.
5. Chạy `python setup-token.py` rồi nhập token BotFather; không cần tạo Secret.
6. Mở biểu tượng **Testing** ở thanh bên → bấm **Run All Tests**.
7. Muốn chạy bot: mở **Run and Debug** → chọn `Bot: chạy Telegram` → nhấn `F5`.

Cũng có thể dùng `Terminal → Run Task`:

- `Test: chạy toàn bộ`
- `Bot: chạy`
- `Python: cài thư viện`

## Chạy trên server (24/7)

Hai cách deploy, chi tiết trong `deploy/README.md`.

### Cách A — Docker Compose (khuyến nghị)

```bash
python3 setup-token.py
docker compose up -d --build
docker compose logs -f bot
```

Dữ liệu SQLite nằm trong volume `bot-data`, có healthcheck và tự khởi động lại.

### Cách B — systemd (Python thuần, không Docker)

```bash
sudo bash deploy/install-server.sh
sudo systemctl start ty-phu-bot
sudo systemctl status ty-phu-bot
journalctl -u ty-phu-bot -f
```

Bot có graceful shutdown: khi `docker stop` hoặc `systemctl stop`, nó dừng polling và đóng session an toàn.

### Makefile (dùng cho cả local và server)

```bash
make install        # tạo .venv và cài thư viện
make dev-install    # cài kèm ruff
make run            # chạy bot (cần bot_token.txt)
make test           # chạy unit test
make docker-up      # chạy bằng Docker Compose
make docker-logs    # xem log
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

- Workflow `bot.yml` chỉ biên dịch và chạy unit test, không cần token hay GitHub Secret.
- Docker image có thể build trực tiếp bằng `docker compose`; workflow này không publish image.

> GitHub Actions không phải hosting 24/7. Dùng image GHCR trên VPS/Render/Railway/Fly.io. Chỉ chạy một instance khi dùng long polling + SQLite.

## Kinh tế VNĐ

- Vốn đầu ván: `15.000.000₫`
- Qua Xuất phát: `+2.000.000₫`
- Giá đất: `600.000₫`–`2.800.000₫`
- Phí ra tù: `500.000₫`
- Mỗi `1.000.000₫` tài sản quy đổi thêm `1⭐` cuối ván.
- Lần đầu tới đất chưa có chủ là lần mua đất. Chỉ từ lần thứ hai ghé lại, người chơi
  mới được xây và phải còn đứng trên chính khu đất đó khi bắt đầu lượt kế tiếp.
- Mỗi đất xây độc lập tối đa 4 nhà, sau đó nâng cấp thành 1 khách sạn.
- Giá xây theo nhóm màu: `500.000₫`, `1.000.000₫`, `1.500.000₫` hoặc `2.000.000₫`.
- Tiền thuê theo cấp công trình: nhà 1/2/3/4 lần lượt ×5/×15/×45/×80;
  khách sạn ×125. Phá công trình thu hồi 50% giá xây.
- Mỗi người được mở **🎁 Hộp bí ẩn** một lần mỗi ván: có thể nhận tiền,
  nhà miễn phí, dịch chuyển về Xuất phát hoặc **🛡 Khiên miễn tiền thuê**.
- **🏳 Chịu thua**: rời ván, thanh lý tài sản và tự động xác định người thắng.
- **🏚 Phá nhà**: bán công trình lại cho ngân hàng và thu hồi 50% giá xây.
- **🥷 Trộm** không giới hạn: đặt cọc 20% tiền và một đất ngẫu nhiên. Thành công được
  hoàn cọc rồi lấy 25%–75% tiền của mục tiêu; thất bại mất cọc, mất đất thế chấp và vào tù.
- Tỉ lệ trộm người chơi là 30%; trộm **🏦 ngân hàng** là 15% và thành công nhận
  `50.000.000₫`. Bộ phá khóa tăng thêm 15% cho một lần trộm.
- **🎡 Vòng quay**: 55% lỗ nửa tiền cược, 20% lời 25%, 20% hòa vốn và 5% jackpot ×5.
  Không giới hạn lượt và có thể cược tới toàn bộ tiền hiện có.
- **🎲 Tài/Xỉu** không giới hạn lượt và có thể cược tới toàn bộ tiền hiện có.
- **🎁 Hộp bí ẩn** có 45% rỗng; jackpot chỉ 1%. Các phần thưởng khác có tỉ lệ thấp.
- **💣 Bom phá nhà** có 55% phá thành công; thất bại vẫn mất bom.
- **🕶 Chợ đen** bán Bộ phá khóa (+15% cơ hội trộm), Bom phá nhà và Thẻ tẩu thoát.
- Trong mỗi lượt chỉ được chọn **một hành động chiến thuật tổng cộng**: Xây nhà,
  Phá nhà, mở Hộp bí ẩn, Trộm, mua Chợ đen hoặc Phá hoại. Lượt phụ do xúc xắc đôi
  vẫn là cùng một lượt và không đặt lại quyền hành động.
- **Vòng quay và Tài/Xỉu không bị giới hạn số lần trong lượt**; Trạng thái cũng xem tự do.
- Trộm ngân hàng chỉ được thử một lần cho mỗi người trong cả ván.
- Mọi lần cược phải giữ lại ít nhất `100.000₫`, tránh người chơi tự đưa tiền về 0.

## Lệnh

`/help`, `/menu`, `/newgame`, `/join`, `/startgame`, `/roll`, `/status`, `/cancel`, `/profile`, `/shop`, `/buy ITEM_ID`, `/leaderboard`

### Giới hạn theo topic

Trong `.env`, đặt `ALLOWED_TOPIC_IDS=123,456` để bot chỉ hiển thị và xử lý game
trong các topic đó. Để trống nếu muốn cho phép tất cả topic. Mỗi topic được quản lý
như một phòng độc lập. Bot chỉ xoá menu do chính bot gửi nên không cần quyền admin.

## Giới hạn hiện tại

Ván active lưu trong RAM nên restart sẽ hủy ván đang chơi. Ví ⭐, inventory và leaderboard được giữ trong SQLite.
