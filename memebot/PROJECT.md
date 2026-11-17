# memebot: bot giao dịch memecoin Solana (paper) và hạ tầng nghiên cứu

Kiến trúc, cách chạy, dữ liệu, cách đánh giá và mốc trước khi dùng tiền thật.
Lịch sử kết quả và các con số: [RESULTS.md](RESULTS.md). Bot: [bot/README.md](bot/README.md).
Repo `igod3011/for-fun`, nhánh `claude/mql5-market-product-5p7wht`. Mọi code nằm trong `memebot/`.

---

## 1. Mục tiêu và trạng thái (cập nhật 11/11/2026)

**Mục tiêu cuối:** bot chạy 24/7 tự mua, bán, cắt lỗ, chốt lời memecoin Solana (token vừa tốt nghiệp pump.fun lên
PumpSwap), điều khiển qua Telegram, giao dịch bằng một ví riêng với số tiền nhỏ.

**Trạng thái:**
- Chỉ **paper trading**. Không có ví, private key hay lệnh thật. Chỉ thêm khi đạt mục 7.
- Bộ thu thập chạy từ 06/11/2026, khoảng 2.300 pool mỗi ngày.
- **Chưa có lợi thế.** Với bộ lọc "pool tự nhiên" (11/11 tối) cấu hình hiện tại ở mức hòa vốn ngoài mẫu: TEST −1,3%
  mỗi lệnh, khoảng tin cậy 90% −22%..+30%, mới 34 lệnh. Phí thật 1,2% mỗi swap. Sổ paper đầu tiên mất gần hết 1 SOL sau 15 lệnh; sổ mới mở ngày 11/11/2026.
- Hai điều đã biết chắc: (1) 64% pool tốt nghiệp thật kết thúc bằng một giao dịch xả gần hết nguồn cung từ dàn ví;
  (2) không quy tắc thoát nào cứu được, chỉ có thể tránh từ trước khi mua.

---

## 2. Kiến trúc

```
   GeckoTerminal (pool mới, nến)      RPC công khai Solana (dự trữ, dự trữ ảo, quyền mint: miễn phí)
   RugCheck (dev, cờ rủi ro)          Helius DAS (holder, chỉ pool tốt nghiệp thật: 10 credit/1000 ví)
            │
  collector_daemon ─► collect.py ─► cohort.jsonl        (một dòng ghi nhận mỗi pool, chỉ ghi nối)
                                └─► cohort.fills.jsonl  (nến + kết quả sau ≥3 giờ, chỉ ghi nối)
            │
   ┌────────┴───────────────┬──────────────────────────────┐
   ▼                        ▼                              ▼
 report / healthcheck   ml/entry_timing (walk-forward)   bot/runner (paper, 24/7)
 quote_check            ml/rc_rules (từng quy tắc)       ├─ entry_check: lọc tĩnh + lọc dàn ví
                        ml/select_model (chọn token)     ├─ chờ 90 phút + chặn dao rơi
                        ml/wallet_scores (ví giỏi)       ├─ ảnh holder lần hai + RugCheck/DexScreener
                                                         ├─ paper.buy / exit_decision mỗi 15 giây
                                                         └─ Telegram
```

| File | Vai trò |
|---|---|
| `store.py` | Lưu trữ: đọc/ghi `cohort.jsonl` và `cohort.fills.jsonl`, gộp khi đọc, `--migrate`, `--stats` |
| `collect.py` | Một lượt ghi nhận hoặc một lượt điền kết quả (do daemon gọi) |
| `collector_daemon.py` | Ghi nhận mỗi 2 phút (tính từ đầu lượt), xen kẽ các lượt điền nhỏ (8 pool) |
| `rpc.py` | RPC Solana, công khai trước, Helius dự phòng: dự trữ pool, dự trữ ảo của pool, quyền mint/freeze |
| `helius.py` | Helius DAS: số holder, top 10 địa chỉ; `--selftest`, `--inspect` |
| `quote_check.py` | So công thức swap của bot với báo giá Jupiter qua đúng pool đó (chỉ báo giá) |
| `report.py`, `healthcheck.py` | Báo cáo cohort; PASS/WARN/FAIL cho bộ thu thập và bot |
| `ml/entry_timing.py` | Backtest thời điểm vào + quy tắc thoát; `--grid` walk-forward, `--bot-filter`, `--stop-fill` |
| `ml/rc_rules.py` | Từng quy tắc RugCheck/holder: nhóm bị loại so với nhóm giữ lại, hai nửa thời gian, có CI |
| `ml/select_model.py` | Hồi quy logistic dự đoán pool sống sót từ đặc trưng lúc ghi nhận, chia theo thời gian |
| `ml/wallet_scores.py` | Tìm ví "giỏi" và kiểm tra ngoài mẫu |
| `ml/melt_data.py`, `ml/train_rug_model.py` | Bộ dữ liệu MELT bên ngoài (cần lightgbm; không thuộc phần chạy thật) |
| `bot/amm.py` | Toán swap: `(SOL thật + dự trữ ảo) × token`, phí 1,2% |
| `bot/config.py` | Toàn bộ tham số bot (ghi đè bằng `bot_config.json`) |
| `bot/strategy.py` | Hàm thuần: `entry_check`, `farm_reasons`, `exit_decision`, `Position` |
| `bot/paper.py`, `bot/reset_paper.py` | Sổ paper, nhật ký quyết định; mở sổ mới (lưu sổ cũ vào `archive/`) |
| `bot/intel.py`, `bot/runner.py`, `bot/telegram.py`, `bot/review.py`, `bot/wallets.py` | Kiểm tra trước khi mua, vòng lặp chính, Telegram, tổng hợp nhật ký, theo ví |
| `*.bat` | `restart_collector`, `start_bot`, `reset_paper`, `migrate_store` (Windows) |
| `tests/` | 96 test: `python -m unittest discover -s memebot/tests -t .` |

### Nguyên tắc
- **Chỉ thư viện chuẩn Python 3.9+** cho phần chạy thật.
- **Lợi nhuận = số SOL pool thật sự trả** (`bot/amm.py`), không dùng giá giao dịch cuối. Pool do pump.fun migrate
  định giá theo `(SOL thật + dự trữ ảo) × token`. Dự trữ ảo **khác nhau theo pool** (đa số khoảng 17,56 SOL, có pool
  15,3 / 11,2 / 2,9; pool không do migrate là 0) nên luôn dùng giá trị đọc on-chain của chính pool đó.
- **Không nhìn trước tương lai.** Chỉ dùng thông tin có tại thời điểm quyết định.
- **Walk-forward, có khoảng tin cậy.** Một quy tắc chỉ được giữ nếu tốt hơn khi không có nó trên cùng dữ liệu, ở cả
  hai nửa thời gian.
- **Mọi quyết định của bot đều ghi kèm lý do** và đủ số liệu để mô phỏng lại (`bot_trades.jsonl`).

---

## 3. Cài đặt và chạy (Windows, Command Prompt)

```
cd C:\Users\PC1433\memebot\for-fun-claude-mql5-market-product-5p7wht
set HELIUS_API_KEY=...
set TELEGRAM_BOT_TOKEN=...
set TELEGRAM_CHAT_ID=...
memebot\start_all.bat
python -m memebot.healthcheck
```
- `start_all.bat` chạy cả bộ thu thập lẫn bot. **Sau mỗi lần máy khởi động lại phải chạy lại lệnh này**: bot chỉ mua
  được pool do bộ thu thập ghi nhận, nên chạy riêng `start_bot.bat` thì bot đứng yên (bot sẽ báo Telegram nếu vậy).
- Biến môi trường chỉ sống trong cửa sổ đó; máy khởi động lại thì đặt lại và chạy lại hai file `.bat`.
- Lấy chat id: gửi `hi` cho bot, rồi `python -m memebot.bot.telegram --whoami` (khi bot đang dừng).
- Mở sổ paper mới: `memebot\reset_paper.bat`, rồi `memebot\start_bot.bat`.
- Giữ máy không ngủ: `powercfg /change standby-timeout-ac 0`.
- **Cập nhật code bằng git, không tải zip đè lên nữa** (thư mục đã là repo git từ 11/11/2026; tải zip sẽ ghi đè
  mất các thay đổi chưa đẩy lên).
- Linux/VPS: `export` ba biến, chạy hai lệnh `python3 -m memebot.collector_daemon --out cohort.jsonl` và
  `python3 -m memebot.bot.runner` dưới systemd.

**Lệnh Telegram:** `/status`, `/positions`, `/review [giờ]`, `/pause`, `/resume`, `/sellall`, `/stop`, `/help`.

**Chi phí API:** Helius miễn phí 1 triệu credit/tháng; DAS = 10 credit cho mỗi 1.000 ví. Mỗi pool tốt nghiệp thật
tốn 10–20 credit lúc ghi nhận, cộng 10–20 credit cho mỗi ứng viên bot xét mua. Mọi thứ khác (dự trữ, dự trữ ảo, quyền
mint, GeckoTerminal, RugCheck, DexScreener, báo giá Jupiter) miễn phí và có giới hạn tốc độ.

---

## 4. Dữ liệu (trên máy chạy bot, không có trong git)

| File | Nội dung |
|---|---|
| `cohort.jsonl` | Một dòng ghi nhận mỗi pool PumpSwap mới; chỉ ghi nối |
| `cohort.fills.jsonl`, `cohort.filled.txt` | Kết quả sau ≥3 giờ (nến, RugCheck, dự trữ) và chỉ mục pool đã điền |
| (thứ tự điền nến) | GeckoTerminal giới hạn tốc độ nên chỉ điền được ~2.500 pool/ngày trên ~3.000 pool mới. Từ 13/11/2026: pool chuẩn pump.fun điền trước; pool không chuẩn còn chờ ở 15 giờ tuổi chỉ lưu dự trữ (`candles_skipped`), vì nến đầu của nó đằng nào cũng sắp hết hạn |
| `cohort.snaps.jsonl` | Ảnh chụp holder lần hai lúc pool ~90 phút tuổi (lúc bot quyết định), chỉ với pool qua bộ lọc tĩnh của bot; `store.load` gộp thành `helius_90`. Từ 13/11/2026, ~20 credit Helius mỗi pool (~110 pool/ngày) |
| `bot_trades.jsonl`, `bot_series.jsonl`, `bot_state.json` | Nhật ký quyết định, dự trữ mỗi 15 giây của vị thế, trạng thái |
| `archive/<ngày>/` | Các sổ paper cũ |
| `daemon.log`, `bot.log`, `*.err` | Nhật ký |

```
cohort.jsonl:        pool, mint, name, created, reserve_usd, fdv_usd, registered_at
  helius_reg:        pool_sol, pool_tokens, fetched_at                        (mọi pool, RPC miễn phí)
                     virt_sol, mint_authority, freeze_authority              (pool tốt nghiệp thật, RPC miễn phí, từ 11/11)
                     holders, top1/5/10/20_pct, pool_pct, top_holders, accounts_fetched   (Helius DAS)
  rc_reg:            creator, dev_pct, creator_rugs, creator_launches, insider_pct, insiders_detected, risks
cohort.fills.jsonl:  pool, candles [[ts, o, h, l, c, volume_usd]], rugcheck, helius_fill {pool_sol, pool_tokens}, fetched_at
cohort.snaps.jsonl:  pool, helius_90 {như helius_reg, thêm age_min}
```
- Dòng cũ (trước 11/11/2026) chứa luôn nến trong `cohort.jsonl`; `store.load()` đọc được cả hai dạng.
  Chạy `memebot\migrate_store.bat` một lần để tách chúng ra (51 MB → 6 MB) và bật lịch thu thập mới.
- "Pool tốt nghiệp thật": mint kết thúc bằng `pump` và SOL × token trong 1,0–2,6 × 10¹⁰.
- `holders` bị chặn ở 2 trang (2.000 ví): từ 1.000 trở lên đã là dấu hiệu dàn ví.
- Chia sẻ dữ liệu: nén `cohort*.jsonl` và `bot_*.jsonl`, tải lên Google Drive, gửi link. Không gửi `.log`/`.err`.

---

## 5. Cấu hình bot hiện tại

1. **Lọc tĩnh lúc ghi nhận:** mint pump.fun, pool tốt nghiệp thật, ≥40 SOL, không còn quyền mint/freeze, ghi nhận
   ≤15 phút sau khi tạo, **không phải dàn ví** (dưới 1.000 holder và top 10 từ 15% trở lên), **do pump.fun migrate
   thật** (dự trữ ảo on-chain khác 0) và **không ví nào giữ từ 50% nguồn cung**.
2. **Chờ pool 90 phút tuổi** (cửa sổ 30 phút), pool còn ≥40 SOL và SOL không giảm quá 20% từ lúc ghi nhận.
3. **Ảnh holder lần hai** (ghi lại, chưa dùng làm quy tắc), rồi RugCheck/DexScreener: dev >3%, dev từng rug, đã tăng
   >80% trong 1 giờ thì bỏ.
4. **Mua giả lập 0,2 SOL**, phí 1,2% mỗi swap + 0,0003 SOL mỗi giao dịch.
5. **Thoát:** cắt lỗ 10%, trailing 10% sau +20%, giữ tối đa 60 phút.

Đã bỏ: quy tắc top 10 >50% (thay bằng top 1 ≥50%, xem RESULTS.md), quy tắc insider (không bao giờ kích hoạt), chế độ mua đuổi.

---

## 6. Cách đánh giá

| Tần suất | Lệnh | Nhìn vào đâu |
|---|---|---|
| Hằng ngày | `/status`; `python -m memebot.healthcheck` | `0 fail`; bot còn vốn |
| Hằng tuần | `python -m memebot.ml.entry_timing --data cohort.jsonl --grid --stake 0.2 --max-h1 0.8 --bot-filter` | Dòng `NEW bot rules`: TEST và khoảng tin cậy 90% |
| Hằng tuần | `python -m memebot.ml.rc_rules --data cohort.jsonl --stake 0.2 --max-h1 0.8` | Cột `verdict`; `KEEP` phải lặp lại qua các tuần |
| Hằng tuần | `python -m memebot.ml.select_model --data cohort.jsonl` | AUC trên TEST; trung bình nhóm `kept` và khoảng tin cậy của nó |
| Hằng tuần | `/review 168` | Số lệnh đóng, PnL, PnL theo lý do thoát |
| Hằng tuần | `python -m memebot.quote_check` | Phí suy ra phải gần 1,2%; không có `NO SELL QUOTE` |
| Từ 15–16/11 | `python -m memebot.ml.wallet_scores --data cohort.jsonl` | `PASS` hay `FAIL` |

Trong Claude Code có thể gọi skill `/weekly-eval` để chạy và tóm tắt tất cả.

**Cách đọc:** chỉ số TEST mới nói về tương lai. Khoảng tin cậy chứa 0 nghĩa là chưa phân biệt được với may rủi.
Kết quả paper phải gần backtest; lệch nhiều là mô phỏng đang sai ở đâu đó.

---

## 7. Mốc trước khi dùng tiền thật (cần cả ba)
1. Khoảng tin cậy 90% của cấu hình bot trên TEST **nằm hoàn toàn trên 0**, với ít nhất 200 lệnh TEST.
2. Bot paper có **ít nhất 100 lệnh đóng** với PnL dương sau phí.
3. Kết quả paper gần với backtest, và `quote_check` khớp.

Khi đạt: thực thi qua Jupiter Swap API, ký tại máy, **ví riêng** chỉ nạp số tiền chấp nhận mất, private key chỉ trong
biến môi trường, lệnh nhỏ, giới hạn lỗ ngày chặt, kill switch qua Telegram.
**Điểm dừng:** nếu đến cuối tháng 11/2026 khoảng tin cậy vẫn chứa 0 hoặc paper âm, dừng ở mức công cụ nghiên cứu.

---

## 8. Giới hạn đã biết
- Giá vào trong backtest suy ra từ nến GeckoTerminal; quy tắc thoát mô phỏng trên nến 1 phút, bot thật kiểm tra mỗi
  15 giây. Cắt lỗ trong nến khớp theo `--stop-fill` (mặc định không tốt hơn giá đóng nến).
- Dự trữ ảo trong backtest lấy lúc ghi nhận và coi là không đổi; pool ghi nhận trước 11/11 dùng 17,584 SOL.
- Phí 1,2% đo ở vốn hóa 250–1.500 SOL; ở vốn hóa cao hơn phí thấp hơn một chút (chưa mô hình hóa).
- Backtest không áp dụng các kiểm tra RugCheck/DexScreener lúc mua (chỉ có `--max-h1`).
- Chưa mô phỏng trượt giá do cạnh tranh, giao dịch thất bại, MEV, phí ưu tiên lúc thị trường nóng.
- Mới một giai đoạn thị trường (11/2026), một tuần dữ liệu.

## 9. Việc tiếp theo
1. Thu thập tiếp; đánh giá hằng tuần (mục 6). Sổ paper mới là phép thử ngoài mẫu của bộ lọc dàn ví.
2. Khi có 1–2 tuần dữ liệu ảnh holder lần hai: kiểm tra tốc độ tăng holder có tách được pool bị xả không.
3. `wallet_scores` từ 15–16/11; chỉ bật theo ví (paper) nếu `PASS`.
4. Chuyển lên VPS (systemd) khi cấu hình ổn định.
5. Chỉ khi đạt mục 7: thêm thực thi thật.

## 10. An toàn
- Không bao giờ dán private key, token Telegram hay key Helius vào chat hoặc commit vào git.
- Không chạy bot "miễn phí" lạ trên máy có ví thật.
- File `.pkl` tải từ internet chỉ nạp qua unpickler giới hạn (`ml/melt_data.py`).
