# Script thuyết trình: T2S VTNet (13 slide, khoảng 14 phút)

Đi kèm `docs/13_NOI_DUNG_SLIDE_DU_AN.md`.

**Quy ước trong script**
- Người nói xưng "em", gọi người nghe là "anh chị"; đổi cách xưng hô cho hợp với hội đồng.
- *[nghiêng trong ngoặc vuông]* là gợi ý động tác: chỉ vào đâu, dừng ở đâu.
- **Chữ đậm** là chỗ cần nhấn giọng.

| Phần | Slide | Thời gian |
|---|---|---|
| Vấn đề | 1–4 | 3 phút |
| Giải pháp | 5–7 | 4 phút |
| Đánh giá | 8–10 | 4 phút |
| Demo, hướng phát triển, kết luận | 11–13 | 3 phút |

---

## Slide 1 — Tiêu đề (20 giây)

Em xin chào anh chị. Hôm nay em trình bày dự án **T2S VTNet**: một hệ thống cho phép hỏi dữ liệu mạng bằng tiếng Việt.

Nếu chỉ nhớ một câu từ bài hôm nay, em mong anh chị nhớ câu này: **hệ thống phải trả lời đúng, hoặc hỏi lại, hoặc từ chối. Không được đoán.**

---

## Slide 2 — Ai đang gặp vấn đề gì (50 giây)

Trước khi nói về giải pháp, em muốn làm rõ: vấn đề này là của ai.

Kho dữ liệu của mình rất lớn, nhưng kho lớn chỉ là bối cảnh. Nó chỉ thành vấn đề khi gây khó cho một người cụ thể. Ở đây có hai nhóm người, và họ gặp hai khó khăn khác nhau.

*[chỉ cột trái]* Nhóm thứ nhất là **DE và DA**. Họ biết cách viết SQL. Mỗi yêu cầu ad-hoc, họ phải tra xem bảng nào, nối bằng khóa gì, có quy ước ngầm gì. Một yêu cầu nhỏ mất khoảng năm đến mười phút. Đây là ước lượng của nhóm. Cái họ cần là một bản nháp đúng quy ước để **duyệt**, thay vì viết từ đầu.

*[chỉ cột phải]* Nhóm thứ hai là **người dùng nghiệp vụ**, và vấn đề của họ nặng hơn. Họ không biết dữ liệu nằm ở đâu, nên phải nhờ người khác rồi chờ. Nếu tự dùng một công cụ AI, họ nhận về một con số nhưng **không có cách nào biết con số đó đúng hay sai**.

---

## Slide 3 — Vì sao đưa LLM vào chưa đủ (50 giây)

Vậy sao không đưa luôn một mô hình ngôn ngữ vào để sinh SQL?

Hệ thống cũ đã làm đúng như vậy, và đây là kết quả. *[dừng, chỉ vào con số]* **93,2%** kết quả nó trả ra là sai, và nó **không báo lỗi**. SQL vẫn chạy, con số vẫn trông hợp lý, nhưng sai.

Em tìm ra bốn nguyên nhân gốc:
- **Thứ nhất**, không thể đưa hết schema cho model, nên model phải đoán bảng.
- **Thứ hai**, model không biết giá trị thật. Ví dụ khu vực lưu là `AREA_1`, còn model viết số `1`.
- **Thứ ba**, model không biết quy ước ngầm: KPI lưu dạng chuỗi phải ép kiểu, cell xấu phải loại ra, nối bảng danh mục sai thì số bị nhân lên.
- **Thứ tư**, model không biết khi nào nên dừng. Câu mơ hồ hay câu không có dữ liệu, nó vẫn viết ra một câu SQL.

Anh chị giữ giúp em bốn nguyên nhân này, vì phần giải pháp sẽ đi qua từng cái.

---

## Slide 4 — Bài toán (40 giây)

Từ đó, bài toán em đặt ra là: mỗi câu hỏi phải kết thúc bằng **một trong ba kết cục**:
- trả lời đúng;
- hỏi lại khi câu hỏi mơ hồ;
- từ chối, kèm lý do, khi không có dữ liệu.

Có ba ràng buộc đi kèm: hệ thống **chỉ được đọc**, dữ liệu **không được ra ngoài**, và phải chạy được trên **nhiều hệ quản trị** với cú pháp khác nhau.

Vì vậy thước đo thành công của em không phải "trả lời đúng bao nhiêu câu", mà là **tỷ lệ an toàn**: bao nhiêu phần trăm câu hỏi kết thúc đúng cách.

---

## Slide 5 — Kiến trúc tổng quan (1 phút 10 giây)

Đây là kiến trúc tổng quan của hệ thống.

*[chỉ theo mũi tên từ trái sang phải]* Người dùng đặt câu hỏi. Câu hỏi đi vào **cổng quyết định**. Cổng này lấy ngữ cảnh từ khối **tri thức dữ liệu**, rồi mới gọi **mô hình ngôn ngữ**. SQL do mô hình viết ra không chạy thẳng vào kho dữ liệu, mà phải đi qua khối **kiểm chứng an toàn**, nơi chỉ cho phép câu lệnh đọc. Kết quả quay về người dùng.

*[chỉ vòng dưới]* Người dùng bấm "Đúng" hoặc "Báo sai". Phản hồi đi vào **vòng học**, DE duyệt thì mới thành câu mẫu. *[chỉ khối bên cạnh]* Toàn bộ hệ thống được đo bằng **bộ đánh giá A–F**.

Điểm em muốn anh chị để ý: **mô hình ngôn ngữ chỉ là một khối**. Nó không được tự chọn dữ liệu, và câu nó viết không được chạy thẳng.

*[chỉ hai khối tô màu]* Bốn nguyên nhân ở slide trước được xử lý ở hai khối tô màu này. Em mở từng khối ra.

---

## Slide 6 — Tri thức dữ liệu (1 phút 20 giây)

Khối thứ nhất xử lý ba nguyên nhân đầu: đoán bảng, đoán giá trị, không biết quy ước.

*[chỉ sơ đồ]* Ý tưởng là: **trước khi hỏi model, hệ thống đọc dữ liệu thật**. Profiler quét từng bảng:
- Bảng nào, cột nào thật sự có dữ liệu. Trong 148 bảng thì chỉ 38 bảng có dữ liệu. Bảng KPI 5G có 395 cột, nhưng chỉ 10 cột có dữ liệu, nên model chỉ thấy 10 cột đó.
- Giá trị thật trong cột là gì.
- Phạm vi ngày, độ hạt của bảng.

Cùng với đó là glossary để biết khái niệm nghiệp vụ nằm ở bảng nào, và quy ước có bộ kiểm tra tự động. Model nhận một ngữ cảnh gọn và đúng, thay vì cả schema.

*[chỉ bảng trước/sau]* Đây là một câu hỏi thật trong bộ đánh giá: "Khu vực 1 gồm những tỉnh nào?"
- **Trước:** hệ thống lấy nhầm bảng KPI, đoán mã khu vực là số 1, rồi lấy mã tỉnh làm tên tỉnh.
- **Sau:** hệ thống lấy đúng bảng vị trí và đúng giá trị thật, 'Khu vuc 1', vì model đã **nhìn thấy** giá trị đó trong ngữ cảnh.

**Model không thông minh hơn. Model chỉ không phải đoán nữa.**

---

## Slide 7 — Cổng quyết định (1 phút 20 giây)

Khối thứ hai xử lý nguyên nhân thứ tư: **không biết khi nào nên dừng**.

*[chỉ sơ đồ]* Trước khi gọi model, cổng quyết định hỏi ba câu:
- Có dữ liệu cho câu này không?
- Thời gian hỏi có nằm trong phạm vi dữ liệu không?
- Câu hỏi có mơ hồ không?

Không có dữ liệu thì **từ chối, kèm lý do**. Mơ hồ thì **hỏi lại**, cho người dùng chọn, hoặc gõ cách hiểu của mình vào ô "Khác". Chỉ khi rõ ràng mới đi tiếp. Sau khi model viết SQL, nếu kiểm chứng phát hiện vi phạm quy ước và sửa một vòng vẫn không được, hệ thống cũng từ chối, chứ không trả ra một con số chưa đúng quy ước.

*[chỉ ví dụ 1]* Câu hỏi: "Thông lượng 5G toàn quốc tháng 12/2025?" Dữ liệu chỉ có từ tháng 8/2026.
- Hệ thống cũ vẫn trả ra một con số, lấy từ một bảng counter 3G. Con số trông hoàn toàn hợp lý. **Đây chính là sai im lặng.**
- Hệ thống mới trả lời: tháng 12/2025 nằm ngoài phạm vi dữ liệu, dữ liệu chỉ có từ 1/8 đến 20/8/2026.

*[chỉ ví dụ 2]* Câu hỏi: "Top 10 cell có lưu lượng cao nhất." Chữ "lưu lượng" có ba cách hiểu. Hệ thống cũ tự chọn một, còn hệ thống mới hỏi lại.

Sau khi có kết quả, người dùng vẫn thấy hệ thống đã giả định những gì, và sửa được nếu chưa đúng ý. Phần này em sẽ cho xem ở demo.

---

## Slide 8 — Cách đánh giá (1 phút 10 giây)

Để chứng minh hai khối này có tác dụng, em cần một cách đo phù hợp.

Cách phổ biến là EX: chạy SQL, so kết quả với một đáp án chuẩn, khớp thì đúng. Với bài toán này, EX có ba điểm yếu:
- Một câu hỏi có nhiều cách viết đúng: thêm một cột tên tỉnh, hay đổi mã thành tên, thì EX chấm sai dù nghĩa vẫn đúng.
- EX **không thưởng** cho việc hỏi lại hay từ chối đúng lúc, trong khi với người dùng nghiệp vụ đó là hành vi quan trọng nhất.
- EX không phân biệt được "sai" với "chưa đủ căn cứ để chấm".

Vì vậy em chấm theo **thang A–F**. *[chỉ bảng]*
- A là đúng, hoặc hỏi lại, từ chối đúng lúc.
- B là đúng nghĩa nhưng khác hình thức.
- C là câu mơ hồ được trả lời theo một cách hiểu hợp lý.
- D là sai.

A đến D đi từ tốt đến tệ. E và F thì nằm ngoài thứ tự đó: E là đúng may mắn, nguy hiểm vì trông như đúng; F là chỗ máy chấm không tự quyết được, cần người xem.

Chỉ số chính là **tỷ lệ an toàn, bằng A cộng B chia cho tổng số câu**. Câu F vẫn tính vào mẫu số, em không bỏ ra để số đẹp hơn.

---

## Slide 9 — Bộ đánh giá (50 giây)

Bộ đánh giá gồm **123 câu hỏi tiếng Việt** trên 6 domain: KPI 5G, băng rộng cố định, cảnh báo, giám sát dữ liệu, vị trí và KPI 4G.

*[chỉ bảng độ khó]*
- **Câu dễ** là lọc, đếm trên một bảng.
- **Câu trung bình** cần gom nhóm, ép kiểu, chọn đúng bảng.
- **Câu khó**, 54 câu, là loại DE hay gặp nhất: loại trừ cell xấu và cell biển đảo, tính trên cửa sổ nhiều ngày, tổng hợp nhiều cấp từ tỉnh lên khu vực lên toàn mạng, và nối nhiều domain mà không làm số bị nhân lên.

*[chỉ bảng kết cục]* Điểm quan trọng: bộ này **cố tình có 12 câu không có dữ liệu và 5 câu mơ hồ**. Với những câu đó, đáp án đúng là từ chối hoặc hỏi lại, vì người dùng thật sẽ hỏi như vậy.

---

## Slide 10 — Kết quả (1 phút 40 giây)

Đây là kết quả chính. Tất cả các hàng dùng **cùng một mô hình**, nên mọi chênh lệch đến từ hệ thống. Mỗi hàng thêm một khối so với hàng trên. *[chỉ icon đầu hàng]* Icon là khối tương ứng trên sơ đồ kiến trúc.

*[đi từ trên xuống, dừng ở từng bước nhảy]*
- Hệ thống cũ: tỷ lệ an toàn **4,9%**, sai im lặng 93%.
- Thêm **chọn bảng theo glossary**: lên 31,7%. Đây là bước nhảy lớn nhất.
- Thêm **profiler đọc dữ liệu thật**: lên 48,8%.
- Thêm quy ước và kiểm chứng: gần như không đổi về tỷ lệ an toàn. Giá trị của khối này là biến câu sai thành câu từ chối có lý do.
- Thêm **cổng quyết định**: lên **63,4%**. Hệ thống nhận ra đúng **17 trên 17** câu phải hỏi lại hoặc từ chối, và **không còn lỗi chạy nào**.

*[dừng một nhịp]* Từ 4,9% lên 63,4% với cùng một mô hình.

*[chỉ cột Dễ, TB, Khó]* Nhìn theo độ khó: câu dễ đúng 24/26, câu trung bình 33/43. **Câu khó mới đạt 21/54**. Đây là điểm yếu còn lại, em sẽ quay lại ở hướng phát triển.

*[chỉ ô tương tác]* Về tương tác: với 5 câu mơ hồ, hệ thống hỏi lại đúng cả 5. Sau khi người dùng chọn cách hiểu, hiện mới trả lời đúng 1 trên 4 câu; ba câu còn lại sai ở cách tính của model. Em nói thẳng con số này, vì phần tương tác mới được thử ở quy mô nhỏ.

---

## Slide 11 — Demo (1 phút 20 giây)

Sau đây là giao diện thật của hệ thống. *[lần lượt từng ảnh, mỗi ảnh khoảng 12 giây]*

1. Một câu hỏi rõ ràng: người dùng thấy bảng kết quả, câu SQL, và **các giả định hệ thống đã dùng**: dùng bảng nào, hiểu khái niệm nào ra sao.
2. Một câu mơ hồ, "lưu lượng tháng 8 theo tỉnh": hệ thống không đoán. Nó đưa ra thẻ chọn nguồn dữ liệu 4G hay 5G, kèm mô tả ngắn, và các cách hiểu để chọn. Không có cách nào đúng ý thì gõ vào ô "Khác".
3. Sau khi chọn, kết quả ghi rõ "cách hiểu bạn đã chọn".
4. Một câu ngoài phạm vi dữ liệu: hệ thống từ chối và nói rõ dữ liệu có từ ngày nào đến ngày nào.
5. Hỏi tiếp: câu sau mang theo ngữ cảnh của câu trước, người dùng không phải hỏi lại từ đầu.
6. Trang duyệt của DE: phản hồi của người dùng về đây. DE sửa SQL nếu cần, rồi duyệt thành câu mẫu. **Phản hồi chỉ thành tri thức khi có người duyệt.**

---

## Slide 12 — Hướng phát triển (1 phút)

Hướng phát triển của em tập trung vào **chất lượng**, nhắm thẳng vào hai điểm yếu vừa đo được.

- **Thứ nhất, câu khó.** Câu khó sai chủ yếu ở cách tính: cửa sổ ngày, tổng hợp nhiều cấp. Hướng làm là tìm những câu mẫu tương tự mà DE đã duyệt, rồi đưa vào ngữ cảnh. Một ví dụ đúng quy ước giúp model nhiều hơn một đoạn mô tả. Thước đo là tỷ lệ an toàn ở nhóm câu khó.
- **Thứ hai, 37% sai im lặng còn lại.** Hướng làm là kiểm chứng kết quả mạnh hơn: tự kiểm tra việc nối bảng có làm nhân số không, và đối chiếu các cấp tổng hợp với nhau, ví dụ tổng các tỉnh phải bằng toàn mạng.
- **Thứ ba**, đưa các khối thật vào: danh mục dữ liệu từ OpenMetadata, mô hình chạy nội bộ, kết nối các hệ quản trị thật, và bộ câu hỏi do người dùng thật viết. Như vậy kết quả được chứng minh trên dữ liệu thật, không chỉ trên dữ liệu mô phỏng.

---

## Slide 13 — Kết luận (30 giây)

Em xin tóm lại.

Vấn đề thật của bài toán không phải là "sinh được SQL". Model nào cũng sinh được. Vấn đề thật là **sai mà không báo**.

Với cùng một mô hình, hệ thống của em đưa tỷ lệ an toàn từ **4,9% lên 63,4%**, nhận ra **đủ 17 câu** phải hỏi lại hoặc từ chối, và **không còn lỗi chạy**.

Khác biệt đến từ hai điều: model **không phải đoán** vì có tri thức từ dữ liệu thật, và hệ thống **biết khi nào nên dừng**.

Em cảm ơn anh chị đã lắng nghe, và rất mong nhận được câu hỏi.

---

## Gợi ý khi trả lời câu hỏi

- Nghe hết câu hỏi, nhắc lại ý chính trong một câu, rồi mới trả lời.
- Câu trả lời mẫu cho các câu hay gặp nằm ở phần "Câu hỏi hội đồng có thể hỏi" và "Câu hỏi sâu" cuối `docs/13_NOI_DUNG_SLIDE_DU_AN.md`.
- Với câu chưa làm, trả lời theo mẫu: *"Phần này hiện chưa có. Em đã xác định cách làm là … và sẽ đo bằng …"*. Cách trả lời này tốt hơn là cố trả lời cho có.

## Ba con số cần thuộc lòng

| Con số | Nghĩa |
|---|---|
| **93,2%** | Tỷ lệ sai im lặng của hệ thống cũ |
| **4,9% → 63,4%** | Tỷ lệ an toàn, cùng một mô hình |
| **17/17** | Số câu hỏi lại / từ chối đúng |
