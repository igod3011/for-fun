# Pelluca: bot Telegram kiểm tra token (công khai, chỉ đọc)

Bot trả lời **mọi người** nhắn cho nó (khác bot paper chỉ nghe bạn). Giao diện tiếng Anh.
Không giao dịch, không giữ ví, không hỏi seed phrase. Dữ liệu: RPC công khai của Solana (miễn phí), Helius chỉ khi
RPC công khai lỗi, và DexScreener (được phép dùng thương mại). Không dùng RugCheck và GeckoTerminal (điều khoản không
cho sản phẩm thu phí, xem Notion "Tuần 1").

## Lệnh trong Telegram
- `/check <CA>` hoặc dán thẳng địa chỉ token: báo cáo rủi ro.
- `/watch <CA>`: báo khi SOL trong pool giảm 20% trong 30 phút hoặc còn dưới 5 SOL (ngưỡng đo 19/11/2026, xem
  `memebot/RESULTS.md`).
- `/unwatch <CA>`, `/list`, `/terms` (tóm tắt điều khoản + link pelluca.com/terms), `/help`.
- Điều khoản dịch vụ đầy đủ (tiếng Anh): `memebot/pelluca/legal/TERMS.md`. Viết theo mẫu pump.fun và GMGN
  (luật BVI, trọng tài BVI IAC, bỏ quyền kiện tập thể, trần trách nhiệm 100 USD). Cần tạo email support@pelluca.com.
- Giới hạn gói Free (`limits.py`, duyệt 19/11/2026): 20 lần kiểm tra mỗi giờ và 100 mỗi ngày, 3 token theo dõi.
  Gói Pro (khi có `pay.py`): 300 lần/ngày, 25 token.

## Báo cáo /check gồm
- Pool có thật là pool tốt nghiệp pump.fun không (dự trữ ảo), **token LP đã đốt chưa** (chưa đốt = có thể rút
  thanh khoản bất cứ lúc nào).
- Pool đã cạn chưa, đã mất bao nhiêu so với ~85 SOL lúc tốt nghiệp, giá sập bao nhiêu trong 1 giờ.
- Quyền mint / freeze còn bật không.
- Top 1 / top 10 nắm bao nhiêu, ví tạo token còn giữ bao nhiêu.
- **Lịch sử ví tạo token** (thay cờ "dev từng rug" của RugCheck): các token khác cùng ví đã tốt nghiệp, bao nhiêu
  cái nay đã cạn. Lấy thẳng từ chuỗi.
- Mua 0,5 SOL rồi bán ngay mất bao nhiêu, top 10 bán hết thì rút đi bao nhiêu % SOL của pool.
- Tỷ lệ nền từ nghiên cứu 10 ngày: 71% pool tốt nghiệp mất hơn 90% SOL trong 3 giờ.

## Chạy trên macOS (Terminal)
1. Cài Python + git (một lần): `xcode-select --install`, kiểm tra bằng `python3 --version`.
2. Tải code: mở https://github.com/igod3011/for-fun/archive/refs/heads/claude/mql5-market-product-5p7wht.zip,
   giải nén, rồi `cd ~/Downloads/for-fun-claude-mql5-market-product-5p7wht`.
3. `export PELLUCA_BOT_TOKEN=token_vua_nhan` rồi `python3 -m memebot.pelluca.bot` (thấy `Pelluca bot running`).
   Biến môi trường chỉ sống trong cửa sổ Terminal đó; đóng máy (gập nắp) là bot dừng, nên chạy 24/7 thì dùng VPS.

## Chạy trên Windows (thử)
1. Tạo bot MỚI: Telegram → @BotFather → `/newbot` → đặt tên `Pelluca` → nhận token. Không dùng token của bot paper.
2. Trong Command Prompt, tại thư mục dự án:
```
set PELLUCA_BOT_TOKEN=token_vua_nhan
```
```
python -m memebot.pelluca.bot
```
   Đúng khi thấy dòng `Pelluca bot running`. Mở bot trên Telegram, gửi `/check` kèm một CA.
3. Thử không cần Telegram:
```
python -m memebot.pelluca.check 2cMcMEX3Eqo86tUrVe5dgHp5GZNwqQ6crqm22UeZpump
```

## Đo độ chính xác cảnh báo /watch (cần dữ liệu cohort trên máy bạn)
```
python -m memebot.pelluca.drain_eval --data cohort.jsonl
```
Chọn ngưỡng trên 60% pool đầu, báo kết quả trên 40% pool sau. Gửi tôi ảnh chụp kết quả để cập nhật KPI.

## Chạy trên VPS (Ubuntu, Vultr Singapore 5 USD)
Xem `memebot/pelluca/deploy/VPS.md`.

## Website pelluca.com (`web.py`, thư mục `web/`)
- `python -m memebot.pelluca.web` chạy ở 127.0.0.1:8080; Caddy phía trước lo HTTPS (`deploy/Caddyfile`, VPS.md mục 8).
- Trang: `/` (ô dán CA gọi `/api/check`, cùng logic với bot), `/studio` (Meme Studio, đang "coming soon"),
  `/terms` (dựng từ `legal/TERMS.md` mỗi lần mở, nên sửa điều khoản chỉ cần sửa file đó).
- Giới hạn theo IP giống gói Free. Không lưu IP vào log. Chỉ thư viện chuẩn Python.
- Logo "Pelly" (sứa trong suốt): `web/logo.svg`, `web/favicon.svg`, ảnh đại diện `web/pelly-640.png`.
