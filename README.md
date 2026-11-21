# OCR LLM Digitization

## Chạy ứng dụng local

Backend dùng FastAPI để nhận file và chạy PaddleOCR-VL. OCR chấp nhận PDF và các ảnh JPG, JPEG, PNG, BMP, TIFF, WEBP; mỗi lần chỉ chạy một tài liệu để tránh nhiều tác vụ tranh GPU. Kết quả theo từng trang được ghi vào `data/raw/{document_name}/`.

### 1. Cài dependencies backend

Từ thư mục gốc repo trong Ubuntu/WSL:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. Khởi động API

```bash
uvicorn backend.api.app:app --host 0.0.0.0 --port 8000
```

API nhận upload tại `POST /api/ocr/jobs`, trả trạng thái job tại `GET /api/ocr/jobs/{job_id}` và phục vụ ảnh đính kèm trong Markdown tại `/api/ocr/documents/{document_name}/{asset_path}`. Trạng thái job lưu trong bộ nhớ; khi khởi động lại API, các job đang chạy và trạng thái cũ không được khôi phục. Các file OCR đã ghi trong `data/raw/` vẫn còn.

### 3. Khởi động frontend

Trong terminal khác:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev -- --host 0.0.0.0
```

Mở URL Vite được in ra trong terminal. Để dùng Vite proxy, để `VITE_API_BASE_URL` trống trong `.env`; proxy chuyển `/api` tới `http://127.0.0.1:8000`. Nếu gọi API trực tiếp, đặt biến này thành địa chỉ backend, ví dụ `http://localhost:8000`.

### Hiệu đính và duyệt cuối trên web

Sau khi OCR hoàn tất, chọn **Qwen3:8B** trong mục Hiệu đính OCR. Qwen được chọn mặc định và gọi Ollama cục bộ với model `qwen3:8b` tại `http://localhost:11434`, không cần API key.

Đặt các biến môi trường trong terminal/backend process trước khi khởi động API:

```bash
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="qwen3:8b"
export OLLAMA_EMBEDDING_MODEL="embeddinggemma"
# Kích thước vector của model embeddinggemma là 768; chỉ đổi khi model yêu cầu kích thước khác.
# export OLLAMA_EMBEDDING_DIMENSIONS="768"
# Ngưỡng tương đồng vector (mặc định 0.35).
# export OLLAMA_VECTOR_SCORE_THRESHOLD="0.35"
# Tùy chọn: mặc định không giới hạn; đặt số giây để bật giới hạn chờ Ollama.
# export OLLAMA_TIMEOUT_SECONDS="600"
export DIGITIZATION_USER_ID="local_user"
```

Bản web hiện chưa có đăng nhập, vì vậy `DIGITIZATION_USER_ID` mặc định là `local_user`.

### Tìm kiếm toàn thư viện bằng AI

Tìm kiếm từ khóa thông thường vẫn tra tên và nội dung tài liệu đã lưu. Nhập `@AI: câu hỏi` trong ô tìm kiếm Dashboard hoặc khung chat để Ollama trích xuất từ khóa, tạo embedding, tìm các đoạn liên quan và trả lời dựa trên tài liệu đã duyệt. Chọn một kết quả trong chat để mở tài liệu tại đúng trang. Kết quả được phân trang và có thể duyệt tiếp.

Cài model embedding một lần và giữ Ollama chạy khi dùng tìm kiếm AI:

```bash
ollama pull qwen3:8b
ollama pull embeddinggemma
```

Chỉ mục vector Qdrant local được lưu trong `storage/vector_index/`; SQLite và các tệp Markdown đã duyệt vẫn là dữ liệu chuẩn. Tài liệu được đưa vào chỉ mục sau khi lưu thành công. Khi API khởi động, hệ thống tự lập chỉ mục bù cho tài liệu cũ hoặc các lần trước bị lỗi. API trạng thái là `GET /api/library/index-status`; để thử lập chỉ mục lại các tài liệu còn pending/failed, gọi `POST /api/library/reindex`. Nếu thay model embedding hoặc kích thước vector, đặt `OLLAMA_EMBEDDING_MODEL` và `OLLAMA_EMBEDDING_DIMENSIONS` trước, rồi gọi `POST /api/library/reindex?rebuild=true`; thao tác này xóa và dựng lại toàn bộ chỉ mục từ tài liệu đã lưu. Theo dõi tiến độ qua `GET /api/library/index-status`. Chỉ chạy một tiến trình backend trên cùng thư mục dữ liệu Qdrant local tại một thời điểm.

Khi hiệu đính xong, cửa sổ duyệt cuối hiển thị OCR và LLM cạnh nhau, cuộn đồng bộ và highlight các sửa của model. Nút **Edit** cho phép sửa văn bản; thay đổi được đồng bộ sang đoạn tương ứng ở cột kia và ghi vào audit log. Cú pháp Markdown, bảng, tiêu đề, công thức, thứ tự khối và hình ảnh được giữ theo đầu ra OCR. **Save with OCR output** hoặc **Save with LLM output** lập tức lưu bản chọn vào `storage/digitization/` cùng bản gốc PDF và `edit_log.json`. **Cancel** đóng cửa sổ, giữ review ở trạng thái chờ để mở lại sau.
