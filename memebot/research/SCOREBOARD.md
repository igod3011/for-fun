# Bảng giả thuyết đã thử (cập nhật 13/11/2026)

Mọi con số là sau phí, trên dữ liệu thật. "Hai nửa" là nửa đầu và nửa sau của dữ liệu theo thời gian. Chi tiết và
cách đo: `memebot/RESULTS.md`. Chưa có giả thuyết nào qua ngưỡng "backtest → paper" ở `PHASE1_AUDIT.md` mục 4.

## Memecoin (pool pump.fun đã lên PumpSwap, lệnh 0,2 SOL, phí 1,2% mỗi chiều)

| # | Giả thuyết | Số lệnh | Kỳ vọng mỗi lệnh | CI 90% | Hai nửa | Kết luận |
|---|---|---|---|---|---|---|
| M1 | Mua mọi pool chuẩn ở phút 90 | 235 | −12,2% | −19,2%..−4,0% | +3,8% / −26,0% | Loại |
| M2 | M1 + lọc dàn ví + loại ví giữ ≥50% ("pool tự nhiên") | 76 | +8,6% | −10,6%..+31,9% | +18,4% / +1,1% | Chưa chứng minh; đang chạy paper |
| M3 | Mua nhanh sau khi lên sàn (2–20 phút) | 1.132–1.742 | −17,5%..−28,4% | nằm dưới 0 | cả hai âm | Loại |
| M4 | Mua sau cú giảm ≥25/35/50% | 104–160 | −9,3%..−10,8% | nằm dưới 0 | cả hai âm | Loại |
| M5 | Giảm sâu rồi chờ bật +10/+20% mới mua | 90–143 | −7%..−12% | nằm dưới 0 | cả hai âm | Loại |
| M6 | Bỏ lệnh vừa bật ≥30% từ đáy | 49 giữ lại | −8,4% | −17,7%..+0,8% | −2,8% / −11,9% | Loại (bỏ mất lệnh thắng lớn) |
| M7 | 432 cấu hình cắt lỗ/chốt lời rộng trên pool tự nhiên | — | — | — | 0% cấu hình dương ở cả hai nửa | Loại |
| M8 | Giữ pool sống sót 1–48 giờ | 125 | −39,9% ở 24 giờ | — | — | Loại |
| M9 | Mô hình chọn token (hồi quy logistic, AUC 0,856) | — | nhóm điểm cao vẫn lỗ | — | — | Loại |
| M10 | Theo ví giỏi (`wallet_scores`) | 6 pool kiểm tra | — | — | — | Thiếu dữ liệu; chạy lại từ 15–16/11 |
| M11 | Không mua khi top 10 holder sụt mạnh từ lúc ghi nhận | 4 lệnh paper | 2 mất gần hết, 1 lỗ nhỏ, 1 lãi | — | — | Thiếu dữ liệu; đang thu `helius_90` |

## Futures (Binance USDT perpetual, phí 0,07% mỗi chiều, funding thật)

| # | Giả thuyết | Mẫu | Kết quả kiểm tra | CI 90% | Hai nửa | Kết luận |
|---|---|---|---|---|---|---|
| F1 | Giao cắt EMA trên PEPE, PUMP (10 USD x5, nến 1h) | 146 / 52 lệnh | −48 USD / −27 USD | PEPE nằm dưới 0 | lãi lúc chọn, lỗ lúc kiểm tra | Loại |
| F2 | Phá đỉnh/đáy Donchian | 66 / 32 lệnh | −17 USD / −9 USD | chứa 0 | như trên | Loại |
| F3 | RSI bắt đảo chiều | 40 / 69 lệnh | −9 USD / +6 USD | chứa 0 | — | Chưa chứng minh |
| F4 | Bollinger bắt đảo chiều (1h và 4h) | 37–197 lệnh | −7..+20 USD | chứa 0 | không ổn định | Chưa chứng minh |
| F5 | Bán khống coin mới niêm yết (ngày 7, giữ 30 ngày, cắt lỗ +50%, kèm mua BTC) | 422 coin | +6,4% mỗi lệnh | +3,4%..+9,6% | +10,5% / +2,2% | Từng có lãi rõ (2024 đến giữa 2025), nay gần 0; theo dõi bằng paper nếu được duyệt |
| F6 | Động lượng 1 tuần, mua nhóm tăng mạnh / bán nhóm giảm mạnh | 210 tuần | +0,39% mỗi tuần | −0,14%..+0,99% | −0,21% / +0,98% | Chưa chứng minh |
| F7 | Động lượng 4 tuần | 210 tuần | +0,13% mỗi tuần | −0,41%..+0,66% | 0,00% / +0,25% | Chưa chứng minh |
| F8 | Đảo chiều 1 tuần (mua nhóm giảm / bán nhóm tăng) | 210 tuần | −0,67% mỗi tuần | nằm dưới 0 | cả hai âm | Loại |

Lưu ý cho F5–F8: danh sách coin lấy từ sàn hôm nay nên thiếu các hợp đồng đã hủy niêm yết (thiên lệch sống sót).

## Chưa thử, đã sàng lọc sơ bộ

| Ngách | Sàng lọc | Ghi chú |
|---|---|---|
| Ăn funding trung lập giá (mua spot, bán perp) | Khả thi với vốn nhỏ, dữ liệu miễn phí | Lợi suất thấp (PUMP đo được 8,9% một năm cho bên bán); cần đo phí vào ra và rủi ro funding đổi dấu |
| Thông tin trước khi lên sàn (ai mua trên đường cong giá) | Khả thi ở dạng paper, tốn credit Helius | Chưa có dữ liệu; cần đo chi phí trước |
| Bắn tỉa block đầu | Không khả thi | Cần hạ tầng trả phí, tiền thật ngay từ đầu, không thử paper được |
| Market making, chênh lệch liên sàn, tam giác, MEV | Không khả thi với vốn nhỏ và máy cá nhân | Cần vốn lớn, độ trễ thấp hoặc nhiều tài khoản sàn |
