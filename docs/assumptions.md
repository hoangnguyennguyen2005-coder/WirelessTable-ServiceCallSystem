# Mặc định triển khai và giới hạn
- Yêu cầu đã chốt giữ nguyên theo requirements-source.txt, không có logbook để đối chiếu.
- Nhắc một lần sau >300s; DONE ở WAITING_ACK bị từ chối. Ghi trạng thái lúc đóng.
- Poll 5s, double press window 600ms, serial115200 baud/8N1, TTL120s, tối đa5 lần gửi/backoff1,2,4,8,16s: đề xuất phần mềm, chưa là thông số firmware đo được.
- Simulation dùng data/simulation.sqlite3; hardware dùng data/hardware.sqlite3. Seed demo idempotent chỉ simulation. Hardware đăng ký bàn/staff qua cấu hình UI/API, không seed demo.
- Server chỉ hỗ trợ loopback, Host/Origin allowlist; LAN bị từ chối thay vì cung cấp bảo mật giả. Staff selector chỉ simulation; hardware prototype thiết bị nhân viên dùng adapter riêng và API token cấu hình, không selector công khai.
- Không phần trăm pin, không offline kết luận cho idle. Chỉ mV và last_seen nếu có.
- RF frame đề xuất cần xác nhận firmware; boot_id+call_token 32bit lưu bền tại node (firmware chịu trách nhiệm) không được tái sử dụng. Mất correlation sau mất nguồn cần quy trình đối soát, không tự sinh DONE mới.
- SQLite UTC epoch seconds; UI Asia/Ho_Chi_Minh. Demo clock offset chỉ simulation; không đổi timestamp đã lưu và không dùng cho hardware.
- Quản lý loopback được coi là người vận hành tin cậy; không có SaaS login. Trên hardware, staff prototype yêu cầu token riêng cấu hình environment; đây là prototype, chưa thiết bị thật.
