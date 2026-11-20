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

Sau khi OCR hoàn tất, chọn **Qwen3:8B** trong mục Hiệu đính OCR. Qwen được chọn mặc định và gọi Ollama local với model `qwen3:8b` tại `http://localhost:11434`, không cần API key. Gemini là lựa chọn tùy chọn khi muốn dùng API Google.

Đặt các biến môi trường trong terminal/backend process trước khi khởi động API:

```bash
export GEMINI_API_KEY="<Gemini API key>"
export GEMINI_MODEL="gemini-3.8-flash"
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="qwen3:8b"
# Tùy chọn: mặc định không giới hạn; đặt số giây để bật giới hạn chờ Ollama.
# export OLLAMA_TIMEOUT_SECONDS="600"
export DIGITIZATION_USER_ID="local_user"
```

`GEMINI_API_KEY` chỉ được đọc ở backend; không đặt key trong `frontend/.env` hoặc biến `VITE_*`. Nếu muốn điền trực tiếp trong code, mở file local `backend/llm/gemini_local_settings.py` (được Git bỏ qua) và gán key vào biến `GEMINI_API_KEY`. Biến môi trường `GEMINI_API_KEY` được ưu tiên hơn giá trị trong file local. Mức suy luận Gemini mặc định là `low` để giảm thời gian chờ; có thể đổi bằng `GEMINI_THINKING_LEVEL`. Bản web hiện chưa có đăng nhập, vì vậy `DIGITIZATION_USER_ID` mặc định là `local_user`.

Gemini client tự retry tối đa ba lần cho các lỗi HTTP tạm thời (`429`, `500`, `502`, `503`, `504`), có backoff và tôn trọng `Retry-After`.
Thời gian chờ mỗi phản hồi mặc định là 300 giây; có thể điều chỉnh bằng `GEMINI_TIMEOUT_SECONDS`.

Khi hiệu đính xong, cửa sổ duyệt cuối hiển thị OCR và LLM cạnh nhau, cuộn đồng bộ và highlight các sửa của model. Nút **Edit** cho phép sửa văn bản; thay đổi được đồng bộ sang đoạn tương ứng ở cột kia và ghi vào audit log. Cú pháp Markdown, bảng, tiêu đề, công thức, thứ tự khối và hình ảnh được giữ theo đầu ra OCR. **Save with OCR output** hoặc **Save with LLM output** lập tức lưu bản chọn vào `storage/digitization/` cùng bản gốc PDF và `edit_log.json`. **Cancel** đóng cửa sổ, giữ review ở trạng thái chờ để mở lại sau.
