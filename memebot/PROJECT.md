# memebot: bot giao dịch memecoin Solana (paper) và hạ tầng nghiên cứu

Tài liệu tổng quan: mục tiêu, kiến trúc, cách chạy, dữ liệu, kết quả đến 11/2026 và cách đánh giá hiệu quả.
Nhánh: `claude/mql5-market-product-5p7wht` của repo `igod3011/for-fun`. Mọi code nằm trong `memebot/`.

---

## 1. Mục tiêu và trạng thái

**Mục tiêu cuối:** một bot chạy 24/7 tự mua, bán, cắt lỗ, chốt lời memecoin Solana (token vừa tốt nghiệp
pump.fun lên PumpSwap), báo cáo và nhận lệnh qua Telegram, giao dịch bằng một ví riêng với số tiền nhỏ.

**Trạng thái hiện tại:**
- Đang chạy **paper trading** (giả lập, không tiền thật, không ví, không private key) trên máy Windows của người dùng.
- Bộ thu thập dữ liệu chạy song song từ 06/11/2026, khoảng 2.300 pool mỗi ngày.
- **Chưa có phần giao dịch thật.** Chỉ thêm khi đạt các mốc ở mục 7.

**Kết luận nghiên cứu quan trọng nhất đến nay:** mua mù quáng token vừa tốt nghiệp lỗ trung bình khoảng 75%.
Cấu hình tốt nhất tìm được (vào lệnh sau 90 phút + bộ lọc + cắt lỗ chặt + trailing) dương khoảng +2 đến +3% mỗi
lệnh trên dữ liệu kiểm tra, nhưng khoảng tin cậy 90% vẫn chứa 0, nên **chưa chứng minh được lợi thế**.

---

## 2. Kiến trúc

```
                 GeckoTerminal (pool mới)          RPC công khai Solana (dự trữ pool, miễn phí)
                          │                         Helius DAS (holder, chỉ pool tốt nghiệp thật)
                          ▼                         RugCheck (dev, insider)
  collector_daemon ──► collect.py ──► cohort.jsonl ◄── (ghi nhận mỗi 2 phút, điền nến mỗi 5 phút)
                                          │
              ┌───────────────────────────┼─────────────────────────────┐
              ▼                           ▼                             ▼
     report / healthcheck        ml/entry_timing (backtest,       bot/runner (paper, 24/7)
     (tình trạng, baseline)      walk-forward grid, CI)           ├─ strategy.entry_check (lọc tĩnh)
                                 ml/wallet_scores (ví giỏi)       ├─ chờ pool 90 phút tuổi + chặn dao rơi
                                                                  ├─ intel: RugCheck + DexScreener
                                                                  ├─ paper.buy (dự trữ thật, phí thật)
                                                                  ├─ exit_decision mỗi 15 giây
                                                                  └─ Telegram: tin nhắn + lệnh điều khiển
```

### Bản đồ module
| File | Vai trò |
|---|---|
| `collect.py` | Tìm pool PumpSwap mới (GeckoTerminal), snapshot dự trữ, RugCheck lúc ghi nhận, điền nến 1 phút + snapshot lúc điền |
| `collector_daemon.py` | Chạy `collect.py` mãi mãi: ghi nhận mỗi 2 phút, điền tối đa 20 pool mỗi 5 phút |
| `rpc.py` | RPC Solana: công khai trước (miễn phí), Helius dự phòng; `pool_reserves()` đọc SOL và token của pool |
| `helius.py` | Helius DAS (10 credit/lệnh): holder, top 10 địa chỉ, quyền mint/freeze; `--selftest`, `--inspect` |
| `report.py` | Báo cáo cohort: pool chết, baseline lợi nhuận **thực rút được** (theo dự trữ thật), phân nhóm pool |
| `healthcheck.py` | PASS/WARN/FAIL cho bộ thu thập; `--live` gọi thử API |
| `ml/entry_timing.py` | Backtest thời điểm vào + quy tắc thoát; `--grid` walk-forward 480 cấu hình, bootstrap CI |
| `ml/wallet_scores.py` | Tìm ví "giỏi" và kiểm tra chúng có giữ được lợi thế ở giai đoạn sau không |
| `ml/melt_data.py`, `ml/train_rug_model.py` | Nạp an toàn bộ dữ liệu MELT (41k token) và mô hình phát hiện rug (AUROC 0,90) |
| `bot/config.py` | Toàn bộ tham số bot (ghi đè bằng `bot_config.json`) |
| `bot/strategy.py` | Hàm thuần: `entry_check`, `exit_decision`, `chase_check`, `Position` |
| `bot/amm.py` | Toán swap constant-product trên dự trữ thật |
| `bot/paper.py` | Danh mục paper: số dư, vị thế, phí, giới hạn rủi ro, lưu trạng thái, nhật ký quyết định |
| `bot/intel.py` | RugCheck + DexScreener trước khi mua; định dạng giá, vốn hóa |
| `bot/runner.py` | Vòng lặp chính, Telegram, follow ví, báo cáo ngày |
| `bot/telegram.py` | Client Telegram (stdlib), `--whoami` lấy chat id |
| `bot/review.py` | Tổng hợp `bot_trades.jsonl` (lệnh `/review`) |
| `bot/wallets.py` | Theo dõi ví theo thời gian thực (follow mode, tắt mặc định) |
| `restart_collector.bat`, `start_bot.bat` | Khởi động lại bộ thu thập / bot trên Windows (chỉ dừng đúng tiến trình của nó) |
| `tests/` | 58 test, chạy bằng `python -m unittest discover -s memebot/tests -t .` |
| `anomaly.py`, `backtest.py`, `broker.py`, `engine.py`, `strategy.py`, `synthetic.py`, `live.py`, `realtest.py`, `models.py`, `config.py` (gốc) | **Bản thử nghiệm đầu tiên** (dữ liệu giả lập, DexScreener). Giữ để tham khảo, không dùng cho bot hiện tại |

### Nguyên tắc thiết kế
- **Chỉ dùng thư viện chuẩn Python 3.9+** cho bot và bộ thu thập, để chạy được trên Windows và Linux (VPS) không cần cài gì.
- **Lợi nhuận luôn tính bằng số SOL thật rút được từ pool** (constant product trên dự trữ thật), không dùng giá
  giao dịch cuối (GeckoTerminal có giá ảo khi pool cạn).
- **Không nhìn trước tương lai:** không dùng dữ liệu biết được sau thời điểm quyết định (đã từng mắc lỗi này: lọc
  theo thanh khoản lúc thu thập cho kết quả giả +250%).
- **Đánh giá walk-forward:** chọn trên dữ liệu cũ, kiểm tra trên dữ liệu mới; luôn kèm khoảng tin cậy.
- **Mọi quyết định của bot đều ghi kèm lý do** (`bot_trades.jsonl`).

---

## 3. Cài đặt và chạy

### Windows (đang dùng)
Yêu cầu: Python 3.9+ ("Add python.exe to PATH" khi cài). Không cần cài thư viện nào.
```
cd C:\Users\PC1433\memebot\for-fun-claude-mql5-market-product-5p7wht
set HELIUS_API_KEY=...
set TELEGRAM_BOT_TOKEN=...
set TELEGRAM_CHAT_ID=...
memebot\restart_collector.bat
memebot\start_bot.bat
python -m memebot.healthcheck
```
- Lấy chat id: gửi `hi` cho bot trong Telegram, rồi `python -m memebot.bot.telegram --whoami` (khi bot đang dừng).
- Cập nhật code: tải zip của nhánh, giải nén đè (giữ nguyên các file dữ liệu):
  `powershell -Command "Invoke-WebRequest -Uri 'https://github.com/igod3011/for-fun/archive/refs/heads/claude/mql5-market-product-5p7wht.zip' -OutFile code.zip; Expand-Archive code.zip -DestinationPath .. -Force"`
- Biến môi trường chỉ sống trong cửa sổ đó. Máy khởi động lại thì phải đặt lại và chạy lại hai file `.bat`.
- Giữ máy không ngủ: `powercfg /change standby-timeout-ac 0`.

### Linux / VPS (dự kiến)
```
export HELIUS_API_KEY=... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
nohup python3 -m memebot.collector_daemon --out cohort.jsonl > daemon.log 2> daemon.err &
nohup python3 -m memebot.bot.runner > bot.log 2> bot.err &
```
Nên dùng systemd để tự khởi động lại. Không ghi key vào file trong repo.

### Lệnh Telegram
`/status`, `/positions`, `/review [giờ]`, `/pause`, `/resume`, `/sellall`, `/stop`, `/help`.
Bot chỉ nghe đúng `TELEGRAM_CHAT_ID`.

### Chi phí API
- Helius gói miễn phí: 1 triệu credit/tháng. DAS = 10 credit, RPC thường = 1 credit. Sau tối ưu, khoảng 5–12 nghìn credit/ngày
  (trước tối ưu khoảng 100 nghìn/ngày). Kiểm tra dashboard Helius định kỳ.
- GeckoTerminal, RugCheck, DexScreener, RPC công khai Solana: miễn phí, có giới hạn tốc độ (code đã giãn cách và thử lại).

---

## 4. Dữ liệu

Tất cả nằm trên máy chạy bot, trong thư mục code (không có trong git).

| File | Nội dung | Ghi bởi |
|---|---|---|
| `cohort.jsonl` | Mỗi dòng một pool PumpSwap mới (xem schema dưới). Khoảng 2.300 pool/ngày, khoảng 10 MB/ngày | bộ thu thập |
| `daemon.log`, `daemon.err` | Nhật ký bộ thu thập (`pages cover X min` = độ phủ) | bộ thu thập |
| `bot_trades.jsonl` | Mọi quyết định của bot: `buy`, `sell`, `skip` + lý do, giá, MC, PnL | bot |
| `bot_series.jsonl` | Dự trữ pool của các vị thế mỗi 15 giây (để mô phỏng lại quy tắc thoát) | bot |
| `bot_state.json` | Số dư, vị thế đang mở, token đã xét (để khởi động lại không mất gì) | bot |
| `bot.log`, `bot.err` | Nhật ký bot | bot |
| `smart_wallets.json` | Kết quả `wallet_scores` (danh sách ví + kết luận PASS/FAIL) | `ml/wallet_scores` |

### Schema một dòng `cohort.jsonl`
```
pool, mint, name, created (unix giây, lúc tạo pool), reserve_usd, fdv_usd, registered_at
helius_reg:  pool_sol, pool_tokens, fetched_at            (mọi pool, RPC miễn phí)
             holders, top1/5/10/20_pct, pool_pct,         (chỉ pool tốt nghiệp thật, Helius DAS)
             top_holders [[địa chỉ, tỷ lệ], ...], mint_authority, freeze_authority
rc_reg:      creator, dev_pct, creator_rugs, creator_launches, insider_pct, insiders_detected, risks
             (RugCheck lúc ghi nhận, chỉ pool tốt nghiệp thật, từ bản 11/2026)
candles:     [[ts, open, high, low, close, volume_usd], ...]   1 phút, GeckoTerminal, điền khi pool ≥3 giờ tuổi
rugcheck:    tóm tắt RugCheck lúc điền nến
helius_fill: pool_sol, pool_tokens, fetched_at             (snapshot dự trữ lúc điền nến = kết quả thật)
fetched_at
```
"Pool tốt nghiệp thật" (canonical): mint kết thúc bằng `pump` và k = SOL × token trong 1,0–2,6 × 10¹⁰
(bộ thu thập dùng khoảng rộng hơn 0,5–5 × 10¹⁰ để lấy dữ liệu holder).

### Chia sẻ dữ liệu để phân tích
Nén `cohort.jsonl` và `bot_*.jsonl` thành zip (giảm khoảng 90%), tải lên Google Drive chế độ "Anyone with the link",
gửi link. Không gửi các file `.err`/`.log` nếu chúng có thể chứa thông tin cá nhân.

---

## 5. Kết quả đến hiện tại

### Nghiên cứu bên ngoài
- MELT (41.470 token pump.fun, 12/2024–3/2025): 84% rủi ro cao; trung vị lợi nhuận sau migration −68%.
  Mô hình LightGBM chia theo thời gian: AUROC 0,90; lọc rug cải thiện trung vị nhưng trung bình vẫn âm.
- Đặc trưng mạnh nhất: tập trung nắm giữ sau khi gộp ví bundle.

### Dữ liệu tự thu (khoảng 7.000 pool trong 3 ngày đầu)
| Chỉ số | Giá trị |
|---|---|
| Pool chết (<30 phút giao dịch trong 3 giờ đầu) | 68% |
| Pool đã cạn ngay lúc ghi nhận (<1 SOL) | 31% |
| Pool PumpSwap không phải pump.fun | 3.393 pool, trung bình −98,4%, 0% có lãi |
| Pool giả cho mint pump.fun thật | 148 pool, −100% |
| **Pool tốt nghiệp thật, mua mù và giữ ≥3 giờ** | 811 pool, **trung bình −75,2%, 12% có lãi** |
| Cờ `rugged` của RugCheck | 0/6.794: vô dụng làm nhãn |

### Backtest thời điểm vào và quy tắc thoát (lợi nhuận thực rút được, phí 0,5%/swap + 0,0003 SOL/giao dịch)
- Giữ lệnh đến 3 giờ: −40% đến −74% ở mọi cấu hình. **Bắt buộc phải có quy tắc thoát.**
- Chặn dao rơi (≥40 SOL, SOL không giảm >20% từ lúc ghi nhận) cải thiện nhất quán ở cả hai nửa dữ liệu.
- Bộ lọc lực mua (giá không thấp hơn 10 phút trước) không thêm giá trị.
- Walk-forward 480 cấu hình (921 pool, lệnh 0,2 SOL):

| Cấu hình | TEST | Khoảng tin cậy 90% |
|---|---|---|
| Cũ: vào +60 phút, SL 25%, chốt lời 50%@+50%/+100%, trailing 20% sau +30%, giữ 120 phút | −7,0% | −10,7%..−3,1% (chắc chắn lỗ) |
| **Hiện tại: vào +90 phút, SL 10%, không chốt lời cố định, trailing 10% sau +20%, giữ 60 phút** | +1,8% | −1,9%..+6,3% |
| Hiện tại + bỏ token đã tăng >80% trong 1 giờ | **+3,1%** (n=63, thắng 52%) | −1,2%..+7,9% |

- Lệnh 0,2 SOL tốt hơn 0,05 SOL vì phí cố định chiếm 0,3% thay vì 1,2% mỗi vòng.
- Quy tắc dev >3%, dev từng rug, insider >10%: đang bật (hợp lý theo nghiên cứu) nhưng **chưa backtest**
  (dữ liệu `rc_reg` mới bắt đầu thu từ 11/2026).

### Đánh giá các nguồn khác
- GMGN: API phải xin duyệt; phí 1%/lệnh; dùng để tham khảo thủ công.
- TradingAgents (tauricresearch): khung LLM nhiều tác tử cho cổ phiếu/BTC theo ngày, quá chậm và tốn cho memecoin;
  học được: cổng duyệt rủi ro tách biệt, kỷ luật chống nhìn trước tương lai, nhật ký quyết định có chấm điểm.
- Video TikTok "Grok Bot": quảng bá, không kiểm chứng được, lợi nhuận phi lý; chỉ lấy ý tưởng quy tắc lọc.

---

## 6. Cách đánh giá hiệu quả

| Tần suất | Lệnh | Nhìn vào đâu |
|---|---|---|
| Hằng ngày | `/status` (Telegram) | Bot còn chạy, PnL ngày |
| Hằng ngày | `python -m memebot.healthcheck` | `0 fail`; `pages cover` ≥6 phút; `overdue` gần 0 |
| Hằng tuần | `python -m memebot.ml.entry_timing --data cohort.jsonl --grid --stake 0.2 --max-h1 0.8` | Dòng `NEW bot rules`: TEST và **khoảng tin cậy 90%** |
| Hằng tuần | `/review 168` | Số lệnh đóng, PnL, tỷ lệ thắng, PnL theo từng lý do thoát |
| Sau 5–7 ngày có địa chỉ ví | `python -m memebot.ml.wallet_scores --data cohort.jsonl` | `PASS` hay `FAIL` |
| Khi cần | `python -m memebot.report cohort.jsonl` | Baseline `REALIZABLE` theo nhóm pool |
| Hằng ngày | Dashboard Helius | Credit dùng mỗi ngày (mục tiêu ≤ 25 nghìn) |

**Cách đọc:**
- Chỉ số TEST trong walk-forward là thước đo duy nhất về tương lai. Train luôn đẹp hơn.
- Khoảng tin cậy chứa 0 nghĩa là chưa phân biệt được với may rủi.
- Kết quả paper phải gần với backtest. Nếu paper tệ hơn nhiều: độ trễ, trượt giá, hoặc khác biệt mô phỏng.
- Mọi bộ lọc mới phải tốt hơn khi không có nó **trên cùng dữ liệu**, ở cả hai nửa thời gian.

---

## 7. Mốc quyết định trước khi dùng tiền thật (cần đạt cả ba)
1. Khoảng tin cậy 90% của cấu hình bot trên TEST **nằm hoàn toàn trên 0**, với ít nhất 200 lệnh TEST.
2. Bot paper có **ít nhất 100 lệnh đóng** với PnL dương sau phí.
3. Kết quả paper gần với backtest.

Khi đạt: thêm thực thi qua Jupiter Swap API, ký giao dịch tại máy, **ví riêng** (tài khoản Phantom mới, chỉ nạp số tiền
chấp nhận mất), private key chỉ trong biến môi trường, lệnh nhỏ, giới hạn lỗ ngày chặt, kill switch qua Telegram.
Nếu sau 2–3 tuần khoảng tin cậy vẫn chứa 0 hoặc paper âm: dừng ở mức công cụ nghiên cứu, không dùng tiền thật.

---

## 8. Giới hạn đã biết
- Giá lúc vào trong backtest suy ra từ nến GeckoTerminal + tích số dự trữ; sai nếu thanh khoản bị rút trước lúc vào.
- Quy tắc thoát mô phỏng trên giá đóng cửa từng phút; bot thật kiểm tra mỗi 15 giây.
- Bộ thu thập có thể sót pool khi 200 pool mới nhất phủ dưới khoảng 4 phút (sót ngẫu nhiên, không làm lệch kết quả).
- Một giai đoạn thị trường (11/2026). Chưa có MEV, giao dịch thất bại, honeypot chặn bán trong mô phỏng.
- RPC công khai Solana không cam kết ổn định; có Helius dự phòng.

## 9. Lộ trình
1. Tiếp tục thu thập 2–3 tuần; đánh giá hằng tuần (mục 6).
2. Backtest quy tắc dev/bundle khi có đủ `rc_reg`; chạy `wallet_scores`; nếu PASS thì bật follow mode (paper).
3. Mô hình chọn token trên đặc trưng lúc ghi nhận (holder, dev, insider, dự trữ), chia theo thời gian.
4. Chuyển lên VPS (systemd) khi cấu hình ổn định.
5. Chỉ khi đạt mục 7: thêm thực thi thật với ví riêng và tiền nhỏ.

## 10. An toàn
- Không bao giờ dán private key, token Telegram hay key Helius vào chat hoặc commit vào git.
- Không chạy bot "miễn phí" lạ trên GitHub/Telegram trên máy có ví thật (đã có vụ repo giả đánh cắp ví).
- Mọi file `.pkl` tải từ internet chỉ nạp qua unpickler giới hạn (`ml/melt_data.py`).
