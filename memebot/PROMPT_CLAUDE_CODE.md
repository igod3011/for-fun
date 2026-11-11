# Prompt tổng quan để dán vào Claude Code

Dán nguyên phần trong khung dưới vào phiên Claude Code mới, mở tại thư mục gốc của dự án (thư mục chứa `memebot/`).
Nếu repo có `CLAUDE.md` ở gốc thì Claude Code đã tự đọc, prompt này bổ sung bối cảnh và việc cần làm.

```
Bạn tiếp quản dự án "memebot": hạ tầng nghiên cứu + bot giao dịch PAPER cho memecoin Solana (token vừa tốt nghiệp
pump.fun lên PumpSwap), chạy 24/7 trên máy Windows của tôi, điều khiển qua Telegram.

Việc đầu tiên:
1. Đọc memebot/PROJECT.md (kiến trúc, schema dữ liệu, kết quả, cách đánh giá, mốc trước khi dùng tiền thật)
   và CLAUDE.md ở gốc (quy tắc bắt buộc).
2. Chạy: python -m unittest discover -s memebot/tests -t .   (phải đạt hết trước khi sửa gì)
3. Tóm tắt lại cho tôi bằng tiếng Việt: hệ thống đang làm gì, kết quả đến nay, việc tiếp theo hợp lý nhất.

Bối cảnh:
- Bộ thu thập (memebot.collector_daemon) ghi mọi pool PumpSwap mới vào cohort.jsonl: dự trữ pool (RPC công khai),
  holder + top 10 địa chỉ (Helius DAS, chỉ pool tốt nghiệp thật), RugCheck lúc ghi nhận, nến 1 phút + dự trữ lúc điền.
- Bot (memebot.bot.runner) lọc tĩnh, chờ pool 90 phút tuổi, chặn "dao rơi", kiểm tra RugCheck/DexScreener
  (dev >3%, dev từng rug, insider >10%, đã tăng >80% trong 1 giờ), mua giả lập 0,2 SOL, thoát: SL 10%,
  trailing 10% sau +20%, giữ tối đa 60 phút. Tin nhắn Telegram có CA, giá, vốn hóa.
- Kết quả: mua mù token tốt nghiệp lỗ khoảng −75%. Cấu hình hiện tại dương khoảng +3% mỗi lệnh trên TEST
  (walk-forward, 63 lệnh) nhưng khoảng tin cậy 90% còn chứa 0, nên CHƯA chứng minh được lợi thế.
- Dữ liệu (cohort.jsonl, bot_trades.jsonl, bot_series.jsonl, bot_state.json) nằm trên máy tôi, không có trong git.
  Nếu cần phân tích, hỏi tôi gửi file (zip qua Google Drive).

Quy tắc bắt buộc (chi tiết trong CLAUDE.md):
- Chỉ paper. Không viết phần giao dịch thật, ví, private key trừ khi tôi yêu cầu VÀ đạt mốc ở PROJECT.md mục 7.
  Không bao giờ bảo tôi dán key/token vào chat.
- Code chạy thật chỉ dùng thư viện chuẩn Python (chạy trên Windows và VPS Linux không cần cài gì).
- Lợi nhuận tính bằng SOL thật rút được từ pool (constant product trên dự trữ thật), không dùng giá giao dịch cuối.
- Không nhìn trước tương lai; đánh giá walk-forward có khoảng tin cậy; một quy tắc chỉ được giữ nếu tốt hơn khi không
  có nó trên cùng dữ liệu ở cả hai nửa thời gian. Báo cáo trung thực, kể cả khi kết quả xấu.
- Tiết kiệm credit Helius (gói miễn phí 1 triệu/tháng; DAS = 10 credit).
- Mọi thay đổi: thêm test, chạy toàn bộ test, chỉ commit khi đạt. Hướng dẫn cho tôi bằng tiếng Việt, từng lệnh để
  copy (tôi dùng Command Prompt trên Windows), kèm cách kiểm tra đã chạy đúng.

Việc đang chờ (theo PROJECT.md mục 9):
- Đánh giá hằng tuần: entry_timing --grid --stake 0.2 --max-h1 0.8 và /review 168.
- Khi có đủ dữ liệu rc_reg: backtest quy tắc dev/bundle. Khi có 5–7 ngày địa chỉ ví: chạy ml.wallet_scores.
- Mô hình chọn token trên đặc trưng lúc ghi nhận (chia theo thời gian).
- Sau này: chuyển lên VPS (systemd).
```
