# Phase 1: Audit hệ thống và đánh giá Master Prompt (13/11/2026)

Tài liệu này trả lời nhiệm vụ đầu tiên của Master Prompt "Crypto Profitability Research". Không có code giao dịch
nào được thêm ở giai đoạn này. Số liệu lấy từ sổ paper (`bot_trades.jsonl`, `archive/`), `cohort.jsonl` và các
backtest đã ghi trong `memebot/RESULTS.md`. Bảng các giả thuyết đã thử nằm ở `SCOREBOARD.md` cùng thư mục.

## 1. Kiến trúc hiện tại

| Bộ phận | File | Trạng thái |
|---|---|---|
| Thu thập dữ liệu (pool PumpSwap mới, nến, holder, ảnh chụp 90 phút) | `collector_daemon.py`, `collect.py`, `store.py`, `rpc.py`, `helius.py` | Chạy 24/7, giữ lại |
| Công cụ nghiên cứu (walk-forward, CI bootstrap, kiểm tra quy tắc) | `ml/entry_timing.py`, `ml/rc_rules.py`, `ml/select_model.py`, `ml/wallet_scores.py` | Dùng được, giữ lại; là hạt nhân của Research Engine |
| Bot paper + Telegram | `bot/runner.py`, `strategy.py`, `paper.py`, `intel.py`, `telegram.py` | Chạy đúng như thiết kế; chiến lược nó chạy không có lợi thế |
| Giám sát | `healthcheck.py`, `quote_check.py`, cảnh báo bộ thu thập dừng | Giữ lại |

Chưa có: dữ liệu futures trong repo (mới ở script tạm), dữ liệu trước khi token lên sàn, sổ đăng ký giả thuyết
tự động, mô phỏng Monte Carlo.

## 2. Vì sao tài khoản âm

Hai sổ paper, mỗi lệnh 0,2 SOL trên vốn 1 SOL:

| | Sổ cũ (09–11/11) | Sổ hiện tại (11–13/11) |
|---|---|---|
| Lệnh đã đóng | 15 | 20 |
| Tổng lãi lỗ | −0,998 SOL | −0,582 SOL |
| Tỉ lệ thắng | 20% | 35% |
| Lãi TB lệnh thắng / lỗ TB lệnh thua | +0,002 / −0,084 SOL | +0,038 / −0,065 SOL |
| Profit factor | 0,01 | 0,31 |
| Sụt giảm lớn nhất | −0,998 SOL | −0,669 SOL |
| Số lệnh mất hơn 0,1 SOL | 4 lệnh = −0,774 SOL | 3 lệnh = −0,578 SOL |
| Thoát lệnh | 10 cắt lỗ, 2 trailing, 3 hết giờ | 12 cắt lỗ, 4 trailing, 4 hết giờ |

Phân loại nguyên nhân theo danh mục của Master Prompt:

1. **Sai chiến lược (nguyên nhân gốc).** Mua pool đã lên sàn ở phút 90 bằng dữ liệu công khai không có lợi thế
   thông tin. Walk-forward trên pool tự nhiên: +8,6% mỗi lệnh nhưng CI 90% là −10,6%..+31,9% và trung vị −10,3%.
   Hơn 10 nhóm quy tắc đã thử, không nhóm nào có CI nằm trên 0 ở cả hai nửa thời gian (xem `SCOREBOARD.md`).
2. **Rủi ro đuôi không kiểm soát được bằng cắt lỗ.** Ở sổ hiện tại, 3 lệnh mất gần hết chiếm −0,578 trong −0,582
   SOL; 17 lệnh còn lại gần hòa vốn. Một cú xả là một giao dịch duy nhất, nên cắt lỗ −10% (kiểm tra mỗi 15 giây)
   khớp ở −97%..−99%. Trong backtest, 7/76 lệnh mất hơn 50%.
3. **Quản trị vốn không phù hợp.** Mỗi lệnh đặt 20% tài khoản vào một tài sản có khoảng 9% khả năng mất gần hết.
   Mức này chọn để giảm tỉ trọng phí cố định trong phép đo paper; với tiền thật là quá lớn.
4. **Chi phí.** Phí swap 1,2% mỗi chiều (đo bằng báo giá thật) cộng phí cố định: khoảng 2,7% mỗi lệnh khứ hồi.
   Lệnh thắng trung bình chỉ +19% vốn lệnh, lệnh thua −33%: chi phí ăn một phần đáng kể của lợi thế vốn không có.
5. **Lỗi đo lường đã sửa (11/11).** Backtest cũ coi cắt lỗ khớp đúng mức stop (+3% ảo), phí giả định 0,5% thay vì
   1,2%, bỏ qua dự trữ ảo của pool. Sổ cũ chạy trên các giả định sai đó.
6. **Sự cố vận hành.** Máy khởi động lại làm bộ thu thập dừng 18 giờ (đã có cảnh báo); hàng chờ điền nến (đã sửa).
   Không gây lỗ, nhưng làm mất dữ liệu.

Không phải nguyên nhân: overtrading (7–9 lệnh mỗi ngày), độ trễ API, lỗi khớp lệnh mô phỏng (đã đối chiếu báo giá
Jupiter).

**Kết luận audit:** phần hạ tầng đúng và nên giữ. Thứ cần thay là nguồn lợi thế, không phải tham số.

## 3. Đánh giá Master Prompt

Điểm mạnh, giữ nguyên: lấy kỳ vọng sau phí làm tiêu chí; "không giao dịch cũng là quyết định đúng"; làm theo
giai đoạn và chờ xác nhận; tách Research khỏi Trading; cấm số liệu giả định.

Điểm cần sửa trước khi dùng làm kim chỉ nam:

| # | Vấn đề | Đề xuất sửa |
|---|---|---|
| 1 | Phạm vi khoảng 45 ngách, nhiều ngách bất khả thi với vốn nhỏ và máy cá nhân (market making, chênh lệch liên sàn, tam giác, MEV, cụm thanh lý cần dữ liệu trả phí, độ trễ thấp hoặc vốn lớn) | Thêm bước sàng lọc khả thi TRƯỚC backtest: vốn tối thiểu, dữ liệu miễn phí hay không, có cần tốc độ không. Chỉ backtest ngách qua sàng |
| 2 | Thử hàng chục chiến lược nhân nhiều tham số chắc chắn sinh kết quả đẹp giả (đa kiểm định). Prompt chưa có cơ chế chống | Đăng ký giả thuyết trước khi chạy, đếm số lần thử, ngưỡng chặt dần theo số lần thử, và bắt buộc xác nhận lại bằng paper |
| 3 | "Tiêu chí được xác định trước" nhưng không có con số nào | Dùng một bộ ngưỡng duy nhất, đề xuất ở mục 4, thay cho PROJECT.md mục 7 nếu bạn duyệt |
| 4 | "Vốn nhỏ" không có con số. Lợi thế rủi ro thấp thật (ăn funding) chỉ khoảng 5–10% một năm: trên 100 USD là 5–10 USD | Cần bạn cho số vốn và mức lỗ tối đa chấp nhận. Mười tiêu chí ở mục 1.2 không thể cùng đạt; phải xếp thứ tự ưu tiên |
| 5 | Xếp hạng bằng Sharpe/Sortino trên vài chục lệnh là nhiễu | Xếp hạng theo cận dưới CI của kỳ vọng ròng, sau đó mới tới sụt giảm và sức chứa vốn |
| 6 | Đòi dữ liệu đủ thị trường tăng, giảm, đi ngang | Futures có khoảng 1,5 năm; dữ liệu memecoin của ta mới 8 ngày. Ghi rõ giới hạn trong từng báo cáo thay vì coi như đạt |
| 7 | Mục 4 (Execution Engine, Portfolio Manager, API key, database, nhiều sàn) và Phase 3–5 | Hoãn toàn bộ cho tới khi có một chiến lược qua ngưỡng. Xây trước là lãng phí, và trái quy tắc "chỉ paper, chỉ thư viện chuẩn" đang có hiệu lực |
| 8 | "Tự động điều chỉnh vốn theo hiệu suất" | Là chạy theo thành tích gần đây; tắt cho tới khi có lịch sử dài |
| 9 | Phase 1 vừa cấm sửa code vừa yêu cầu "chuẩn bị nền tảng nghiên cứu" | Tôi hiểu là chỉ tài liệu và sổ giả thuyết; code Research Engine chờ bạn duyệt |
| 10 | Thiếu ngân sách cho chính việc nghiên cứu (credit Helius, dữ liệu trả phí, thời gian) và điều kiện dừng | Mỗi giả thuyết có điều kiện loại bỏ viết trước; giữ điểm dừng cuối 11/2026 cho hướng memecoin |

## 4. Đề xuất: Research Engine (Crypto Strategy Discovery Engine)

Không giao dịch. Đầu ra duy nhất là bảng xếp hạng giả thuyết kèm bằng chứng. Thiết kế tối thiểu:

1. **Sổ giả thuyết** (`research/hypotheses.json`): mỗi giả thuyết có cơ chế tạo lãi, dữ liệu cần, điều kiện loại
   bỏ viết trước, số lần đã thử, kết quả, trạng thái.
2. **Bộ chấm chuẩn** dùng chung cho mọi giả thuyết (tái sử dụng `ml/entry_timing.py`): nhận danh sách lệnh đã
   tính phí, trả về kỳ vọng ròng, CI bootstrap, kết quả từng nửa thời gian, profit factor, sụt giảm lớn nhất và
   Monte Carlo xáo thứ tự lệnh (xác suất sụt giảm vượt ngưỡng).
3. **Nguồn dữ liệu dạng mô-đun:** `cohort` (đã có), futures Binance công khai (đã thử, miễn phí), sau đó mới tới
   dữ liệu trước khi lên sàn.
4. **Lệnh chạy định kỳ** in lại bảng xếp hạng; Telegram chỉ báo khi một giả thuyết đổi trạng thái.

Ngưỡng đề xuất để một giả thuyết được chuyển sang paper, rồi sang Trading Engine:

| Cổng | Điều kiện |
|---|---|
| Backtest → paper | Kỳ vọng ròng sau phí dương ở CẢ HAI nửa thời gian; cận dưới CI 90% trên 0 trên toàn mẫu; ít nhất 100 lệnh; không phụ thuộc vào dưới 5 lệnh thắng lớn |
| Paper → tiền thật | Ít nhất 100 lệnh paper trong ít nhất 4 tuần; kết quả paper nằm trong CI của backtest; sụt giảm lớn nhất dưới mức bạn đặt; bạn yêu cầu bằng lời |
| Loại bỏ | Vi phạm điều kiện loại bỏ viết trước, hoặc cận trên CI dưới 0 |

## 5. Cần bạn xác nhận trước Phase 2

1. Số vốn dự kiến và mức lỗ tối đa chấp nhận (để sàng lọc ngách theo vốn).
2. Duyệt bộ ngưỡng ở mục 4.
3. Duyệt việc viết code Research Engine (chỉ nghiên cứu, chỉ thư viện chuẩn, không có code giao dịch).
