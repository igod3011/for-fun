# Tổng kết dự án + prompt để dán vào Claude Code (cập nhật 17/11/2026)

Mở Claude Code tại thư mục gốc của dự án (thư mục chứa `memebot/` và `CLAUDE.md`), rồi dán nguyên khung dưới.
Claude Code tự đọc `CLAUDE.md`; prompt này bổ sung bối cảnh, trạng thái và việc tiếp theo.

```
Bạn tiếp quản dự án của tôi. Repo igod3011/for-fun, nhánh claude/mql5-market-product-5p7wht. Tôi dùng máy Windows (Command Prompt) và đôi khi MacBook
(Windows: python, set BIEN=...; Mac: python3, export BIEN=...). Trả lời tôi bằng tiếng Việt; code, comment, commit bằng tiếng Anh.

VIỆC ĐẦU TIÊN
1. Đọc CLAUDE.md (quy tắc bắt buộc), memebot/PROMPT_CLAUDE_CODE.md (file này: trạng thái đầy đủ),
   memebot/pelluca/README.md, memebot/RESULTS.md (mục 16/11/2026).
2. Chạy: python3 -m unittest discover -s memebot/tests -t .   (phải đạt hết, hiện 132 test)
3. Mở Notion "Pelluca: Quản lý dự án" (https://app.notion.com/p/41b5b058739681c687ced7b24c9279da), đọc bảng
   Tasks và Nhật ký để biết việc đang dở. Tóm tắt lại cho tôi: đã xong gì, đang chờ gì, việc tiếp theo.

DỰ ÁN GỒM HAI PHẦN
A. memebot (nghiên cứu + bot giao dịch PAPER memecoin Solana) - ĐÃ DỪNG 16/11/2026.
   10 ngày dữ liệu, 23.116 pool (2.943 pool tốt nghiệp pump.fun). Không quy tắc nào có kỳ vọng dương được chứng
   minh; sổ paper 66 lệnh -1,570 SOL; theo ví giỏi: FAIL. KHÔNG chạy tiền thật. Dữ liệu (cohort*.jsonl) nằm trên
   máy Windows cũ, không có trong git. Chỉ mở lại khi có giả thuyết mới, đăng ký qua memebot/research.
B. Pelluca (sản phẩm, đang làm): công cụ kiểm tra rủi ro token cho thị trường quốc tế, tiếng Anh, chỉ đọc.
   Tên miền pelluca.com (đã mua, 11 USD/năm). Ngân sách cố định <= 1.000.000 đ/tháng.
   - Bot Telegram công khai: memebot/pelluca/bot.py (env PELLUCA_BOT_TOKEN, bot mới từ @BotFather).
     /check <CA>: LP đã đốt chưa, pool cạn, mất bao nhiêu so với ~85 SOL lúc tốt nghiệp, quyền mint/freeze,
     top holder, ví tạo token còn giữ bao nhiêu, lịch sử ví tạo token (pool khác cùng ví đã cạn chưa), chi phí
     mua-bán ngay. /watch <CA>: báo khi SOL pool giảm 30% trong 10 phút hoặc < 5 SOL (ngưỡng tạm, chưa đo).
   - Dữ liệu cho sản phẩm thu phí: CHỈ chuỗi Solana (memebot/rpc.py: RPC công khai trước, Helius dự phòng) và
     DexScreener (điều khoản cho phép thương mại, ghi nguồn). KHÔNG RugCheck, KHÔNG GeckoTerminal không key.
   - Thanh toán: khách trả SOL vào một ví Phantom MỚI chỉ để nhận tiền. Code chỉ đọc giao dịch đến (pay.py, Tuần 4),
     không bao giờ có private key/seed. Rủi ro pháp lý Việt Nam (crypto không phải phương tiện thanh toán, Nghị
     định 284/2026) đã được tôi chấp nhận; hỏi luật sư khi doanh thu >= 500 USD/tháng.

TRẠNG THÁI KẾ HOẠCH 30 NGÀY (bắt đầu 17/11/2026)
- Tuần 1: XONG (điều khoản dữ liệu, cách thu tiền, tên miền, bỏ các việc gửi email).
- Tuần 2: code XONG (/check, /watch, lịch sử ví tạo token, drain_eval, hướng dẫn VPS). Còn chờ tôi:
  (1) tạo bot Pelluca và chạy thử trên Mac; (2) chạy drain_eval trên dữ liệu cohort (nằm ở máy Windows cũ) để
  chỉnh ngưỡng /watch và cập nhật KPI; (3) thuê VPS Vultr Singapore 5 USD, làm theo memebot/pelluca/deploy/VPS.md.
- Tuần 3: website tiếng Anh một trang trên pelluca.com (ô kiểm tra CA, báo cáo ngày, đăng ký cảnh báo); báo cáo
  thị trường hằng ngày tự động; Meme Studio bản nội dung (tên, câu chuyện, hình) + bộ lọc mạo danh; điều khoản dịch
  vụ tiếng Anh, tuyên bố không phải lời khuyên đầu tư, 18+.
- Tuần 4: ra mắt trên X, Reddit, nhóm Telegram, Product Hunt; thử giá Pro 9 USD/tháng, gói meme 5 USD/50 lượt;
  pay.py (hóa đơn số SOL riêng, hết hạn 30 phút, đọc ví nhận qua RPC công khai); tạo ví nhận tiền; báo cáo 30 ngày.
- KPI Cổng 1: >= 300 người dùng/tuần, >= 20% quay lại sau 30 ngày, >= 30 người trả phí, cảnh báo báo trước >= 60%
  ca mất trắng với <= 20% báo nhầm, chi phí <= 50% doanh thu tháng trước.

QUY TẮC (chi tiết trong CLAUDE.md)
- Không viết code giao dịch thật, ví, private key. Không bao giờ bảo tôi dán key/token vào chat: secret chỉ nằm
  trong biến môi trường (export trên Mac, file .env chmod 600 trên VPS).
- Code chạy thật chỉ dùng thư viện chuẩn Python. Thêm test cho mọi thay đổi, chạy toàn bộ test, chỉ commit khi đạt.
  Push lên nhánh claude/mql5-market-product-5p7wht; không tạo PR nếu tôi không yêu cầu.
- Số liệu phải trung thực: đánh giá chia theo thời gian, có khoảng tin cậy, so với mốc không có quy tắc.
- Sau MỖI việc xong hoặc cập nhật: cập nhật Notion trong cùng lượt (Tasks: Trạng thái + Hoàn thành ngày;
  Nhật ký: 1 dòng; KPI/Chi phí nếu có số mới). ID các bảng có trong CLAUDE.md.
- Hướng dẫn tôi từng lệnh một để copy vào Terminal, kèm cách kiểm tra đã chạy đúng.
```

## Tài liệu và đường dẫn
- Notion quản lý dự án: https://app.notion.com/p/41b5b058739681c687ced7b24c9279da (Tasks, Nhật ký, KPI, Chi phí,
  trang "Tuần 1", trang "Tổng kết dự án").
- Bản đề xuất kinh doanh (bản đầu, tên cũ MemeRadar): https://claude.ai/artifact/ANJtzM3WuEFWhFk3GpEBoC
- Quy tắc cho Claude Code: `CLAUDE.md`. Kiến trúc nghiên cứu: `memebot/PROJECT.md`; kết quả: `memebot/RESULTS.md`;
  nghiên cứu chiến lược: `memebot/research/SCOREBOARD.md`.
- Pelluca: `memebot/pelluca/README.md` (cách chạy Mac/Windows, lệnh bot, đo cảnh báo), `memebot/pelluca/deploy/VPS.md`.

## Chi phí đến nay
- Tên miền pelluca.com: 11 USD/năm (đã trả 17/11/2026).
- Dự kiến hằng tháng: VPS 5–8 USD, AI viết nội dung <= 8 USD, AI tạo ảnh <= 8 USD, dự phòng 5 USD. Dữ liệu: 0 USD.

## Thay đổi môi trường cloud của Claude (đã làm)
Môi trường "Igod" được mở thêm mạng tới: docs.dexscreener.com, www.coingecko.com, docs.coingecko.com,
apiguide.geckoterminal.com, www.helius.dev, rugcheck.xyz (đọc điều khoản) và rdap.verisign.com (kiểm tra tên miền).
