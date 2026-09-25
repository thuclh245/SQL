# Định dạng hồ sơ luyện tập

Mỗi buổi là một file `docs/interview-practice/NNNN-<yyyy-mm-dd>.md`.

```markdown
# Buổi NNNN — <yyyy-mm-dd> · <chủ đề> · <mức>

## Kết quả

| # | Mã câu | Chủ đề | Điểm | Lỗi chính |
|---|---|---|---|---|
| 1 | K3 | kien-truc | 3,5 | Không nói được vì sao model không tự chọn bảng |

Trung bình: Chính xác x · Đầy đủ x · Rõ ràng x · Trung thực x · **Tổng x/5**

## Điểm yếu cần luyện

1. <điểm yếu> — câu nói mẫu: "<…>"

## Câu trả lời chuẩn để ôn

Chép lại câu trả lời chuẩn bốn khối (Kết luận → Lý do → Bằng chứng → Giới hạn) của mỗi câu dưới 4 điểm. Khối nào người dùng thiếu thì gắn ❌ ở đầu khối đó.

### <mã câu> — <câu hỏi>
> **[Kết luận]** …
> ❌ **[Bằng chứng]** …

## Câu cần hỏi lại buổi sau

- <mã câu> (điểm < 3), diễn đạt khác đi

## Ghi chú

<sở thích của người dùng về cách luyện; lệch giữa tài liệu và code đã phát hiện>
```

Mã câu lấy theo ngân hàng câu hỏi (ví dụ V2, K3). Câu hỏi xoáy không ghi thành dòng riêng; lỗi lộ ra ở câu hỏi xoáy ghi vào cột "Lỗi chính" của câu gốc.
