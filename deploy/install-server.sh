#!/usr/bin/env bash
# Cài đặt bot trên server Linux bằng systemd (không dùng Docker).
# Chạy với quyền sudo trên Ubuntu/Debian.
set -euo pipefail

APP_DIR="/opt/ty-phu-bot"
SERVICE_USER="typhu"
SERVICE_NAME="ty-phu-bot"

echo "==> Cài đặt gói hệ thống"
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip rsync

echo "==> Tạo user dịch vụ: ${SERVICE_USER}"
if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  sudo useradd --system --create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

echo "==> Sao chép mã nguồn tới ${APP_DIR}"
sudo mkdir -p "${APP_DIR}"
sudo rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude 'data' \
  --exclude '__pycache__' --exclude '.env' \
  "$(dirname "$0")/../" "${APP_DIR}/"

echo "==> Tạo virtual environment và cài thư viện"
sudo python3 -m venv "${APP_DIR}/.venv"
sudo "${APP_DIR}/.venv/bin/pip" install --upgrade pip
sudo "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

if [ ! -f "${APP_DIR}/.env" ]; then
  echo "==> Tạo file .env mẫu (nhớ điền BOT_TOKEN mới)"
  sudo cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
fi

sudo mkdir -p "${APP_DIR}/data"
sudo chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"

echo "==> Cài đặt systemd service"
sudo cp "${APP_DIR}/deploy/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

cat <<EOF

==> Hoàn tất cài đặt.

1. Chỉnh token mới trong: ${APP_DIR}/.env
2. Khởi động bot:   sudo systemctl start ${SERVICE_NAME}
3. Xem trạng thái:   sudo systemctl status ${SERVICE_NAME}
4. Xem log:          journalctl -u ${SERVICE_NAME} -f
EOF
