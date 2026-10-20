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

Nút **AI correction** và lựa chọn model hiện chỉ là giao diện; chúng chưa gọi Ollama.
