# Pelluca: bot Telegram kiểm tra token (công khai, chỉ đọc)

Bot trả lời **mọi người** nhắn cho nó (khác bot paper chỉ nghe bạn). Giao diện tiếng Anh.
Không giao dịch, không giữ ví, không hỏi seed phrase. Dữ liệu: RPC công khai của Solana (miễn phí), Helius chỉ khi
RPC công khai lỗi, và DexScreener (được phép dùng thương mại). Không dùng RugCheck và GeckoTerminal (điều khoản không
cho sản phẩm thu phí, xem Notion "Tuần 1").

## Lệnh trong Telegram
- `/check <CA>` hoặc dán thẳng địa chỉ token: báo cáo rủi ro.
- `/watch <CA>`: báo khi SOL trong pool giảm 30% trong 10 phút hoặc còn dưới 5 SOL.
- `/unwatch <CA>`, `/list`, `/help`.
- Giới hạn: 20 lần kiểm tra mỗi giờ, 10 token theo dõi mỗi người.

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
