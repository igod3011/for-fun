# Bảng xếp hạng giả thuyết (tự sinh)

Tạo lúc 2026-11-13 20:24 bằng `python -m memebot.research.run`. Đừng sửa tay: chạy lại lệnh đó.
Tài khoản nghiên cứu 100 USD, mức lỗ tối đa chấp nhận 50 USD. Mọi con số là sau phí.
Xếp theo: đã qua ngưỡng trước, rồi tới cận dưới của lãi ròng một năm (không xếp theo trung bình).

| Hạng | Mã | Giả thuyết | Kết luận | Số lệnh | Kỳ vọng mỗi lệnh | Khoảng tin cậy | Nửa đầu / nửa sau | Thắng | Lãi ròng 1 năm (cận dưới .. trung bình) | Xác suất lỗ quá 50 USD trong 1 năm |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | F5 | Bán khống coin mới niêm yết từ ngày 7, giữ 30 ngày, cắt lỗ +50%, kèm mua BTC | ĐẠT, chuyển sang paper | 422 | +7.0% | +1.7% .. +12.1% (99.3%) | +10.3% / +3.6% | 65% | +13 .. +54 USD | 0% |
| 2 | C1 | Ăn funding trung lập giá: mua spot, bán perp ở coin có funding cao | ĐẠT, chuyển sang paper | 136 | +0.2% | +0.1% .. +0.3% (95.0%) | +0.1% / +0.4% | 88% | +4 .. +6 USD | 0% |
| 3 | F6 | Động lượng 1 tuần: mua nhóm 20% tăng mạnh nhất, bán nhóm 20% giảm mạnh nhất | Chưa chứng minh | 210 | +0.4% | -0.3% .. +1.2% (97.5%) | -0.2% / +1.0% | 47% | -9 .. +10 USD | 0% |
| 4 | F1 | Theo xu hướng EMA 20/100 nến 1h trên PEPE và PUMP (10 USD x5) | Chưa chứng minh | 333 | +2.0% | -6.0% .. +12.4% (99.6%) | +5.8% / -1.7% | 23% | chạm mức dừng -50 .. +45 USD | 35% |
| 5 | M2 | Chỉ pool tự nhiên (lọc dàn ví, loại ví giữ từ 50%) lúc 90 phút | Chưa chứng minh | 93 | +4.7% | -14.3% .. +30.4% (97.5%) | +13.1% / -3.6% | 31% | chạm mức dừng -50 .. +1130 USD | 32% |
| 6 | M4 | Mua sau cú giảm từ 35% so với đỉnh 30 phút (pool tự nhiên) | Loại | 190 | -9.8% | -16.2% .. -3.2% (98.9%) | -9.9% / -9.7% | 21% | chạm mức dừng -50 .. chạm mức dừng -50 USD | 100% |
| 7 | M1 | Mua mọi pool chuẩn pump.fun lúc 90 phút tuổi | Loại | 287 | -14.4% | -20.6% .. -7.2% (90.0%) | -1.4% / -27.2% | 27% | chạm mức dừng -50 .. chạm mức dừng -50 USD | 100% |
| 8 | M3 | Mua nhanh: 5 phút sau khi lên sàn | Loại | 1698 | -22.5% | -27.6% .. -16.8% (98.0%) | -27.9% / -17.0% | 22% | chạm mức dừng -50 .. chạm mức dừng -50 USD | 100% |

## Chi tiết từng giả thuyết

### F5. Bán khống coin mới niêm yết từ ngày 7, giữ 30 ngày, cắt lỗ +50%, kèm mua BTC
- Cơ chế: Coin mới được niêm yết ở đỉnh chú ý; người giữ từ trước bán dần trong các tuần sau.
- Điều kiện loại bỏ (viết trước): Loại nếu kỳ vọng âm ở nửa sau thêm một quý nữa, hoặc funding của bên bán âm hơn 3% mỗi lệnh.
- Kết luận: **ĐẠT, chuyển sang paper** (qua mọi ngưỡng).
- Cỡ lệnh 5 USD, khoảng 154 lệnh mỗi năm, dữ liệu 998 ngày, đã thử 15 biến thể. Trung vị +17.1%, lệnh tệ nhất -76.0%, profit factor 1.49, bỏ 4 lệnh thắng lớn nhất còn +6.2%, 20% lệnh gần nhất +4.9%.
- Mô phỏng 1 năm (154 lệnh, xáo ngẫu nhiên): lãi lỗ 5% xấu nhất +14 USD, trung vị +54 USD, 5% tốt nhất +95 USD.
- Lưu ý: thiếu các hợp đồng đã hủy niêm yết; đòn bẩy x1, không dùng được x5 vì cắt lỗ ở +50%; khoảng 13 vị thế mở cùng lúc nên mỗi lệnh chỉ 5 USD; các lệnh chồng thời gian và cùng chịu một cú tăng của altcoin, nên xác suất lỗ lớn thực tế cao hơn con số mô phỏng.

### C1. Ăn funding trung lập giá: mua spot, bán perp ở coin có funding cao
- Cơ chế: Người long dùng đòn bẩy trả funding cho người short; giữ spot để triệt tiêu biến động giá.
- Điều kiện loại bỏ (viết trước): Loại nếu lợi suất ròng sau phí dưới 5% một năm trên vốn sử dụng, hoặc khoảng tin cậy chứa 0.
- Kết luận: **ĐẠT, chuyển sang paper** (qua mọi ngưỡng).
- Cỡ lệnh 30 USD, khoảng 92 lệnh mỗi năm, dữ liệu 539 ngày, đã thử 2 biến thể. Trung vị +0.1%, lệnh tệ nhất -1.5%, profit factor 10.06, bỏ 4 lệnh thắng lớn nhất còn +0.2%, 20% lệnh gần nhất +0.5%.
- Mô phỏng 1 năm (92 lệnh, xáo ngẫu nhiên): lãi lỗ 5% xấu nhất +4 USD, trung vị +6 USD, 5% tốt nhất +8 USD.
- Lưu ý: bỏ qua chênh lệch spot-perp và giả định coin nào cũng có thị trường spot; vốn dùng gấp đôi vị thế.

### F6. Động lượng 1 tuần: mua nhóm 20% tăng mạnh nhất, bán nhóm 20% giảm mạnh nhất
- Cơ chế: Coin đang mạnh tiếp tục mạnh hơn coin đang yếu trong tuần kế tiếp.
- Điều kiện loại bỏ (viết trước): Loại nếu cả khoảng tin cậy nằm dưới 0.
- Kết luận: **Chưa chứng minh** (khoảng tin cậy chứa 0; không dương ở cả hai nửa; âm nếu bỏ 4 lệnh thắng lớn nhất).
- Cỡ lệnh 50 USD, khoảng 52 lệnh mỗi năm, dữ liệu 1463 ngày, đã thử 4 biến thể. Trung vị -0.3%, lệnh tệ nhất -14.4%, profit factor 1.26, bỏ 4 lệnh thắng lớn nhất còn -0.0%, 20% lệnh gần nhất -0.6%.
- Mô phỏng 1 năm (52 lệnh, xáo ngẫu nhiên): lãi lỗ 5% xấu nhất -18 USD, trung vị +10 USD, 5% tốt nhất +42 USD.
- Lưu ý: mỗi tuần là một lệnh trên tổng vị thế 50 USD; coi như đổi toàn bộ danh mục hằng tuần.

### F1. Theo xu hướng EMA 20/100 nến 1h trên PEPE và PUMP (10 USD x5)
- Cơ chế: Xu hướng giá kéo dài; chỉ báo trung bình động bắt được nó.
- Điều kiện loại bỏ (viết trước): Loại nếu cả khoảng tin cậy nằm dưới 0, hoặc lãi lúc chọn tham số nhưng lỗ lúc kiểm tra.
- Kết luận: **Chưa chứng minh** (khoảng tin cậy chứa 0; không dương ở cả hai nửa; âm nếu bỏ 4 lệnh thắng lớn nhất).
- Cỡ lệnh 10 USD, khoảng 224 lệnh mỗi năm, dữ liệu 542 ngày, đã thử 24 biến thể. Trung vị -13.7%, lệnh tệ nhất -71.9%, profit factor 1.15, bỏ 4 lệnh thắng lớn nhất còn -2.6%, 20% lệnh gần nhất -2.0%.
- Mô phỏng 1 năm (224 lệnh, xáo ngẫu nhiên): lãi lỗ 5% xấu nhất -93 USD, trung vị +41 USD, 5% tốt nhất +204 USD.
- Lưu ý: lợi nhuận tính trên ký quỹ; đã thử 24 cấu hình của 4 loại chỉ báo.

### M2. Chỉ pool tự nhiên (lọc dàn ví, loại ví giữ từ 50%) lúc 90 phút
- Cơ chế: Loại bỏ pool do dàn ví hoặc một ví kiểm soát; phần còn lại có người mua thật.
- Điều kiện loại bỏ (viết trước): Loại nếu sau 100 lệnh paper kỳ vọng vẫn không dương, hoặc tới cuối 11/2026 khoảng tin cậy còn chứa 0.
- Kết luận: **Chưa chứng minh** (93 lệnh, cần 100; khoảng tin cậy chứa 0; không dương ở cả hai nửa; âm nếu bỏ 4 lệnh thắng lớn nhất).
- Cỡ lệnh 5 USD, khoảng 4831 lệnh mỗi năm, dữ liệu 7 ngày, đã thử 4 biến thể. Trung vị -11.1%, lệnh tệ nhất -101.1%, profit factor 1.26, bỏ 4 lệnh thắng lớn nhất còn -11.7%, 20% lệnh gần nhất -14.4%.
- Mô phỏng 1 năm (4831 lệnh, xáo ngẫu nhiên): lãi lỗ 5% xấu nhất +540 USD, trung vị +1123 USD, 5% tốt nhất +1729 USD.
- Lưu ý: đây là cấu hình bot paper đang chạy.

### M4. Mua sau cú giảm từ 35% so với đỉnh 30 phút (pool tự nhiên)
- Cơ chế: Giá giảm quá đà sẽ hồi lại.
- Điều kiện loại bỏ (viết trước): Loại nếu cả khoảng tin cậy nằm dưới 0.
- Kết luận: **Loại** (cả khoảng tin cậy nằm dưới 0).
- Cỡ lệnh 5 USD, khoảng 9765 lệnh mỗi năm, dữ liệu 7 ngày, đã thử 9 biến thể. Trung vị -11.1%, lệnh tệ nhất -99.7%, profit factor 0.45, bỏ 4 lệnh thắng lớn nhất còn -12.2%, 20% lệnh gần nhất -7.7%.
- Mô phỏng 1 năm (5000 lệnh, xáo ngẫu nhiên): lãi lỗ 5% xấu nhất -2659 USD, trung vị -2459 USD, 5% tốt nhất -2258 USD.
- Lưu ý: đã thử 3 độ sâu x 3 kiểu chờ bật lại.

### M1. Mua mọi pool chuẩn pump.fun lúc 90 phút tuổi
- Cơ chế: Pool sống sót 90 phút được cho là đã qua giai đoạn xả hàng.
- Điều kiện loại bỏ (viết trước): Loại nếu cả khoảng tin cậy nằm dưới 0.
- Kết luận: **Loại** (cả khoảng tin cậy nằm dưới 0).
- Cỡ lệnh 5 USD, khoảng 14732 lệnh mỗi năm, dữ liệu 7 ngày, đã thử 1 biến thể. Trung vị -2.3%, lệnh tệ nhất -101.1%, profit factor 0.37, bỏ 4 lệnh thắng lớn nhất còn -19.8%, 20% lệnh gần nhất -19.0%.
- Mô phỏng 1 năm (5000 lệnh, xáo ngẫu nhiên): lãi lỗ 5% xấu nhất -3976 USD, trung vị -3599 USD, 5% tốt nhất -3197 USD.
- Lưu ý: mọi pool chuẩn, không lọc holder.

### M3. Mua nhanh: 5 phút sau khi lên sàn
- Cơ chế: Vào sớm hơn người khác ngay sau khi token tốt nghiệp.
- Điều kiện loại bỏ (viết trước): Loại nếu cả khoảng tin cậy nằm dưới 0.
- Kết luận: **Loại** (cả khoảng tin cậy nằm dưới 0).
- Cỡ lệnh 5 USD, khoảng 87078 lệnh mỗi năm, dữ liệu 7 ngày, đã thử 5 biến thể. Trung vị -21.2%, lệnh tệ nhất -101.1%, profit factor 0.46, bỏ 4 lệnh thắng lớn nhất còn -24.6%, 20% lệnh gần nhất -12.5%.
- Mô phỏng 1 năm (5000 lệnh, xáo ngẫu nhiên): lãi lỗ 5% xấu nhất -6138 USD, trung vị -5625 USD, 5% tốt nhất -5035 USD.
- Lưu ý: đã thử 2, 3, 5, 10, 20 phút.

