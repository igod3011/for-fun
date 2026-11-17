# Bot giao dịch memecoin (chế độ PAPER) điều khiển qua Telegram

**Chỉ giao dịch giả lập (paper).** Không có ví, không có private key, không đặt lệnh thật. Phần thực thi thật
chỉ được thêm khi paper trading có lãi sau phí trong vài tuần.

## Cách hoạt động
1. **Nguồn token:** đọc các pool mới mà bộ thu thập vừa ghi vào `cohort.jsonl` (cần bộ thu thập đang chạy).
2. **Bộ lọc vào lệnh** (`strategy.entry_check`): mint pump.fun, pool tốt nghiệp thật (k = SOL×token trong
   1,0–2,6×10¹⁰), ≥40 SOL, không còn mint/freeze authority, đăng ký ≤15 phút sau khi tạo, và **không phải dàn ví**: dưới 1.000 holder
   (`max_holders_reg`) và top 10 holder từ 15% trở lên (`min_top10`); pool phải do pump.fun migrate thật (dự trữ ảo on-chain khác 0) và
   không ví nào giữ từ 50% nguồn cung (`max_top1`). Quy tắc cũ "top 10 ≤50%" đã bỏ vì loại nhầm
   nhóm tốt hơn.
3. **Chờ đến khi pool được 90 phút tuổi** (`entry_delay_min`, cửa sổ 30 phút), rồi kiểm tra lại "dao rơi":
   pool còn ≥40 SOL và SOL không giảm quá 20% so với lúc ghi nhận. Đạt thì **mua giả lập** 0,2 SOL (`stake_sol`, phí 1,2% mỗi swap) theo dự trữ
   thật lúc đó (có tính dự trữ ảo đọc on-chain của chính pool đó, xem `amm.py`), cộng phí cố định 0,0003 SOL mỗi lệnh (`tx_fee_sol`).
4. **Kiểm tra trước khi mua** (`intel.py`, RugCheck + DexScreener, miễn phí): bỏ qua nếu ví dev còn giữ >3%
   nguồn cung, dev từng rug token khác, hoặc giá đã tăng >80% trong 1 giờ. Ngay trước đó bot chụp holder lần hai (Helius) và ghi
   vào nhật ký cùng quyết định; số này chưa dùng làm quy tắc.
   Không lấy được dữ liệu RugCheck thì cũng không mua. Tin nhắn mua có giá, vốn hóa (MC), % tăng 1 giờ,
   % dev và số holder lúc ghi nhận → lúc mua; tin bán có giá và MC lúc vào so với lúc bán.
5. **Theo dõi mỗi 15 giây** (`strategy.exit_decision`), giá trị tính bằng số SOL pool thật sự trả:
   cắt lỗ −10%, trailing stop 10% sau khi lãi +20%, không chốt lời cố định,
   thoát khi SOL trong pool bị rút 25% so với đỉnh, giữ tối đa 60 phút.
   Bộ quy tắc này đến từ dò tìm walk-forward trên 839 pool. **Con số +3% lúc đó là ảo** (backtest coi cắt lỗ khớp
   đúng mức stop); đo lại ngày 11/11/2026 với phí thật 1,2% và bộ lọc dàn ví: TEST −17,2% mỗi lệnh (CI 90% −30,4%..−0,4%). Bot paper thật
   cũng mất gần hết 1 SOL sau 15 lệnh. Xem `PROJECT.md` mục 5.
6. **Giới hạn rủi ro:** tối đa 3 vị thế, ngừng mở lệnh mới khi lỗ trong ngày ≥0,6 SOL (nới cho paper để không cắt
   ngắn phép đo; phải đặt chặt lại trước khi dùng tiền thật).
7. Mọi quyết định (mua, bán, bỏ qua và lý do) ghi vào `bot_trades.jsonl`; trạng thái lưu ở `bot_state.json`
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
`/status`, `/positions`, `/review [giờ]`, `/pause`, `/resume`, `/sellall`, `/topup 5` (nạp thêm SOL paper, không tính vào lãi lỗ), `/stop`, `/help`.
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
   rồi chạy lại `memebot\start_bot.bat`. Nếu `smart_wallets.json` ghi `FAIL`, bot coi danh sách ví là rỗng và
   không khởi động chế độ này. Bot kiểm tra giao dịch của các ví mỗi 60 giây; khi đủ số ví cùng mua
   một token pump.fun có pool tốt nghiệp thật, bot mua giả lập và báo "🐋 PAPER FOLLOW BUY".
   Tốn Helius: khoảng 1 lệnh gọi mỗi ví mỗi phút, cộng 1 lệnh cho mỗi giao dịch mới của ví.

## Chọn thời điểm vào lệnh (backtest trên dữ liệu thật)
```
python -m memebot.ml.entry_timing --data cohort.jsonl
python -m memebot.ml.entry_timing --data cohort.jsonl --grid
```
`--grid` dò 480 cấu hình (thời điểm vào × cắt lỗ × chốt lời × trailing × thời gian giữ) theo walk-forward:
chọn trên 60% pool cũ hơn, báo kết quả TEST trên 40% pool mới hơn. Chỉ số TEST mới có ý nghĩa.
Mặc định tính phí cố định 0,0003 SOL mỗi giao dịch; đổi bằng `--tx-fee` và cỡ lệnh bằng `--stake`.
`--max-h1 0.8` bỏ các lệnh mà giá đã tăng >80% trong giờ trước đó (kiểm chứng quy tắc của bot).
Quy tắc dev/bundle và số holder: `python -m memebot.ml.rc_rules --data cohort.jsonl --stake 0.2 --max-h1 0.8`.
`--stop-fill close|low|stop` chọn cách khớp cắt lỗ trong nến (mặc định `close`; `stop` là mô hình cũ, quá lạc quan).
So sánh vào lệnh sau 5/15/30/60 phút với 3 bộ lọc (F0 mọi pool còn giao dịch, F1 + chặn dao rơi,
F2 + lực mua), và 2 cách thoát (giữ đến lúc điền nến, hoặc theo quy tắc của bot). Kết quả tính bằng số SOL
thật rút ra được từ pool. Một bộ lọc chỉ có ích nếu tốt hơn F0 ở cả nửa đầu lẫn nửa sau của dữ liệu.
