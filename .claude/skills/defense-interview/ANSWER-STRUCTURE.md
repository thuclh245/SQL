# Khung câu trả lời chuẩn

Mọi câu trả lời chuẩn dựng theo bốn khối, **theo đúng thứ tự này**. Hội đồng nghe câu đầu tiên để biết người trả lời có hiểu câu hỏi không, nên kết luận luôn đứng đầu.

| Khối | Vai trò | Độ dài | Câu hỏi tự kiểm |
|---|---|---|---|
| **Kết luận** | Trả lời thẳng câu hỏi | 1 câu | Nếu chỉ nghe câu này, hội đồng có biết câu trả lời không? |
| **Lý do** | Vì sao, hoặc hoạt động thế nào | 1–2 câu | Có giải thích cơ chế, hay chỉ nhắc lại kết luận? |
| **Bằng chứng** | Số liệu, ví dụ thật, trích từ nguồn sự thật | 1–2 câu | Có con số hoặc ví dụ cụ thể không? Có đúng nguồn không? |
| **Giới hạn** | Phạm vi của bằng chứng; điều chưa đo hoặc chưa làm | 0–1 câu | Có để người nghe hiểu rộng hơn thực tế không? |

Khối **Giới hạn** bắt buộc ở mức `phan-bien`, và bắt buộc ở mọi câu mà bằng chứng là dữ liệu synthetic, một lượt chạy, mẫu nhỏ, hoặc tính năng chưa đo. Các trường hợp còn lại có thể bỏ.

## Ví dụ

**Câu hỏi (R3):** Độ hạt được phát hiện thế nào?

| # | Ý chuẩn |
|---|---|
| 1 | **Kết luận:** Profiler tự chạy truy vấn gom nhóm trên dữ liệu để xem một khóa có bao nhiêu dòng. |
| 2 | **Lý do:** Nếu một khóa có nhiều dòng thì nối hoặc đếm thẳng sẽ làm số bị nhân lên, nên profiler ghi cảnh báo vào ngữ cảnh cho model. Riêng bảng sự kiện (có cột định danh duy nhất) thì ghi "không khử trùng". |
| 3 | **Bằng chứng:** Bảng danh mục vị trí có 3 dòng cho mỗi tỉnh (theo huyện). Nối thẳng thì Hà Nội ra 264 dòng thay vì 88. |
| 4 | **Giới hạn:** Mới chạy trên dữ liệu synthetic. Với kho thật cần chạy định kỳ, hoặc lấy từ OpenMetadata Profiler. |

**Câu trả lời chuẩn khi nói:**
> **[Kết luận]** Profiler tự gom nhóm theo khóa để xem một khóa có bao nhiêu dòng.
> **[Lý do]** Khóa có nhiều dòng thì nối hoặc đếm thẳng sẽ làm số bị nhân lên, nên hệ thống ghi cảnh báo vào ngữ cảnh để model khử trùng trước; bảng sự kiện thì ghi là không khử trùng.
> **[Bằng chứng]** Ví dụ bảng danh mục có 3 dòng cho mỗi tỉnh: nối thẳng thì số dòng của Hà Nội thành 264 thay vì 88.
> **[Giới hạn]** Hiện mới chạy trên dữ liệu mô phỏng; trên kho thật sẽ chạy định kỳ.

## Khi đánh giá trong bảng đối chiếu

- ✅ **đủ**: người dùng nói đúng ý, không cần đúng từng chữ.
- ⚠️ **chưa chính xác**: có nhắc tới ý đó nhưng sai số liệu, sai thuật ngữ, mơ hồ, hoặc nói quá.
- ❌ **thiếu**: không nhắc tới.

Ý người dùng nói nhưng không có trong khung chuẩn thì ghi riêng dưới bảng, phân loại là **thừa** (đúng nhưng không cần), **lạc đề**, hoặc **sai** (phải sửa).

Khi nhận xét phần **logic trình bày**, xét:
- thứ tự các ý: kết luận có nằm đầu không, hay bị chôn ở cuối;
- mỗi ý có dẫn sang ý sau không;
- có câu nào lặp lại ý đã nói không.
