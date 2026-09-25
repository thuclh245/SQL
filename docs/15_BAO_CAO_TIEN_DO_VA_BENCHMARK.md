# Báo cáo benchmark VTNet Mini

## 1. Benchmark là gì

VTNet Mini là **bộ đề kiểm tra hệ thống hỏi dữ liệu bằng tiếng Việt** trên kho dữ liệu mạng viễn thông. Mỗi câu hỏi có:
- **kết cục mong đợi**: trả lời, từ chối, hoặc hỏi lại;
- **đáp án chuẩn** (gold SQL và kết quả đúng) nếu câu đó cần trả lời.

**Vì sao phải tự xây, không dùng Spider hay BIRD:** các bộ công khai có schema nhỏ, câu hỏi tiếng Anh, và câu nào cũng có đáp án. Chúng không kiểm tra được hai điều mà kho VTNet cần nhất:
1. **Hiểu đúng nghiệp vụ viễn thông:** quy ước ngầm, giá trị mã hóa, bẫy khi nối bảng.
2. **Biết lúc nào không nên trả lời:** câu mơ hồ, câu không có dữ liệu.

---

## 2. Benchmark gồm những gì

### 2.1. Dữ liệu

| Thành phần | Nội dung |
|---|---|
| **Schema** | Lấy từ danh mục OpenMetadata thật của VTNet (8.857 bảng). Chọn **148 bảng, 5.864 cột** thuộc 8 schema: npms, gnoc, pm_counter, data_monitoring, fbb, netbi, geolocation, aaa. Tên bảng và cột giữ gần production |
| **Dữ liệu** | 1.770 dòng synthetic trong DuckDB, seed cố định nên tái lập được. Thời gian: 01/08 → 20/08/2026 |
| **Nhiễu** | Chỉ 38 bảng có dữ liệu. 110 bảng chỉ có schema, cố ý giữ lại như kho thật |
| **Bẫy dữ liệu** | Dữ liệu được sinh sao cho **mỗi điều kiện quan trọng đều làm đổi kết quả**, ví dụ cell đúng 3 ngày, cell biển đảo, cell ở Lào, thông lượng bằng 0, tỉnh thiếu trong danh mục. Nhờ vậy, SQL bỏ sót một điều kiện sẽ ra số sai, không thể đúng may mắn |
| **Quy ước nghiệp vụ** | 19 quy ước: 11 đã chấp nhận, đều có bộ kiểm tra tự động trên SQL; 8 đề xuất chờ DE duyệt (7 trong số đó mới là mô tả chữ). Ví dụ: KPI lưu dạng chuỗi phải ép kiểu; `date_hour` là chuỗi `YYYY-MM-DD-HH`; "cell xấu" phải loại cell biển đảo |

### 2.2. Câu hỏi: 123 câu tiếng Việt

| Kết cục mong đợi | Số câu |
|---|---|
| Cần trả lời | 106 |
| Không có dữ liệu → phải **từ chối** | 12 |
| Mơ hồ → phải **hỏi lại** | 5 |

| Độ khó | Số câu | Khó ở đâu |
|---|---|---|
| Dễ | 26 | Lọc, đếm, tra cứu trên một bảng |
| Trung bình | 43 | Gom nhóm, ép kiểu KPI, chọn đúng bảng giữa các bảng gần giống |
| Khó | 54 | Loại trừ (anti-join), cửa sổ nhiều ngày, tổng hợp nhiều cấp, nối nhiều domain, tránh nhân số khi nối |

**Domain:** KPI 5G (41) · băng rộng cố định FBB (25) · cảnh báo GNOC (24) · giám sát dữ liệu (19) · danh mục vị trí (9) · KPI 4G (5).

---

## 3. Một số case cụ thể

### Case 1 — Dễ: tra cứu danh mục
> **"Khu vực 1 gồm những tỉnh nào? Cho tôi mã và tên tỉnh."**

```sql
SELECT DISTINCT province_code, province_name
FROM hive__netbi__f_location_new
WHERE area_code = 'AREA_1';
```

**Kiểm tra:**
- Chọn đúng bảng danh mục (không dùng bảng KPI).
- Dùng đúng giá trị thật `'AREA_1'`, không phải số `1`.

### Case 2 — Trung bình: hiểu nghĩa bộ đếm
> **"Với từng máy chủ SBR, tổng số phiên tính cước bắt đầu và kết thúc là bao nhiêu?"**

```sql
SELECT sbr_server, SUM(CAST(start AS BIGINT)), SUM(CAST(stop AS BIGINT))
FROM hive__aaa__accounting GROUP BY sbr_server;
```

**Kiểm tra:** hiểu `start`/`stop` là **bộ đếm cần cộng dồn**, không phải đếm số dòng; và phải ép kiểu vì cột lưu dạng chuỗi.

### Case 3 — Khó: KPI cell xấu
> **"Trong 7 ngày kết thúc 20/8/2026, có bao nhiêu cell 5G xấu (tốc độ tải xuống dưới 5 Mbps trong hơn 3 ngày), không tính cell biển đảo? Tổng hợp theo tỉnh, theo khu vực và toàn mạng."**

Một câu hỏi, **11 quy ước** phải đúng cùng lúc:

| Điều kiện | Nếu sai |
|---|---|
| Cửa sổ 7 ngày tính cả hai đầu (14/8 → 20/8) | Thiếu hoặc thừa một ngày |
| "Hơn 3 ngày" là `> 3`, không phải `>= 3` | Tính thêm cell đúng 3 ngày (bẫy nhóm B) |
| Chỉ tính cell có lưu lượng > 0 và thông lượng > 0 | Tính thêm cell không hoạt động |
| Chỉ tính cell ở Việt Nam | Tính thêm cell ở Lào |
| Loại cell biển đảo bằng `NOT EXISTS` | Tính thêm cell biển đảo |
| Ép kiểu KPI từ chuỗi sang số | So sánh chuỗi: `'10' < '5'` |
| Tổng hợp 3 cấp bằng `GROUPING SETS` | Thiếu cấp khu vực hoặc toàn mạng |
| Khử trùng danh mục trước khi nối lấy tên tỉnh | Số bị nhân lên |

Mỗi điều kiện trên đều có dữ liệu bẫy tương ứng, nên bỏ sót một điều kiện là kết quả sai.

### Case 4 — Phải từ chối
> **"Thông lượng 5G toàn quốc tháng 12/2025 là bao nhiêu?"**

- **Đúng:** từ chối, vì dữ liệu KPI 5G chỉ có từ 01/08 đến 20/08/2026.
- **Sai:** trả ra bất kỳ con số nào. Hệ thống cũ trả ra một con số lấy từ bảng counter 3G.

### Case 5 — Phải hỏi lại
> **"Top 10 cell 5G có lưu lượng cao nhất ngày 20/8/2026"**

- **Đúng:** hỏi lại. "Lưu lượng" có thể là tổng, tải xuống hoặc tải lên, và mỗi cách cho ra một top 10 khác nhau.
- Mỗi cách hiểu có đáp án riêng, nên sau khi người dùng chọn, câu trả lời vẫn chấm được.

---

## 4. Đo như thế nào, và tại sao

### 4.1. Vì sao không chỉ dùng EX

EX (Execution Accuracy) là cách chấm phổ biến: chạy SQL, so kết quả với **một** đáp án, khớp thì đúng. Với bài toán này, EX có ba vấn đề:

| Vấn đề của EX | Ví dụ |
|---|---|
| **Chấm oan câu đúng nghĩa** | Trả thêm cột tên tỉnh, dùng tên khu vực thay cho mã, hay xoay bảng thành một dòng nhiều cột thì EX chấm sai, dù người dùng nhận đúng thông tin |
| **Không thưởng cho việc dừng đúng lúc** | Ở case 4, từ chối là đáp án đúng, nhưng EX không có đáp án để so. Hệ thống bịa số và hệ thống từ chối bị chấm như nhau |
| **Không tách "sai" với "chưa đủ căn cứ"** | Khi gold có thể thừa cột, máy không tự quyết được ai đúng |

Điều quan trọng nhất với người dùng không phải "SQL có giống đáp án không", mà là **"đưa kết quả này cho người dùng thì có an toàn không"**.

### 4.2. Thang A–F

| Nhãn | Nghĩa | An toàn |
|---|---|---|
| **A** | Đúng; hoặc từ chối / hỏi lại đúng ở câu phải từ chối / hỏi lại | ✅ |
| **B** | Đúng nghĩa, khác hình thức: thêm cột (B1), đổi mã ↔ tên (B3), xoay bảng (B5) | ✅ |
| **C** | Câu mơ hồ, trả lời theo một cách hiểu hợp lý | ⚠️ |
| **D** | Sai số, lỗi chạy, bịa câu trả lời cho câu phải từ chối, hoặc từ chối câu trả lời được | ❌ |
| **E** | Đúng may mắn: SQL sai nhưng số trùng đáp án | ❌ |
| **F** | Chưa đủ căn cứ để chấm, cần người xem | ❓ |

A đến D xếp từ tốt đến tệ. E và F nằm ngoài thứ tự đó.

### 4.3. Chỉ số

| Chỉ số | Công thức | Ý nghĩa |
|---|---|---|
| **Safe** (chính) | (A + B) / tổng số câu | Tỷ lệ câu hỏi kết thúc an toàn. F **vẫn nằm trong mẫu số** |
| Sai im lặng | số kết quả sai / số kết quả đã trả ra | Trong các con số đưa cho người dùng, bao nhiêu phần trăm sai |
| Hỏi lại / từ chối đúng | trên 17 câu phải hỏi lại hoặc từ chối | Hệ thống có biết dừng không |

---

## 5. Kết quả

Model `gpt-oss-120b` cho mọi cấu hình. Mỗi hàng thêm một thành phần so với hàng trên, nên chênh lệch đến từ hệ thống, không phải từ model.

| Cấu hình | **Safe** | A | B | D | F | Sai im lặng ↓ | Hỏi lại / từ chối đúng (17) | Lỗi chạy ↓ |
|---|---|---|---|---|---|---|---|---|
| Hệ thống cũ | 4,9% | 2 | 4 | 115 | 2 | 93,2% | 0 | 35 |
| + Chọn bảng theo nghĩa nghiệp vụ | 31,7% | 31 | 8 | 73 | 10 | 64,3% | 0 | 11 |
| + Đọc dữ liệu thật (giá trị, phạm vi, grain) | 48,8% | 48 | 12 | 50 | 13 | 49,6% | 0 | 4 |
| + Quy ước và kiểm chứng SQL | 50,4% | 50 | 12 | 49 | 12 | 46,1% | 0 | 8 |
| **+ Cổng hỏi lại / từ chối** | **63,4%** | **70** | **8** | **34** | **11** | **37,1%** | **17** | **0** |

**Theo độ khó** (hệ thống đầy đủ, số câu đạt A hoặc B):

| Dễ | Trung bình | Khó |
|---|---|---|
| **24/26** | **33/43** | **21/54** |

**Đọc kết quả**
1. Hệ thống cũ gần như không bao giờ báo lỗi: **93,2%** kết quả trả ra là sai.
2. Ba bước tạo khác biệt:
   - chọn bảng: +26,8 điểm;
   - đọc dữ liệu thật: +14,6 điểm;
   - cổng hỏi lại / từ chối: +13,0 điểm, nhận đúng **17/17** câu.
3. Thang A–F thấy được điều EX không thấy. Ở bước cuối, EX gần như không đổi, nhưng Safe tăng 13 điểm, vì 17 câu phải từ chối chuyển từ "bịa số" sang "dừng đúng".
4. Câu dễ và trung bình đã tốt. **Câu khó (21/54) là điểm yếu còn lại**, chủ yếu sai ở cách tính: độ hạt, cửa sổ ngày, tổng hợp nhiều cấp.

**Lưu ý về độ tin cậy**
- Chạy lại cùng một cấu hình, kết quả dao động khoảng ±5–6 điểm. Vì vậy chỉ ba bước nhảy lớn ở trên được coi là có ý nghĩa.
- Toàn bộ case đang ở trạng thái draft, chưa được DE duyệt.
- Câu hỏi và glossary do cùng nhóm viết, nên kết quả còn lạc quan. Cần thêm bộ câu hỏi do người khác viết để kiểm chứng.
