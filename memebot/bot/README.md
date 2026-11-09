# Bot giao dịch memecoin (chế độ PAPER) điều khiển qua Telegram

**Chỉ giao dịch giả lập (paper).** Không có ví, không có private key, không đặt lệnh thật. Phần thực thi thật
chỉ được thêm khi paper trading có lãi sau phí trong vài tuần.

## Cách hoạt động
1. **Nguồn token:** đọc các pool mới mà bộ thu thập vừa ghi vào `cohort.jsonl` (cần bộ thu thập đang chạy).
2. **Bộ lọc vào lệnh** (`strategy.entry_check`): mint pump.fun, pool tốt nghiệp thật (k = SOL×token trong
   1,0–2,6×10¹⁰), ≥20 SOL, không còn mint/freeze authority, top 10 holder ≤50%, đăng ký ≤15 phút sau khi tạo.
   Đây là bộ lọc tạm thời; quy tắc tốt hơn sẽ đến từ phân tích dữ liệu 2 tuần.
3. **Mua giả lập** 0,05 SOL theo dự trữ thật của pool lúc đó (Helius).
4. **Theo dõi mỗi 15 giây** (`strategy.exit_decision`), giá trị tính bằng số SOL pool thật sự trả:
   cắt lỗ −25%, trailing stop 20% sau khi lãi +30%, chốt lời từng phần ở +50% và +100%,
   thoát khi SOL trong pool bị rút 25% so với đỉnh, giữ tối đa 120 phút.
   "Mua đuổi" (`chase_enabled`) có sẵn nhưng mặc định TẮT.
5. **Giới hạn rủi ro:** tối đa 3 vị thế, ngừng mở lệnh mới khi lỗ trong ngày ≥0,2 SOL.
6. Mọi quyết định (mua, bán, bỏ qua và lý do) ghi vào `bot_trades.jsonl`; trạng thái lưu ở `bot_state.json`
   nên khởi động lại không mất vị thế.

Muốn đổi thông số: tạo file `bot_config.json` cùng thư mục, ví dụ `{"stake_sol": 0.02, "max_positions": 2}`.

## Cài đặt lần đầu (Windows)
1. Trong Telegram, chat với **@BotFather** → `/newbot` → đặt tên → nhận **token**. Không gửi token cho ai.
2. Mở bot vừa tạo trong Telegram, gửi một tin bất kỳ (ví dụ `hi`).
3. Trong Command Prompt, ở thư mục code:
   ```
   set TELEGRAM_BOT_TOKEN=token_cua_ban
   python -m memebot.bot.telegram --whoami
   ```
   Lệnh in ra `chat id: 123456789`.
4. Đặt đủ ba biến rồi khởi động bot:
   ```
   set TELEGRAM_CHAT_ID=123456789
   set HELIUS_API_KEY=key_cua_ban
   python -m memebot.bot.runner --once
   memebot\start_bot.bat
   ```
   `--once` chạy thử một vòng rồi thoát. Sau `start_bot.bat` bạn sẽ nhận tin "bot started" trong Telegram.

## Lệnh Telegram
`/status`, `/positions`, `/pause`, `/resume`, `/sellall`, `/stop`, `/help`.
Bot chỉ nghe lệnh từ đúng `TELEGRAM_CHAT_ID`; tin nhắn từ người khác bị bỏ qua.

## Chuyển lên VPS sau này
Chỉ dùng thư viện chuẩn của Python nên chạy được trên Linux: đặt các biến bằng `export`, chạy
`nohup python3 -m memebot.bot.runner > bot.log 2>&1 &` (hoặc một dịch vụ systemd).

## Theo dõi ví "cá mập" (3 bước)
1. **Thu địa chỉ:** bộ thu thập lưu top 10 holder (trừ pool) của mỗi pool lúc ghi nhận và lúc điền nến
   (`helius_reg.top_holders`). Chỉ pool ghi nhận SAU bản cập nhật này mới có địa chỉ.
2. **Chấm điểm và kiểm chứng** (sau ít nhất 5–7 ngày dữ liệu có địa chỉ):
   ```
   python -m memebot.ml.wallet_scores --data cohort.jsonl
   ```
   Chia theo thời gian: 60% đầu để tìm ví, 40% sau để kiểm tra. Ví giữ hơn 10% nguồn cung bị bỏ qua
   (thường là ví dev hoặc bundle). Kết quả `PASS` hoặc `FAIL` được ghi vào `smart_wallets.json`.
3. **Bot làm theo (paper):** chỉ bật khi bước 2 báo `PASS`. Tạo `bot_config.json`:
   ```
   {"follow_enabled": true, "follow_min_wallets": 1}
   ```
   rồi chạy lại `memebot\start_bot.bat`. Bot kiểm tra giao dịch của các ví mỗi 60 giây; khi đủ số ví cùng mua
   một token pump.fun có pool tốt nghiệp thật, bot mua giả lập và báo "🐋 PAPER FOLLOW BUY".
   Tốn Helius: khoảng 1 lệnh gọi mỗi ví mỗi phút, cộng 1 lệnh cho mỗi giao dịch mới của ví.

## Chọn thời điểm vào lệnh (backtest trên dữ liệu thật)
```
python -m memebot.ml.entry_timing --data cohort.jsonl
```
So sánh vào lệnh sau 5/15/30/60 phút với 3 bộ lọc (F0 mọi pool còn giao dịch, F1 + chặn dao rơi,
F2 + lực mua), và 2 cách thoát (giữ đến lúc điền nến, hoặc theo quy tắc của bot). Kết quả tính bằng số SOL
thật rút ra được từ pool. Một bộ lọc chỉ có ích nếu tốt hơn F0 ở cả nửa đầu lẫn nửa sau của dữ liệu.
