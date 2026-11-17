# Đưa bot Pelluca lên VPS (Ubuntu 24.04, Vultr Singapore 5 USD/tháng)

Bạn tự thuê VPS và tự thanh toán. Không gửi mật khẩu, token hay khóa SSH vào chat.

## 1. Thuê VPS
Vultr → Deploy → Cloud Compute (Shared CPU) → Singapore → Ubuntu 24.04 LTS → gói 1 vCPU / 1 GB (5 USD) → đặt
mật khẩu root hoặc thêm khóa SSH → Deploy. Ghi lại địa chỉ IP.

## 2. Đăng nhập (Command Prompt trên Windows có sẵn ssh)
```
ssh root@IP_CUA_VPS
```
Các lệnh dưới đây chạy TRÊN VPS, lần lượt từng lệnh.

## 3. Cài đặt (một lần)
```
apt update && apt -y upgrade && apt -y install python3 git
```
```
adduser --disabled-password --gecos "" pelluca
```
```
sudo -u pelluca git clone -b claude/mql5-market-product-5p7wht https://github.com/igod3011/for-fun.git /home/pelluca/app
```
(Repo riêng tư: GitHub → Settings → Developer settings → Fine-grained token chỉ quyền đọc repo này, rồi dùng
`https://TOKEN@github.com/igod3011/for-fun.git`. Token gõ trên VPS, không gửi vào chat.)

## 4. Đặt token bot (chỉ nằm trên VPS)
```
nano /home/pelluca/pelluca.env
```
Gõ vào file (thay bằng token thật), lưu bằng Ctrl+O, Enter, Ctrl+X:
```
PELLUCA_BOT_TOKEN=token_cua_bot_pelluca
PELLUCA_WATCH_FILE=/home/pelluca/pelluca_watch.json
```
Tùy chọn: thêm `HELIUS_API_KEY=...` để dự phòng khi RPC công khai bận.
```
chown pelluca:pelluca /home/pelluca/pelluca.env && chmod 600 /home/pelluca/pelluca.env
```

## 5. Chạy như dịch vụ (tự khởi động lại khi lỗi hoặc VPS khởi động lại)
```
cp /home/pelluca/app/memebot/pelluca/deploy/pelluca-bot.service /etc/systemd/system/
```
```
systemctl daemon-reload && systemctl enable --now pelluca-bot
```
Kiểm tra: `systemctl status pelluca-bot` phải ghi `active (running)`; nhật ký: `journalctl -u pelluca-bot -n 50`.
Mở bot trên Telegram, gửi `/check` kèm một CA.

## 6. Cập nhật code sau này
```
sudo -u pelluca git -C /home/pelluca/app pull && systemctl restart pelluca-bot
```

## 7. Bảo mật tối thiểu
```
ufw allow OpenSSH && ufw --force enable
```
Bot chỉ gọi ra ngoài (Telegram, RPC), không mở cổng nào, nên không cần mở thêm.
