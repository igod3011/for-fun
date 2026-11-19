# Đưa bot Pelluca lên VPS (Ubuntu 24.04, Vultr Singapore 5 USD/tháng)

Bạn tự thuê VPS và tự thanh toán. Không gửi mật khẩu, token hay khóa SSH vào chat.

## 1. Thuê VPS
Vultr → Deploy → Cloud Compute (Shared CPU) → Singapore → Ubuntu 24.04 LTS → gói 1 vCPU / 1 GB (5 USD) → đặt
mật khẩu root hoặc thêm khóa SSH → Deploy. Ghi lại địa chỉ IP.

## 2. Đăng nhập (Terminal trên Mac hoặc Command Prompt trên Windows đều có sẵn ssh)
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
(Repo đang công khai nên không cần token GitHub.)

## 4. Đặt token bot (chỉ nằm trên VPS)
Lệnh hỏi token, dán vào (màn hình không hiện gì), Enter:
```
read -rsp "Bot token: " T && echo && printf 'PELLUCA_BOT_TOKEN=%s\nPELLUCA_WATCH_FILE=/home/pelluca/pelluca_watch.json\n' "$T" > /home/pelluca/pelluca.env && unset T && chown pelluca:pelluca /home/pelluca/pelluca.env && chmod 600 /home/pelluca/pelluca.env
```
Nên thêm key Helius (gói miễn phí): RPC công khai gần như luôn từ chối lệnh đọc top holder, không có Helius một
lần /check mất ~21 giây thay vì ~2 giây (đo 19/11/2026). Bot chỉ dùng Helius cho lệnh đó và khi RPC công khai bận.
```
read -rsp "Helius key: " K && echo && echo "HELIUS_API_KEY=$K" >> /home/pelluca/pelluca.env && unset K && chmod 600 /home/pelluca/pelluca.env
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

Đo thời gian từng bước của một lần kiểm tra:
```
cd /home/pelluca/app && set -a && . /home/pelluca/pelluca.env && set +a && python3 -m memebot.pelluca.check <CA> --timing | grep -v TOKEN
```

## 6. Cập nhật code sau này
```
sudo -u pelluca git -C /home/pelluca/app pull && systemctl restart pelluca-bot pelluca-web
```
(Chưa cài website thì bỏ `pelluca-web`.)

## 7. Bảo mật tối thiểu
```
ufw allow OpenSSH && ufw --force enable
```
Bot chỉ gọi ra ngoài (Telegram, RPC), không mở cổng nào. Website mở thêm cổng 80 và 443 (mục 8).

## 8. Website pelluca.com (cùng VPS)
Cần có tên miền trước. Trong trang quản lý tên miền, tạo 2 bản ghi A: `@` và `www` trỏ về IP của VPS. Chờ vài
phút rồi kiểm tra trên máy mình: `ping pelluca.com` phải ra đúng IP VPS.

Chạy website (Python chuẩn, chỉ nghe ở 127.0.0.1:8080):
```
cp /home/pelluca/app/memebot/pelluca/deploy/pelluca-web.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now pelluca-web
```
Kiểm tra: `curl -s 127.0.0.1:8080 | head -3` phải ra `<!doctype html>`.

Caddy lo HTTPS (tự xin và gia hạn chứng chỉ):
```
apt -y install caddy
```
```
cp /home/pelluca/app/memebot/pelluca/deploy/Caddyfile /etc/caddy/Caddyfile && systemctl reload caddy
```
```
ufw allow 80 && ufw allow 443
```
Kiểm tra: mở https://pelluca.com trên trình duyệt, dán một CA và bấm Check.
