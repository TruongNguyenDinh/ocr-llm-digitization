# Hướng Dẫn Context Cho AI Coding Agent (GEMINI.md)

Tài liệu này được tạo tự động bởi AI Coding Agent nhằm lưu trữ context chuẩn xác, đã được xác minh từ toàn bộ source code của dự án **OCR LLM Digitization**.

---

## 1. Mục Đích và Kiến Trúc Project

### 1.1 Mục đích dự án
Dự án xây dựng hệ thống số hóa văn bản tiếng Việt kết hợp hai công nghệ chính:
1. **Trích xuất nội dung văn bản & bố cục (OCR)**: Sử dụng **PaddleOCR-VL** (`paddleocr[doc-parser]`) nhận diện tài liệu đa trang (PDF hoặc các định dạng ảnh `.jpg`, `.png`, `.bmp`, `.tiff`, `.webp`).
2. **Hậu xử lý & số hóa thông minh (LLM)**: Sử dụng mô hình ngôn ngữ cục bộ thông qua **Ollama** (mặc định mô hình `qwen3:8b`) để:
   - Sửa lỗi chính tả, dấu tiếng Việt, khoảng trắng và ký tự nhận diện sai theo từng trang.
   - Phân loại tài liệu và trích xuất siêu dữ liệu (metadata: người gửi, người nhận, ngày tháng, loại văn bản) từ toàn bộ nội dung.
   - Tạo báo cáo so sánh (diff) trực quan phục vụ người dùng duyệt (human-in-the-loop).
   - Lưu trữ bản số hóa hoàn tất khi có sự phê duyệt tường minh từ người dùng.

### 1.2 Kiến trúc tổng thể và luồng dữ liệu

```
[Người dùng tải tài liệu (Ảnh / PDF)]
                 │
                 ▼
       ┌──────────────────┐
       │   Frontend UI    │ (React 19 + TypeScript + Vite)
       └─────────┬────────┘
                 │ HTTP (Multipart Upload / Polling / Proxy /api)
                 ▼
       ┌──────────────────┐
       │   FastAPI App    │ ([backend/api/app.py](file:///home/j4vis/projects/orc-llm-digitization/backend/api/app.py))
       └─────────┬────────┘
                 │ Submit Job vào ThreadPoolExecutor (max_workers=1)
                 ▼
  ┌─────────────────────────────┐
  │      PaddleOCR-VL Engine    │ ([backend/ocr_vl/pipeline.py](file:///home/j4vis/projects/orc-llm-digitization/backend/ocr_vl/pipeline.py))
  │  - Đếm trang trước          │
  │  - Xuất raw JSON, MD, TXT   │
  │  - Lưu assets hình ảnh      │
  └──────────────┬──────────────┘
                 │ Ghi dữ liệu vào `data/raw/{document_name}/`
                 ▼
  ┌─────────────────────────────┐
  │     Local LLM Workflow      │ ([backend/llm/workflow.py](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/workflow.py))
  │  1. Sửa lỗi OCR từng trang  │ (Gọi Ollama API: `qwen3:8b`)
  │  2. Trích xuất metadata     │ (5 nhóm tài liệu và một nhãn dự phòng từ `labels.json`)
  │  3. So sánh Diff văn bản    │ ([backend/llm/comparison.py](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/comparison.py))
  │  4. Xuất review.json draft  │ ([backend/llm/review_store.py](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/review_store.py))
  └──────────────┬──────────────┘
                 │ Chờ người dùng duyệt nội dung từng trang (Human Review)
                 ▼
  ┌─────────────────────────────┐
  │       Storage Service       │ ([backend/storage/service.py](file:///home/j4vis/projects/orc-llm-digitization/backend/storage/service.py))
  │  - Ghi Markdown số hóa      │ -> `storage/digitization/{label}/{user_id}_{seq}/`
  │  - Chuyển/Copy PDF gốc      │ -> `storage/origin/{label}/{user_id}_{seq}.pdf`
  │  - Ghi Metadata vào SQLite  │ -> `storage/metadata.sqlite3`
  └─────────────────────────────┘
```

> [!NOTE]
> Bên cạnh pipeline Ollama chính, thư mục [`backend/LoRA/`](file:///home/j4vis/projects/orc-llm-digitization/backend/LoRA/) chứa mã nguồn nghiên cứu, huấn luyện (fine-tuning) và đánh giá mô hình bằng thư viện Hugging Face Transformers/PEFT. Trọng số mô hình đã huấn luyện được lưu tại thư mục `models/`. Theo quy tắc dự án, không sửa đổi `backend/LoRA/` khi làm việc trên workflow ứng dụng Ollama.

---

## 2. Các Package và Module Chính

### 2.1 Backend Pipeline (`backend/`)

| Package / Module | Đường dẫn | Chức năng chính & Ký hiệu code quan trọng |
| :--- | :--- | :--- |
| **OCR-VL** | [`backend/ocr_vl/`](file:///home/j4vis/projects/orc-llm-digitization/backend/ocr_vl/) | • [`PaddleOCRVLEngine`](file:///home/j4vis/projects/orc-llm-digitization/backend/ocr_vl/engine.py#L5): Bọc thư viện `paddleocr.PaddleOCRVL`.<br>• [`process_document`](file:///home/j4vis/projects/orc-llm-digitization/backend/ocr_vl/pipeline.py#L147): Validate input, tính số trang, xuất `page_XXX.json`, `page_XXX.md`, `page_XXX.txt` và emit progress callback.<br>• [`correction.py`](file:///home/j4vis/projects/orc-llm-digitization/backend/ocr_vl/correction.py): Stub rỗng hiện tại. |
| **LLM Core** | [`backend/llm/`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/) | • [`OllamaClient`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/ollama_client.py#L12): Gọi Ollama HTTP API (`/api/tags`, `/api/chat`).<br>• [`LocalLLMWorkflow`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/workflow.py#L36): Điều phối luồng sửa lỗi từng trang và trích xuất metadata tổng thể.<br>• [`prompts.py`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/prompts.py): System prompts chống prompt injection cho OCR correction và classification.<br>• [`schemas.py`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/schemas.py): Các dataclass ([`PageText`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/schemas.py#L11), [`CorrectedPage`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/schemas.py#L17), [`DocumentMetadata`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/schemas.py#L24), [`ReviewDraft`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/schemas.py#L34)) và hàm parse structured JSON.<br>• [`comparison.py`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/comparison.py): So sánh dòng giữa OCR thô và gợi ý LLM bằng `difflib.SequenceMatcher`.<br>• [`review_store.py`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/review_store.py): Lưu/đọc atomically bản ghi `review.json` qua temporary file và `os.link` / `os.replace`.<br>• [`labels.json`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/labels.json): Danh mục 60 loại tài liệu (mã `0` đến `59`). |
| **Storage** | [`backend/storage/`](file:///home/j4vis/projects/orc-llm-digitization/backend/storage/) | • [`SQLiteRepository`](file:///home/j4vis/projects/orc-llm-digitization/backend/storage/repository.py#L8): Quản lý bảng `documents` trong SQLite với transaction `BEGIN IMMEDIATE` và tự tăng `sequence` theo từng `user_id`.<br>• [`finalize_review`](file:///home/j4vis/projects/orc-llm-digitization/backend/storage/service.py#L82): Lưu trữ tài liệu khi đã có đủ duyệt từ người dùng cho tất cả các trang; chuyển ảnh thành PDF hoặc sao chép PDF gốc; rollback tự động nếu thất bại.<br>• [`get_digitized_document`](file:///home/j4vis/projects/orc-llm-digitization/backend/storage/service.py#L213): Truy vấn thông tin tài liệu đã số hóa. |
| **API** | [`backend/api/`](file:///home/j4vis/projects/orc-llm-digitization/backend/api/) | • [`app.py`](file:///home/j4vis/projects/orc-llm-digitization/backend/api/app.py): Ứng dụng FastAPI (`POST /api/ocr/jobs`, `GET /api/ocr/jobs/{job_id}`, `GET /api/ocr/documents/...`, `GET /api/system/status`). Giới hạn 1 worker OCR tránh tranh chấp GPU.<br>• [`jobs.py`](file:///home/j4vis/projects/orc-llm-digitization/backend/api/jobs.py): [`OCRJobStore`](file:///home/j4vis/projects/orc-llm-digitization/backend/api/jobs.py#L26) lưu trạng thái job trong RAM có khóa luồng `RLock`.<br>• [`system_status.py`](file:///home/j4vis/projects/orc-llm-digitization/backend/api/system_status.py): Đọc tải CPU, RAM (psutil) và GPU (`nvidia-smi`). |
| **CLI & Workflows** | [`backend/`](file:///home/j4vis/projects/orc-llm-digitization/backend/) | • [`document_workflow.py`](file:///home/j4vis/projects/orc-llm-digitization/backend/document_workflow.py): [`prepare_document`](file:///home/j4vis/projects/orc-llm-digitization/backend/document_workflow.py#L11) kết nối toàn bộ quy trình từ OCR đến LLM Review draft.<br>• [`run_ocr.py`](file:///home/j4vis/projects/orc-llm-digitization/backend/run_ocr.py): CLI chạy riêng OCR.<br>• [`run_digitization.py`](file:///home/j4vis/projects/orc-llm-digitization/backend/run_digitization.py): CLI chuẩn bị review draft từ OCR + LLM. |
| **LoRA Training** | [`backend/LoRA/`](file:///home/j4vis/projects/orc-llm-digitization/backend/LoRA/) | • Khu vực độc lập phục vụ huấn luyện LoRA cho Qwen3-8B (`train.py`, `evaluate_correction.py`, `inference_test.py`, `analyze_errors.py`). |

### 2.2 Frontend Application (`frontend/`)

- **Công nghệ**: React 19, TypeScript, Vite, React-Markdown, Remark-GFM.
- **Trang chính**:
  - [`UploadPage.tsx`](file:///home/j4vis/projects/orc-llm-digitization/frontend/src/pages/UploadPage.tsx): Tải lên file, poll trạng thái job từ API backend, xem trước tài liệu bản gốc và bản Markdown OCR.
  - [`DashboardPage.tsx`](file:///home/j4vis/projects/orc-llm-digitization/frontend/src/pages/DashboardPage.tsx): Màn hình chính có thanh tìm kiếm và Chat Panel.
- **Dịch vụ API**:
  - [`ocrApi.ts`](file:///home/j4vis/projects/orc-llm-digitization/frontend/src/services/ocrApi.ts): Tạo job OCR (`createOcrJob`), lấy trạng thái (`getOcrJob`), lấy URL asset đính kèm (`getOcrAssetUrl`).
  - [`systemApi.ts`](file:///home/j4vis/projects/orc-llm-digitization/frontend/src/services/systemApi.ts): Lấy thông tin tài nguyên hệ thống (`getSystemStatus`).
- **Proxy**:
  - [`vite.config.ts`](file:///home/j4vis/projects/orc-llm-digitization/frontend/vite.config.ts) cấu hình proxy `/api` chuyển tiếp sang `http://127.0.0.1:8000`.

---

## 3. Lệnh Build, Test và Chạy

### 3.1 Môi trường yêu cầu
- **Hệ điều hành**: Linux / WSL (Ubuntu).
- **Python**: 3.10+ (môi trường ảo đã cấu hình tại `.venv`).
- **Node.js**: v20+ (hiện tại v24.22.0, npm 11.19.1).
- **Ollama**: Cài đặt cục bộ, đã tải mô hình `qwen3:8b`.
- **GPU**: NVIDIA GPU (tùy chọn nhưng khuyến nghị cho PaddleOCR và Ollama).

### 3.2 Cài đặt dependencies

```bash
# 1. Kích hoạt môi trường ảo Python và cài thư viện backend
source .venv/bin/activate
python -m pip install -r requirements.txt

# 2. Tải mô hình Ollama
ollama pull qwen3:8b

# 3. Cài đặt thư viện frontend
cd frontend
npm install
cd ..
```

### 3.3 Lệnh chạy ứng dụng

- **Khởi động Backend API (FastAPI + Uvicorn)**:
  ```bash
  source .venv/bin/activate
  uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --reload
  ```

- **Khởi động Frontend Dev Server (Vite)**:
  ```bash
  cd frontend
  npm run dev -- --host 0.0.0.0
  ```

- **Chạy OCR đơn lẻ bằng CLI**:
  ```bash
  source .venv/bin/activate
  python -m backend.run_ocr path/to/document.pdf
  ```

- **Chạy trọn gói OCR + LLM Review draft bằng CLI**:
  ```bash
  source .venv/bin/activate
  python -m backend.run_digitization path/to/document.pdf
  ```

### 3.4 Lệnh Build và Kiểm Tra Cú Pháp

- **Build Frontend**:
  ```bash
  cd frontend
  npm run build
  ```
  *(Thực thi `tsc -b && vite build`)*

- **Lint Frontend**:
  ```bash
  cd frontend
  npm run lint
  ```

- **Kiểm tra cú pháp Python (Backend syntax check)**:
  ```bash
  source .venv/bin/activate
  python -m py_compile backend/run_ocr.py backend/run_digitization.py backend/document_workflow.py backend/api/app.py
  ```

- **Kiểm thử tự động**:
  > [!WARNING]
  > Dự án hiện tại **chưa cấu hình test suite tự động** (thư mục `test/` đang trống; không có file `pytest` hay `unittest`). Kiểm thử hiện tại được thực hiện thủ công qua syntax check, smoke test CLI và kiểm tra giao diện.

---

## 4. Quy Ước Code và Các Lưu Ý Quan Trọng

### 4.1 Quy ước code chung
1. **Python**:
   - Thụt lề 4 khoảng trắng (spaces).
   - Đặt tên module, hàm, biến theo quy ước `snake_case`.
   - Sử dụng type annotations ở tất cả các interface boundary (`from __future__ import annotations`, kiểu dữ liệu rõ ràng).
   - Độc lập framework (framework-independent): Giữ cho các service nghiệp vụ (`backend/ocr_vl/`, `backend/llm/`, `backend/storage/`) hoàn toàn độc lập với web framework (FastAPI) để có thể tái sử dụng qua CLI hoặc các worker khác.
2. **Frontend**:
   - React functional components, hooks rõ ràng, strict type checking với TypeScript.
   - Luôn tắt HTML thô (`rehypeRaw` không được bật tùy tiện) trong Markdown viewer để đảm bảo an toàn bảo mật.

### 4.2 Lưu ý quan trọng về dữ liệu và an toàn
1. **Phân tách 3 trạng thái văn bản**:
   - `OCR text`: Văn bản thô được trích xuất từ PaddleOCR-VL.
   - `LLM suggested text`: Đề xuất sửa đổi từ Ollama (chỉ là gợi ý, **không bao giờ** được coi là văn bản đã duyệt).
   - `Approved text`: Văn bản do người dùng chỉnh sửa và xác nhận duyệt tường minh.
2. **Không tự ý finalize tài liệu**:
   - Chỉ được phép gọi `finalize_review` khi người dùng đã duyệt toàn bộ danh sách `page_id` của tài liệu.
3. **An toàn đường dẫn và tránh ghi đè (Atomic & Safe Paths)**:
   - Tên tài liệu và `user_id` phải được chuẩn hóa qua regex an toàn (ví dụ: `_safe_stem`, `_validate_component`), chống path traversal.
   - Thư mục output raw không được phép ghi đè thư mục cũ; nếu trùng lặp, backend phải tự sinh suffix `_2`, `_3`...
   - Lưu trữ `review.json` và xuất file số hóa phải qua file tạm thời (`tempfile`) và thao tác atomic `os.link` / `os.replace`.
4. **Quy tắc Git và bảo mật file**:
   - Tuyệt đối không commit: file tài liệu nguồn (`.pdf`, `.jpg`...), thư mục output OCR (`data/raw/`), thư mục lưu trữ số hóa (`storage/`), trọng số model (`models/`), thông tin nhạy cảm (`.env`), hoặc môi trường ảo (`.venv/`).

---

## 5. Những Điều Agent Cần Kiểm Tra Trước Khi Sửa Code

Trước khi can thiệp vào bất kỳ module nào, AI coding agent cần thực hiện tuần tự:

1. **Kiểm tra phân định phạm vi**:
   - Tuyệt đối không sửa code trong thư mục [`backend/LoRA/`](file:///home/j4vis/projects/orc-llm-digitization/backend/LoRA/) nếu nhiệm vụ liên quan đến workflow số hóa thông thường hoặc Ollama.
2. **Kiểm tra tính toàn vẹn của interface boundaries**:
   - [`process_document`](file:///home/j4vis/projects/orc-llm-digitization/backend/ocr_vl/pipeline.py#L147): Phải duy trì định dạng trả về gồm `document_name`, `page_count`, `pages` và progress callback contract.
   - [`LocalLLMWorkflow`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/workflow.py#L36): Phải đảm bảo trả về [`ReviewDraft`](file:///home/j4vis/projects/orc-llm-digitization/backend/llm/schemas.py#L34) với format JSON đúng schema.
   - [`finalize_review`](file:///home/j4vis/projects/orc-llm-digitization/backend/storage/service.py#L82): Phải yêu cầu đầy đủ các trang trong `approved_pages`.
3. **Kiểm tra dịch vụ phụ thuộc**:
   - Nếu chạm vào module LLM: Kiểm tra Ollama có đang phản hồi tại `http://localhost:11434` và mô hình `qwen3:8b` đã sẵn sàng chưa (`curl -s http://localhost:11434/api/tags`).
4. **Kiểm tra cú pháp & build sau khi sửa đổi**:
   - Backend: Chạy `.venv/bin/python -m py_compile <file_vừa_sửa>`.
   - Frontend: Chạy `npm run build` và `npm run lint` trong thư mục `frontend/`.
5. **Đảm bảo không phá hủy dữ liệu**:
   - Không xóa thư mục lưu trữ `data/raw/` hoặc `storage/`.
   - Đảm bảo tính rollback trong các hàm lưu trữ dữ liệu.

---

## 6. Phần Cần Xác Minh Thêm (Trạng Thái Tính Năng Đang Phát Triển)

Các điểm sau đã được xác minh từ mã nguồn là **chưa hoàn thiện hoặc đang ở dạng giao diện**:

1. **Tích hợp nút AI Correction trên Frontend**:
   - Nút **AI correction** và ô chọn model trong component [`CorrectionControls.tsx`](file:///home/j4vis/projects/orc-llm-digitization/frontend/src/components/CorrectionControls.tsx) hiện chỉ quản lý UI state nội bộ; chưa có hàm gọi API backend để kích hoạt LLM.
2. **Endpoint LLM Review và Finalize trên Web API**:
   - [`backend/api/app.py`](file:///home/j4vis/projects/orc-llm-digitization/backend/api/app.py) hiện chỉ có endpoint upload và lấy kết quả OCR (`/api/ocr/jobs`), chưa nối hàm [`prepare_document`](file:///home/j4vis/projects/orc-llm-digitization/backend/document_workflow.py#L11) hay [`finalize_review`](file:///home/j4vis/projects/orc-llm-digitization/backend/storage/service.py#L82) thành HTTP routes cho frontend gọi.
3. **Lưu trữ trạng thái Job**:
   - [`OCRJobStore`](file:///home/j4vis/projects/orc-llm-digitization/backend/api/jobs.py#L26) đang lưu job trong RAM; nếu backend restart thì thông tin job đang chạy hoặc đã chạy sẽ bị mất (dù file raw trong `data/raw/` vẫn được bảo toàn).
4. **Hệ thống kiểm thử tự động (Unit / Integration Tests)**:
   - Chưa có file test tự động nào trong thư mục `test/` hoặc toàn bộ dự án. Cần thảo luận với người dùng để bổ sung bộ test (pytest/vitest) khi bước vào giai đoạn kiểm thử.
