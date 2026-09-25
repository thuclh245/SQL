# Ngân hàng câu hỏi

Mỗi câu có:
- **mã** và **mức**: D = dễ, V = vừa, P = phản biện;
- **ý bắt buộc**: những ý câu trả lời phải có, dùng cho tiêu chí Đầy đủ;
- **bẫy**: chỗ người trả lời hay nói sai hoặc nói quá;
- **xoáy**: câu hỏi xoáy gợi ý.

Số liệu không chép vào đây. Khi chấm, lấy số liệu từ nguồn sự thật trong SKILL.md, để ngân hàng không bị cũ khi số liệu thay đổi.

Được phép diễn đạt lại câu hỏi. Được tự đặt câu mới cùng chủ đề nếu đã hỏi hết.

---

## van-de — Vấn đề và bài toán

**V1 · D** — Dự án này giải quyết vấn đề gì, cho ai?
- Ý bắt buộc: hai nhóm người dùng (DE/DA, người dùng nghiệp vụ) và khó khăn của từng nhóm; vấn đề cốt lõi là sai im lặng.
- Bẫy: chỉ nói "giúp người dùng không cần viết SQL", không nói tại sao làm việc đó khó.

**V2 · V** — "Kho có nhiều bảng" là bối cảnh hay là vấn đề? Vì sao?
- Ý bắt buộc: bối cảnh chỉ thành vấn đề khi gây hậu quả cho một người cụ thể. Với DE/DA, nó tốn thời gian tra cứu; với người dùng nghiệp vụ, họ không biết dữ liệu ở đâu và không kiểm tra được kết quả.
- Xoáy: "Con số 5–10 phút mỗi yêu cầu, em lấy ở đâu?" Câu trả lời đúng: ước lượng của nhóm, chưa đo, cần lấy số liệu ticket.

**V3 · V** — Vì sao không chỉ đưa một LLM mạnh vào để sinh SQL?
- Ý bắt buộc: tỷ lệ sai im lặng của hệ thống cũ; bốn nguyên nhân gốc (đoán bảng, đoán giá trị, không biết quy ước, không biết khi nào dừng).
- Xoáy: "Model mạnh hơn thì có tự hết các lỗi này không?" Ý cần có: hệ thống cũ cũng hỏng với model khác; model không thể biết giá trị và quy ước nếu không ai đưa cho nó.

**V4 · P** — Sai im lặng nguy hiểm hơn lỗi chạy ở điểm nào?
- Ý bắt buộc: lỗi chạy thì người dùng thấy ngay; sai im lặng thì con số trông hợp lý và đi thẳng vào báo cáo.

**V5 · P** — Bảo mật và đa engine có phải là vấn đề của người dùng không?
- Ý bắt buộc: đó là **ràng buộc** của bài toán, không phải nỗi đau của một nhóm người dùng cụ thể.
- Bẫy: nói hệ thống đã chạy nội bộ, hoặc đã hỗ trợ ClickHouse/StarRocks. Thực tế: thí nghiệm gọi model qua API bên ngoài; chỉ mới đo trên DuckDB.

---

## kien-truc — Kiến trúc tổng quan

**K1 · D** — Trình bày kiến trúc tổng quan trong một phút.
- Ý bắt buộc: luồng người dùng → cổng quyết định (lấy tri thức) → model → kiểm chứng → kho dữ liệu → người dùng; vòng học có người duyệt; bộ đánh giá đo cả hệ thống.

**K2 · V** — Vì sao model không được tự chọn bảng hay tự chạy SQL?
- Ý bắt buộc: có hai lớp chặn, trước và sau model. Model chỉ viết SQL. Nhờ vậy thay model khác vẫn giữ được mức an toàn.

**K3 · V** — Khi SQL vi phạm quy ước, hệ thống làm gì? Sao không tự sửa SQL cho model?
- Ý bắt buộc: báo lỗi để model tự sửa một vòng; vẫn vi phạm thì từ chối. Hệ thống cũ tự viết lại SQL bằng luật và đã làm hỏng câu SQL đúng.

**K4 · P** — So với báo cáo kiến trúc MG tuần trước (FIND, RESOLVE, Evidence Sufficiency, CONSTRUCT), phần nào đã chạy, phần nào chưa?
- Ý bắt buộc:
  - Đã chạy và đo: FIND, Evidence Sufficiency (thành các cổng quyết định), Decide đủ 4 kết cục.
  - Một phần: phân quyền, tra giá trị, vòng tự bổ sung evidence.
  - Chưa làm: nối OpenMetadata vào runtime, n8n, RLS.
- Bẫy: nói đã có đầy đủ như thiết kế.

**K5 · P** — Vì sao không dùng semantic layer như Wren AI, hay agent nhiều bước?
- Ý bắt buộc: semantic layer cần công mô hình hóa lớn cho hàng nghìn bảng. Agent cần kiểm soát vòng lặp và quyền truy cập. Dự án chọn grounding có giới hạn cộng các cổng quyết định, và đo được đóng góp của từng khối.

---

## profiler — Tri thức từ dữ liệu thật

**R1 · D** — Profiler làm gì?
- Ý bắt buộc: lọc cột và bảng có dữ liệu; lấy giá trị thật; lấy phạm vi ngày; phát hiện độ hạt.

**R2 · V** — Làm sao biết cột nào có dữ liệu, giá trị nào đưa vào ngữ cảnh?
- Ý bắt buộc: đếm số giá trị khác nhau; bỏ cột hằng số và cột chứa giá trị giả `sample_…`; cột dạng chữ có tối đa 12 giá trị thì liệt kê hết.
- Xoáy: "Cột có hàng nghìn giá trị, như tên tỉnh, thì sao?" Câu trả lời đúng: hiện chưa làm; hướng làm là tra giá trị ngay lúc hỏi (bỏ dấu, khớp gần đúng).

**R3 · V** — Độ hạt được phát hiện thế nào? Cho ví dụ.
- Ý bắt buộc: gom nhóm theo khóa (và thời gian nếu có) rồi xem số dòng lớn nhất trong một nhóm. Ví dụ bảng danh mục có 3 dòng cho mỗi tỉnh (theo huyện): nối thẳng làm số bị nhân 3. Bảng sự kiện (có cột định danh duy nhất) thì không khử trùng.
- Bẫy: nói trùng "theo phòng ban".

**R4 · V** — Hệ thống lấy dữ liệu và độ hạt từ đâu? Có đọc script sinh dữ liệu không?
- Ý bắt buộc: không đọc script. Profiler chạy truy vấn chỉ đọc trên chính cơ sở dữ liệu. Schema lấy từ export OpenMetadata thật; các dòng dữ liệu là synthetic.
- Xoáy: "Với hơn 8 nghìn bảng thật thì chạy thế nào?" Câu trả lời đúng: chạy định kỳ, trên mẫu dữ liệu, hoặc dùng OpenMetadata Profiler. Phần này chưa làm.

**R5 · P** — Đưa giá trị thật vào ngữ cảnh có gây hại không?
- Ý bắt buộc: có. Ví dụ "cảnh báo" bị model hiểu thành `level_important = 'WARNING'`. Đã khắc phục bằng ghi chú nghĩa trong glossary.

**R6 · P** — Vì sao không dùng mô tả bảng do AI sinh?
- Ý bắt buộc: đã đo, mô tả AI không giúp; thay mô tả AI cho dữ liệu thật làm giảm Safe và tăng lỗi chạy.

---

## cong-quyet-dinh — Cổng hỏi lại / từ chối và tương tác

**G1 · D** — Khi nào hệ thống hỏi lại, khi nào từ chối?
- Ý bắt buộc: không có bảng phù hợp hoặc thời gian ngoài phạm vi thì từ chối; thuật ngữ mơ hồ hoặc nhiều nguồn thay thế nhau thì hỏi lại; thuật ngữ nhạy cảm thì chặn.

**G2 · V** — Hệ thống biết một câu hỏi là mơ hồ bằng cách nào?
- Ý bắt buộc: glossary khai báo thuật ngữ mơ hồ kèm các cách hiểu; khi người dùng đã nói rõ nghĩa thì không hỏi lại; khái niệm có nhiều bảng thay thế nhau (`choose_one`) thì hiện thẻ chọn bảng.
- Xoáy: "Thuật ngữ mơ hồ chưa có trong glossary thì sao?" Câu trả lời đúng: model có thể tự trả HỎI LẠI qua hợp đồng đầu ra, nhưng không bảo đảm. Đây là hạn chế.

**G3 · V** — Người dùng tương tác với hệ thống thế nào? Có số đo không?
- Ý bắt buộc: thẻ chọn bảng, ô "Khác", ghim `@bảng`, xem giả định rồi sửa cách hiểu, hỏi tiếp, Đúng/Báo sai. Số đo mới có ở 5 câu mơ hồ.
- Bẫy: lấy con số 14/21 làm bằng chứng tương tác có hiệu quả. Hệ thống chưa có tương tác cũng đạt 14/21.

**G4 · P** — Hỏi lại nhiều có làm phiền người dùng không?
- Ý bắt buộc: trên benchmark không có câu nào bị hỏi chọn bảng thừa; hỏi lại cách hiểu chỉ xảy ra với thuật ngữ trong danh sách mơ hồ.

**G5 · P** — Vì sao không dùng RAG hay BM25 để tìm bảng tự động?
- Ý bắt buộc: glossary đã đủ độ phủ. Thử BM25 làm lớp tự động thì hệ thống tìm ra bảng cho gần hết các câu lẽ ra phải từ chối, tức mất khả năng từ chối. Vì vậy BM25 chỉ dùng cho mô tả tự do của người dùng.

**G6 · V** — Phản hồi của người dùng được dùng thế nào? Có sợ hệ thống học sai không?
- Ý bắt buộc: phản hồi vào hàng chờ; chỉ DE mới duyệt thành câu mẫu; câu trùng bộ đánh giá bị chặn.

---

## benchmark — Bộ đánh giá

**B1 · D** — Benchmark của em gồm những gì?
- Ý bắt buộc: schema từ danh mục thật, cắt ra 148 bảng; dữ liệu synthetic có bẫy; 123 câu chia theo kết cục, độ khó và domain; quy ước.

**B2 · V** — Vì sao phải tự xây, không dùng Spider hay BIRD?
- Ý bắt buộc: các bộ đó không có nghiệp vụ viễn thông, không phải tiếng Việt, và không có câu phải từ chối hoặc hỏi lại.

**B3 · V** — "Câu khó" khó ở đâu? Cho một ví dụ.
- Ý bắt buộc: anti-join, cửa sổ nhiều ngày, tổng hợp nhiều cấp, nối nhiều domain, tránh nhân số. Ví dụ câu cell 5G xấu cần nhiều quy ước đúng cùng lúc.

**B4 · P** — Dữ liệu synthetic thì kết quả có ý nghĩa gì với kho thật?
- Ý bắt buộc: schema thật nhưng dữ liệu là mô phỏng; bẫy được cài có chủ đích để không đúng may mắn được. Là hạn chế: chưa chứng minh trên dữ liệu thật, đó là hướng phát triển.

**B5 · P** — Câu hỏi và glossary do cùng nhóm viết, như vậy có phải là "học thuộc đề" không?
- Ý bắt buộc: có rủi ro, nên kết quả đang lạc quan. Cách khắc phục: bộ held-out 30–50 câu do người khác viết. Toàn bộ case đang ở trạng thái draft.

**B6 · P** — Gold SQL có đáng tin không?
- Ý bắt buộc: không hoàn toàn. Đã tự gắn cờ các lỗi: gold vi phạm quy ước, gold lệch câu hỏi, gold có điều kiện ẩn, nối heuristic. Cần DE duyệt.

---

## danh-gia — Cách đo

**E1 · D** — Thang A–F là gì?
- Ý bắt buộc: nghĩa của từng nhãn. A–D xếp từ tốt đến tệ; E và F nằm ngoài thứ tự đó.
- Bẫy: nói "F là tệ nhất".

**E2 · V** — Vì sao không dùng EX làm chỉ số chính?
- Ý bắt buộc: EX chấm oan câu đúng nghĩa; không thưởng cho việc từ chối đúng; không tách "sai" với "chưa đủ căn cứ". Ví dụ ở bước thêm cổng quyết định, EX gần như không đổi nhưng Safe tăng rõ.

**E3 · V** — Sai im lặng được đo trên phương diện nào?
- Ý bắt buộc: đo trên kết quả người dùng nhận được, không đo trên câu SQL. Mẫu số là các câu đã trả lời. Tử số gồm kết quả sai, thiếu cột, và trả lời câu lẽ ra phải từ chối.
- Xoáy: "Con số đó cao hơn hay thấp hơn thực tế?" Ý cần có: F bị tính là sai nên có thể cao hơn; E (đúng may mắn) không bị phát hiện nên có thể thấp hơn.

**E4 · P** — Vì sao không bỏ câu F ra khỏi mẫu số?
- Ý bắt buộc: bỏ ra thì số đẹp hơn nhưng che mất phần chưa chắc chắn. Thang A–F quy định F phải nằm trong mẫu số của chỉ số chính.

**E5 · P** — Làm sao biết một câu đúng không phải là đúng may mắn?
- Ý bắt buộc: bẫy dữ liệu được cài để điều kiện sai thì ra số sai; các câu A/B trên gold bị tranh chấp được liệt kê là "nghi E". Kiểm thử đột biến dữ liệu chưa làm đầy đủ.

---

## ket-qua — Kết quả

**Q1 · D** — Kết quả chính là gì?
- Ý bắt buộc: Safe của hệ thống cũ và hệ thống mới, cùng một model; số câu hỏi lại/từ chối đúng; số lỗi chạy.

**Q2 · V** — Khối nào đóng góp nhiều nhất? Khối nào gần như không đóng góp?
- Ý bắt buộc: ba bước nhảy (chọn bảng, profiler, cổng quyết định). Quy ước và kiểm chứng gần như không tăng Safe; giá trị của chúng là biến câu sai thành từ chối có lý do.

**Q3 · P** — 63% có thấp không?
- Ý bắt buộc: chỉ số khắt khe (tính cả câu phải từ chối, F vẫn trong mẫu số); câu dễ và trung bình đã tốt; câu khó là điểm yếu.

**Q4 · P** — Chênh lệch vài điểm giữa các cấu hình có ý nghĩa không?
- Ý bắt buộc: chạy lại cùng cấu hình đã dao động ±5–6 điểm, nên chỉ ba bước nhảy lớn là có ý nghĩa. Cần chạy 3 lần mỗi cấu hình.

**Q5 · V** — Các câu sai, sai vì đâu?
- Ý bắt buộc: khoảng một nửa chưa chắc là lỗi hệ thống (F, gold bị nghi ngờ, nhãn chưa nhất quán). Lỗi thật tập trung ở hiểu nghĩa nghiệp vụ và tính toán nhiều bước ở câu khó.

**Q6 · V** — Chi phí token và thời gian thế nào?
- Ý bắt buộc: số token trung bình mỗi câu; cổng quyết định vừa tăng Safe vừa giảm token, vì một số câu dừng trước khi gọi model. Thời gian phụ thuộc API.

---

## han-che — Hạn chế và trung thực

**H1 · V** — Điểm yếu lớn nhất của hệ thống hiện tại là gì?
- Ý bắt buộc: câu khó; sai im lặng vẫn còn; số liệu lạc quan (glossary và câu hỏi do cùng nhóm viết, dữ liệu synthetic).

**H2 · P** — Nếu ngày mai triển khai cho người dùng thật, điều gì có thể hỏng đầu tiên?
- Ý bắt buộc: thuật ngữ chưa có trong glossary; cột nhiều giá trị chưa được tra; các cơ chế trên dữ liệu thật chưa được đo.

---

## trien-khai — Triển khai và hướng phát triển

**T1 · V** — Hướng phát triển tiếp theo là gì, và đo bằng gì?
- Ý bắt buộc: câu mẫu đã duyệt (nhắm vào câu khó); kiểm chứng kết quả mạnh hơn (nhắm vào sai im lặng); đưa khối thật vào (OpenMetadata, model nội bộ, engine thật, câu hỏi thật). Mỗi hướng kèm chỉ số đo.

**T2 · P** — Dữ liệu có ra ngoài không?
- Ý bắt buộc: thí nghiệm hiện gọi API bên ngoài, được phép vì dữ liệu là synthetic; production phải dùng model nội bộ (vLLM). SQL chỉ đọc, kiểm tra bằng AST; chặn thuật ngữ nhạy cảm.

**T3 · P** — Làm sao mở rộng lên 8.857 bảng?
- Ý bắt buộc: glossary và quy ước do DE/steward duy trì, đồng bộ sang OpenMetadata; profiler chạy định kỳ; chỉ bảng có dữ liệu mới vào danh sách ứng viên. Chưa đo ở quy mô này.

**T4 · P** — Hỗ trợ nhiều engine (ClickHouse, StarRocks, PostgreSQL) thế nào?
- Ý bắt buộc: phương ngữ được khai báo trong hợp đồng dữ liệu; parse theo đúng phương ngữ bằng sqlglot; mỗi engine có adapter riêng. Hiện mới đo trên DuckDB.
