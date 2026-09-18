# A0 — Bộ hình kiến trúc cho báo cáo T2S (Index)

> Mục tiêu: mỗi file dưới đây = **1 slide kiến trúc**, có sẵn (a) thông điệp chính, (b) bullet dán thẳng vào slide, (c) mã Mermaid để vẽ, (d) ánh xạ sang mã nguồn thật trong repo, (e) câu hỏi phản biện + câu trả lời.

## 1. Danh mục hình

| # | File | Tên slide | Dạng hình | Ưu tiên | Trả lời câu hỏi nào của hội đồng |
|---|---|---|---|---|---|
| A1 | `A1_BOI_CANH_HE_THONG.md` | Bối cảnh hệ thống (C4-L1) | Mermaid flowchart | **Bắt buộc** | "Hệ thống này nằm ở đâu trong hạ tầng công ty?" |
| A2 | `A2_KIEN_TRUC_THANH_PHAN.md` | Kiến trúc thành phần + ánh xạ mã nguồn (C4-L2) | Mermaid flowchart + bảng | **Bắt buộc** | "Kiến trúc gồm những khối gì, khối nào đã code?" |
| A3 | `A3_LUONG_END_TO_END.md` | Vòng đời 1 câu hỏi | Mermaid sequence | **Bắt buộc** | "Một câu hỏi đi qua những chốt nào, ai chặn ai?" |
| A4 | `A4_GROUNDING_PHAN_TANG.md` | Phễu thu hẹp 9.000 bảng | Mermaid flowchart (funnel) | **Bắt buộc** | "Làm sao không nhồi 9.000 bảng vào prompt?" |
| A5 | `A5_VERIFICATION_DA_TANG.md` | Ngăn xếp kiểm chứng fail-closed | Mermaid flowchart | **Bắt buộc** | "Lấy gì chặn câu SQL sai-mà-trông-đúng?" |
| A6 | `A6_ORCHESTRATOR_NGAN_SACH.md` | Vòng lặp có ngân sách | Mermaid stateDiagram | Cao | "Khác gì agent loop tự sửa vô hạn?" |
| A7 | `A7_BAO_MAT_DEFENSE_IN_DEPTH.md` | Bảo mật 3 tầng & ranh giới tin cậy | Mermaid flowchart + sequence | **Bắt buộc** | "LLM có thể làm lộ dữ liệu lương không?" |
| A8 | `A8_DA_PHUONG_NGU.md` | Đa phương ngữ ClickHouse/StarRocks/PostgreSQL | Mermaid flowchart + bảng đối chiếu | Cao | "Một model lo được 3 engine kiểu gì?" |
| A9 | `A9_BA_TRANG_THAI_RISK_COVERAGE.md` | Hợp đồng 3 trạng thái & đường Risk–Coverage | Mermaid decision + biểu đồ đường (không phải Mermaid) | **Bắt buộc** | "Không đạt 100% thì đo thành công bằng gì?" |
| A10 | `A10_METADATA_PIPELINE_TRIEN_KHAI.md` | Nguồn metadata & topology triển khai | Mermaid flowchart | Trung bình | "Metadata ở đâu ra, chạy trên hạ tầng nào?" |
| A11 | `A11_MA_TRAN_TRUY_VET.md` | Ma trận truy vết Vấn đề → Chốt chặn → Mã nguồn | Bảng (không cần Mermaid) | **Bắt buộc** | "Mỗi vấn đề khảo sát được giải bằng đúng cái gì?" |

**Gợi ý thứ tự trình bày:** Phần 1–2 (bài toán & khảo sát, bạn đã có) → A1 → A2 → A4 → A5 → A6 → A8 → A7 → A3 (luồng tổng hợp, chốt lại) → A9 → A11. A10 để dành cho phần phụ lục hoặc khi bị hỏi sâu về vận hành.

## 2. Quy ước dùng chung trong toàn bộ hình

| Ký hiệu | Ý nghĩa |
|---|---|
| Khối chữ nhật | Thành phần xác định (deterministic), hành vi có thể kiểm thử lại |
| Khối bo tròn / stadium | Thành phần xác suất (LLM), **không được tin tuyệt đối** |
| Hình thoi | Điểm quyết định có chính sách rõ ràng |
| Đường nét đứt | Luồng phụ trợ (quan sát, kiểm toán, tuỳ chọn) |
| 🔒 | Chốt chặn bảo mật, fail-closed (lỗi ⇒ từ chối, không phải cho qua) |

**Nguyên tắc màu (nếu vẽ lại bằng tay/Figma):** chỉ dùng **2 màu**: một màu cho khối xác định (an toàn), một màu cho khối LLM (rủi ro). Thông điệp thị giác của toàn bộ báo cáo là: *phần màu "rủi ro" rất nhỏ và luôn bị bao quanh bởi phần màu "an toàn"*.

## 3. Quy ước số liệu

- Số đã có bằng chứng nội bộ: ghi kèm mã bằng chứng, ví dụ `(I2)`, `(I3)` — tham chiếu `docs/10_EVIDENCE_REGISTER.md`.
- Số **chưa chạy xong**: để nguyên placeholder `⟨TBD⟩` trong slide nháp, không được điền số ước lượng. Hội đồng bắt được 1 số bịa là mất uy tín toàn bộ phần khảo sát.
- Tham số cấu hình (ngân sách, timeout, giới hạn dòng): lấy **trực tiếp từ mã nguồn**, đã ghi sẵn trong A4/A5/A7 kèm đường dẫn file.

## 4. Cách render Mermaid

- Nhanh nhất: dán vào https://mermaid.live → Export SVG/PNG.
- Trong VS Code: extension "Markdown Preview Mermaid Support".
- **Xuất toàn bộ sơ đồ ra SVG nền trong suốt bằng một lệnh** (script có sẵn trong thư mục này):
  ```bash
  bash docs/kien_truc_slides/render_diagrams.sh
  # kết quả ở docs/kien_truc_slides/rendered/*.svg
  ```
  Script cũng đóng vai trò **kiểm tra cú pháp**: sơ đồ nào sai sẽ báo lỗi và thoát với mã khác 0.
  Toàn bộ 12 sơ đồ trong bộ này đã render thành công với mermaid-cli 11.17.0.
- Slide chiếu máy chiếu: xuất **SVG**, đừng dùng PNG 1x (chữ trong sơ đồ sẽ nhoè ở cuối phòng họp).
