# Hướng dẫn chạy và sử dụng Giao diện Web (Dashboard)

Hệ thống cung cấp một bảng điều khiển (Dashboard) trực quan giúp bạn dễ dàng kiểm tra, giả lập các kịch bản lỗi (chaos engineering) và theo dõi trạng thái hoạt động của lớp tin cậy (reliability layer) theo thời gian thực.

---

## 1. Yêu cầu hệ thống

Đảm bảo bạn đã cài đặt các dependencies và khởi chạy Redis:
```bash
# 1. Cài đặt các gói thư viện
pip install -e ".[dev]" fastapi uvicorn

# 2. Khởi chạy Redis thông qua Docker
docker compose up -d
```

---

## 2. Cách khởi động máy chủ Web

Khởi chạy máy chủ FastAPI bằng lệnh sau:
```bash
python -m uvicorn reliability_lab.app:app --host 127.0.0.1 --port 8000 --reload
```

Sau khi máy chủ khởi động thành công, hãy mở trình duyệt web và truy cập địa chỉ:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 3. Các kịch bản thử nghiệm khuyên dùng

Bạn có thể thay đổi các giá trị trên giao diện trực tiếp để kiểm tra khả năng phục hồi của hệ thống:

### Kịch bản A: Semantic Cache (Bộ nhớ đệm ngữ nghĩa)
1. Để **Primary Fail Rate = 0%** và **Bật Semantic Cache**.
2. Nhập một câu hỏi bất kỳ, ví dụ: `"Chính sách hoàn tiền của năm 2026 là gì?"` -> Nhấn **Gửi Yêu Cầu**.
   - *Kết quả*: Trả về từ Provider chính (Route: `primary`, Cache: `MISS`).
3. Gửi lại chính xác câu hỏi đó hoặc một câu hỏi tương tự như `"Tóm tắt chính sách hoàn tiền 2026"`.
   - *Kết quả*: Trả về ngay lập tức (Route: `cache_hit:0.95+`, Latency = 0ms, Cost = $0, Cache: `HIT`).

### Kịch bản B: Tự động Fallback khi lỗi
1. Kéo **Primary Fail Rate = 100%** (Provider chính bị sập hoàn toàn) và **Backup Fail Rate = 0%**.
2. Tắt Semantic Cache hoặc nhập một câu hỏi mới để tránh bị hit cache.
3. Gửi yêu cầu.
   - *Kết quả*: Gateway tự động chuyển yêu cầu tới Provider dự phòng (Route: `fallback`, Provider: `backup`).
   - Nếu bạn gửi liên tục 3 lần lỗi, hãy nhìn xuống bảng **Circuit Breakers**: `Primary Breaker` sẽ đổi sang trạng thái màu đỏ: **OPEN**.

### Kịch bản C: Ngắt mạch nhanh (Circuit Breaker OPEN)
1. Khi `Primary Breaker` đang ở trạng thái **OPEN**:
2. Gửi một yêu cầu mới.
   - *Kết quả*: Yêu cầu sẽ bỏ qua hoàn toàn việc gọi thử Provider chính mà chuyển thẳng sang Provider dự phòng để tối ưu hóa thời gian phản hồi (Fast fail-over).
3. Đợi khoảng **5 giây** (ngưỡng reset timeout đã cấu hình). Gửi thêm một yêu cầu nữa.
   - *Trạng thái sẽ chuyển sang **HALF_OPEN** để chạy thử. Nếu thành công, mạch sẽ quay lại trạng thái **CLOSED** màu xanh lá cây.*

### Kịch bản D: Degradation tĩnh (Static Fallback)
1. Kéo cả **Primary Fail Rate = 100%** và **Backup Fail Rate = 100%**.
2. Gửi yêu cầu.
   - *Kết quả*: Cả hai provider đều sập, hệ thống trả về thông báo lỗi tĩnh mặc định chống sập hệ thống (Route: `static_fallback`).
