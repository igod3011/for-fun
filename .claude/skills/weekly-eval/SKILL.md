---
name: weekly-eval
description: Đánh giá hằng tuần dự án memebot - chạy healthcheck, backtest walk-forward, kiểm tra từng quy tắc, mô hình chọn token, đối chiếu báo giá và tổng hợp sổ paper, rồi tóm tắt bằng tiếng Việt so với tuần trước. Dùng khi người dùng nói "đánh giá tuần", "weekly", "kết quả tuần này", hoặc /weekly-eval.
---

# Đánh giá hằng tuần memebot

Chạy từ thư mục gốc dự án (thư mục chứa `memebot/` và `cohort.jsonl`). Mọi lệnh chỉ đọc dữ liệu; không lệnh nào đổi
cấu hình hay đụng vào bot/bộ thu thập đang chạy. Không đọc thẳng `cohort*.jsonl` vào ngữ cảnh (hàng chục MB).

## Bước 1. Chạy (lọc đầu ra để tiết kiệm token)

```bash
python -m memebot.healthcheck | tail -n 14
python -m memebot.ml.entry_timing --data cohort.jsonl --grid --stake 0.2 --max-h1 0.8 --bot-filter | grep -E "bot static|^pools|NEW bot|hindsight"
python -m memebot.ml.entry_timing --data cohort.jsonl --grid --stake 0.2 --max-h1 0.8 | grep -E "^pools|NEW bot"
python -m memebot.ml.rc_rules --data cohort.jsonl --stake 0.2 --max-h1 0.8 | grep -E "^canonical|baseline|KEEP|bot:|unproven"
python -m memebot.ml.select_model --data cohort.jsonl | grep -E "canonical|TEST|kept|no selection"
python -m memebot.quote_check -n 8 | tail -n 14
python -m memebot.bot.review --since-hours 168
python -m memebot.ml.wallet_scores --data cohort.jsonl --out smart_wallets.json | tail -n 4
```

`wallet_scores` chỉ chạy khi đã có ít nhất 5 ngày dữ liệu địa chỉ ví (từ 15/11/2026). Lệnh grid mất vài phút.
Nếu một lệnh lỗi, báo nguyên văn dòng lỗi và chạy tiếp các lệnh còn lại.

## Bước 2. Đọc kết quả

- **Con số duy nhất nói về tương lai:** dòng `NEW bot rules` của lần chạy có `--bot-filter`: TEST, n, khoảng tin cậy 90%.
- Khoảng tin cậy chứa 0 = chưa phân biệt được với may rủi. Nằm hoàn toàn dưới 0 = chắc chắn lỗ.
- `rc_rules`: quy tắc nào của bot (`bot:`) đang `no` thì phải đề xuất bỏ; quy tắc `x:` chỉ đáng tin khi `KEEP` lặp lại
  qua nhiều tuần (mỗi lần thử nhiều quy tắc, một `KEEP` có thể là may).
- `select_model`: nhìn trung bình của nhóm `kept` và khoảng tin cậy của nó, không phải AUC.
- `quote_check`: phí suy ra phải gần `BotConfig.fee`; có dòng `MISMATCH` hoặc `NO SELL QUOTE` thì nêu lên đầu báo cáo.
- So sổ paper (`review`) với backtest: lệch nhiều nghĩa là mô phỏng sai ở đâu đó, cần tìm trước khi tin số nào.

## Bước 3. Báo cáo cho người dùng (tiếng Việt, ngắn)

1. Một câu kết luận: có lợi thế chưa, so với tuần trước tốt lên hay xấu đi.
2. Bảng: TEST có/không bộ lọc bot (n, CI), PnL sổ paper tuần (số lệnh, tỷ lệ thắng), phí đo được.
3. Quy tắc nào đổi kết luận so với `memebot/RESULTS.md`.
4. Ba mốc ở `memebot/PROJECT.md` mục 7: đạt/chưa, còn cách bao xa.
5. Đề xuất cụ thể (nếu có), mỗi đề xuất kèm bằng chứng; không tự đổi cấu hình bot.

Sau đó thêm một mục có ngày tháng lên đầu `memebot/RESULTS.md` với các con số vừa đo, chạy test, và commit.
Không bao giờ đề xuất dùng tiền thật khi chưa đạt cả ba mốc.
