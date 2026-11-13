# memebot: kết quả và lịch sử phát hiện

Mới nhất ở trên. Mọi con số là lợi nhuận thực rút được từ pool, sau phí. "TEST" = 40% pool mới nhất, không dùng để chọn.

## 13/11/2026: "mua sau cú giảm" và "tránh cú bật" đều không đạt
388 pool tự nhiên, lệnh 0,2 SOL, phí 1,2%, cách thoát của bot, khớp cắt lỗ kiểu `close`; hai nửa thời gian.
- Mốc so sánh (mua lúc 90 phút): n=76, +8,6% (CI 90% −10,6%..+31,9%), trung vị −10,3%; nửa đầu +18,4%, nửa sau +1,1%.
- Mua ngay khi giá giảm ≥25/35/50% so với đỉnh 30 phút (tuổi 30–120 phút): −9,3% / −9,7% / −10,8% (n=160/143/104),
  CI nằm hẳn dưới 0, âm ở cả hai nửa. Chờ bật +10% hoặc +20% rồi mới mua: −7%..−12%. Nới thoát (SL 25%) tệ hơn.
  Trên cả 1.476 pool chuẩn: −28%..−33%.
- Bỏ lệnh đã bật ≥30% từ đáy 15 phút: phần giữ lại −8,4% (n=49), phần bị bỏ +26,6% (n=25, chứa các lệnh thắng lớn);
  nửa sau hai nhóm như nhau. Không giữ.
- Sổ paper 11–13/11 (9 lệnh đóng, −0,46 SOL): hai lệnh −97%/−99% (0,39 SOL) đều có top 10 holder sụt xuống <15%
  giữa lúc ghi nhận và lúc mua (87,8%→13,6%; 39,4%→6,3%); lệnh thứ ba có dấu hiệu này lỗ −10%. n=3, chưa là quy tắc.
  Số holder tăng thì KHÔNG xấu (nhóm ≥1.000 holder lúc điền nến có kết quả tốt hơn; đây là thông tin sau lệnh).
- Để kiểm chứng: từ 13/11 bộ thu thập chụp holder lúc ~90 phút cho pool qua bộ lọc tĩnh (`helius_90`,
  `cohort.snaps.jsonl`). Đánh giá lại khi có ≥100 pool có `helius_90` đã điền nến.

## 11/11/2026 (tối): đào sâu toàn bộ dữ liệu, bộ lọc "pool tự nhiên"
Câu hỏi: có cách vào/thoát hay nhóm pool nào dương không? Dữ liệu: 1.396 pool tốt nghiệp theo k, cộng nến 15 phút
(tới 10 ngày) của 125 pool còn sống sau 3 giờ.

**Bốn nhóm pool, kết quả rất khác nhau** (lệnh kiểu bot tại +90 phút, phí 1,2%):

| Nhóm (nhận diện lúc ghi nhận) | Số pool | Giữ từ lúc ghi nhận | Lệnh kiểu bot | CI 90% | Lệnh tốt nhất |
|---|---|---|---|---|---|
| Dàn ví (≥1.000 holder hoặc top 10 <15%) | 700 | −88,6% | −33,9% (n=58) | −44,0..−23,3 | +103% |
| Một ví giữ ≥50% nguồn cung | 304 | −59,4% | −14,8% (n=98) | −20,8..−9,4 | +16% |
| **Pool tự nhiên (còn lại)** | 392 | −52,7% | **+9,0% (n=72)** | −10,2..+33,5 | +748% |

- Nhóm "một ví giữ ≥50%" gồm hai loại: (a) pool **giả mạo** không do pump.fun migrate (dự trữ ảo on-chain = 0, người tạo
  giữ LP): một họ 127 pool chạy theo kịch bản, giá tăng tuyến tính 30 phút, không có lệnh bán nào, rồi rút sạch thanh
  khoản (126/127 về 0 SOL); (b) token do cá voi khống chế, giá gần như đứng yên, không có cửa lãi.
- **Quy tắc mới của bot:** bỏ pool không do migrate (`virt_sol == 0`) và pool có một ví giữ ≥50% (`max_top1`).
  Loại "không tự nhiên" so với giữ lại: −22% (n=156) so với +9% (n=72), cùng chiều ở hai nửa, CI chênh lệch +11..+56.
- **Đính chính mục A1 buổi sáng:** quy tắc cũ "top 10 >50%" thực ra đang loại đúng nhóm cá voi/giả mạo. Phép so sánh
  lúc đó sai vì nhóm "giữ lại" còn lẫn dàn ví. Quy tắc đúng là kết hợp: bỏ dàn ví **và** bỏ ví khống chế.

**Walk-forward với bộ lọc mới** (361 pool qua bộ lọc tĩnh): cấu hình hiện tại train +19,0%, **TEST −1,3%** (n=34, thắng
21%, CI 90% −21,9%..+29,8%). Chuỗi cải thiện trên TEST: −28,3% (mọi pool) → −17,2% (bỏ dàn ví) → −1,3% (pool tự nhiên).
Đây là hòa vốn với độ bất định rất lớn, chưa phải lợi thế: trung vị mỗi lệnh −10%, lãi dồn vào vài lệnh rất lớn.

**Những hướng đã thử và không có lãi:**
- 432 cấu hình cắt lỗ rộng/chốt lời/giữ lâu trên pool tự nhiên: 0% dương ở cả train lẫn test.
- Mua ở mọi tuổi 10–170 phút rồi giữ đến 3 giờ: âm ở mọi tuổi, cả pool sạch lẫn dàn ví.
- 12 đặc trưng lúc quyết định (đà giá, khối lượng, mức SOL, sụt giảm từ đỉnh...) chia ngũ phân vị: không nhóm nào
  dương ở cả hai nửa.
- Mua pool còn sống sau 3 giờ rồi giữ 1–48 giờ: pool tự nhiên −1,7% sau 3 giờ, −39,9% sau 24 giờ (60% mất hơn một nửa).
- Mô hình đa biến dự đoán lợi nhuận 30 phút tới cho nhóm 5% điểm cao nhất "+19%, thắng 90%": **ảo**. Toàn bộ là họ
  pool giả mạo ở trên; giá "treo" sau nến cuối không rút được vì thanh khoản đã bị rút.

**Kiến thức bên ngoài đã đối chiếu:** bảng phí PumpSwap theo vốn hóa (1,25% dưới 420 SOL, 1,20% đến 1.470 SOL, giảm
dần còn 0,30%) khớp số đo; nghiên cứu arXiv 2601.08641 ước tính ví "smart money" lãi khoảng 14% mỗi lệnh nhưng người
sao chép chỉ còn khoảng 3% sau ma sát; các thống kê CoinGecko/Dune cho thấy đa số ví pump.fun không có lãi đáng kể.

## 11/11/2026 (chiều): phí thật, dự trữ ảo theo pool, bộ lọc mới, mô hình chọn token
Dữ liệu: 11.122 pool ghi nhận, 1.360 pool tốt nghiệp thật có kết quả.

**Phí swap thật là 1,2%, không phải 0,5%.** `quote_check` so công thức với báo giá Jupiter qua đúng pool: 5 pool
đo sạch cho 1,17–1,25% mỗi chiều ở vốn hóa 250–1.000 SOL. Một vòng mua bán 0,2 SOL tốn khoảng 2,7% kể cả phí giao dịch.

**Dự trữ ảo khác nhau theo pool.** 60 pool đọc on-chain: đa số 17,54–17,58 SOL, nhưng có 15,3 / 13,7 / 11,2 / 2,9 và
0 (pool không do migrate). Với giá trị riêng của pool, tích `(SOL + ảo) × token` lúc ghi nhận là 1,760 × 10¹⁰ ± 0,4%.

**Cấu hình bot sau khi sửa** (+90 phút, SL 10%, trailing 10% sau +20%, giữ 60 phút, bỏ >+80%/1 giờ, lệnh 0,2 SOL):

| Tập pool | Train | TEST | Khoảng tin cậy 90% |
|---|---|---|---|
| Mọi pool tốt nghiệp thật | +3,6% | −28,3% (n=111, thắng 27%) | −37,6%..−17,4% |
| Qua bộ lọc tĩnh của bot (có lọc dàn ví) | +8,7% | **−17,2%** (n=69, thắng 23%) | −30,4%..−0,4% |

Không cấu hình nào trong 480 cấu hình dương trên TEST.

**Từng quy tắc** (`rc_rules`, lệnh kiểu bot, 1.360 pool):

| Quy tắc | Bị loại | Giữ lại | Chênh lệch nửa đầu / nửa sau | CI 90% | Kết luận |
|---|---|---|---|---|---|
| top 10 >50% (quy tắc cũ của bot) | −5% (124) | −20% (101) | −21% / −11% | −31..−1 | sai chiều: đã bỏ |
| ≥1.000 holder | −22% (68) | −8% (157) | +16% / +15% | +1..+29 | giữ |
| top 10 <15% | −36% (45) | −6% (180) | +20% / +35% | +16..+46 | giữ |
| một trong hai (bộ lọc dàn ví) | −26% (84) | −4% (141) | +17% / +24% | +8..+37 | đang dùng |

Trên 399 pool có RugCheck lúc ghi nhận: dev >3% và insider >10% kích hoạt 0 lần; cờ `High holder correlation` tách
tốt khi giữ từ lúc ghi nhận (−96% so với −54%, CI +27..+60) nhưng chưa đủ mẫu trên lệnh kiểu bot.

**Mô hình chọn token** (`select_model`, hồi quy logistic trên đặc trưng lúc ghi nhận, chia theo thời gian):
- Xếp hạng pool sống sót tốt: AUC 0,856 trên TEST (quy tắc dàn ví: 0,738). Đặc trưng mạnh nhất: mức giá và SOL
  trong pool lúc ghi nhận (dương), số holder (âm).
- **Không tạo ra lợi nhuận:** lệnh kiểu bot của nhóm điểm cao −23,1% (n=100); bộ lọc dàn ví −18,1% (n=66).
  Mua lúc ghi nhận rồi giữ 3 giờ ở nhóm 10% điểm cao nhất: −22,6% (CI −52,6%..+12,1%), chỉ 35% sống sót.
- **Trần của cách vào/thoát hiện tại:** ngay cả khi biết trước pool nào sống sót, lệnh kiểu bot trên các pool đó
  chỉ được +8,1% (n=46, thắng 43%). Chọn token hoàn hảo cũng không làm cấu hình này lãi nhiều.

**Ví giỏi** (`wallet_scores`, tiêu chí mới): FAIL, mới có 6 pool kiểm tra có ví được chọn (cần 20).

## 11/11/2026 (sáng): hai lỗi đo lường nền tảng
- **Backtest coi cắt lỗ khớp đúng mức stop.** Một cú xả trong một nến (−100%) được tính thành −10%. Đó là nguồn gốc
  con số "+3% trên TEST". Với `--stop-fill close`: −28%.
- **Công thức AMM bỏ sót dự trữ ảo.** Pool do pump.fun migrate định giá theo `(SOL thật + khoảng 17,58 SOL ảo) × token`.
  Xác nhận on-chain (u64 tại byte 245 của tài khoản pool) và trên 1.183 pool.
- **"Rug" là xả hàng, không phải rút thanh khoản.** LP đã bị đốt. 64% pool tốt nghiệp thật (840/1.308) kết thúc bằng
  một giao dịch bán gần hết nguồn cung: pool còn khoảng 0,45 SOL và 98% nguồn cung. Nhóm này có trung vị 2.004 holder
  chỉ 5 phút sau khi tạo pool; nhóm không bị xả có trung vị 335.
- **Bot paper:** 15 lệnh, −0,998 SOL trên vốn 1 SOL, thắng 20%; 4/9 lệnh 0,2 SOL bị xả, cắt lỗ khớp ở −88%..−100%.
  Sổ này lưu ở `archive/2026-11-11_143011/`.

## 06–09/11/2026: ba ngày đầu (khoảng 7.000 pool)
| Chỉ số | Giá trị |
|---|---|
| Pool chết (<30 phút có giao dịch trong 3 giờ đầu) | 66–68% |
| Pool đã cạn ngay lúc ghi nhận (<1 SOL) | 31% |
| Pool PumpSwap không phải pump.fun | trung bình −98%, 1% có lãi |
| Pool giả cho mint pump.fun thật | −99,5% |
| **Pool tốt nghiệp thật, mua lúc ghi nhận và giữ ≥3 giờ** | **trung bình −72%, 10% có lãi** |
| Cờ `rugged` của RugCheck | 0/10.357: vô dụng làm nhãn |

- Giữ lệnh đến 3 giờ không có quy tắc thoát: −40% đến −74% ở mọi cấu hình.
- Chặn dao rơi (≥40 SOL, SOL không giảm >20% từ lúc ghi nhận) cải thiện ở cả hai nửa dữ liệu.
- Bộ lọc lực mua (giá không thấp hơn 10 phút trước) không thêm giá trị.
- Lệnh 0,2 SOL tốt hơn 0,05 SOL vì phí giao dịch cố định chiếm tỷ lệ nhỏ hơn.
- Các con số "+1,8%" và "+3,1%" từng ghi ở đây là sản phẩm của hai lỗi đo lường nói trên.

## Nghiên cứu bên ngoài
- MELT (41.470 token pump.fun, 12/2024–3/2025): 84% rủi ro cao; trung vị lợi nhuận sau migration −68%. LightGBM chia
  theo thời gian đạt AUROC 0,90; lọc rug cải thiện trung vị nhưng trung bình vẫn âm.
- GMGN: API phải xin duyệt, phí 1% mỗi lệnh; chỉ dùng tham khảo thủ công.
- TradingAgents: khung LLM nhiều tác tử cho cổ phiếu theo ngày, quá chậm và tốn cho memecoin.

## Bài học về phương pháp
- Lọc theo thanh khoản lúc thu thập là nhìn trước tương lai (từng cho kết quả giả +250%).
- Danh sách "top pool" thiên lệch về token đã thắng.
- Nến đầu tiên của pool mở ở giá khởi tạo, không phải giá mua được.
- Một mô phỏng khớp lệnh lạc quan ở đúng trường hợp xấu nhất sẽ chọn nhầm cấu hình chặt nhất.
- Luôn đối chiếu công thức với báo giá thật trước khi tin số liệu.
- Lợi nhuận tính từ giá nến cuối là ảo nếu sau đó không còn giao dịch: phải thoát vào dự trữ thật (như
  `entry_timing.exit_bot` làm). Một kết quả quá đẹp trên một nhóm nhỏ thường là một cái bẫy được thiết kế cho bot.
