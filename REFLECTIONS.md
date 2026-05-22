# Reflections — Group 3

## 1. Multi-account: To run `costctl` against 100 AWS accounts, what changes?

Để mở rộng `costctl` cho 100 accounts, cần thay đổi:

- **Cross-account IAM roles**: Tạo 1 role chung (ví dụ `CostCtlReadOnly`) ở mỗi account target, trust policy cho phép account trung tâm assume. Mỗi lần chạy, dùng `sts.assume_role()` để lấy temporary credentials.
- **Profile loop**: Thêm flag `--profile` hoặc `--account-id` vào CLI. Viết wrapper script loop qua danh sách accounts từ AWS Organizations (`organizations.list_accounts()`), assume role vào từng account rồi chạy command.
- **Aggregated output**: Thêm cột `AccountId` / `AccountAlias` vào mỗi output row. Với `cost`, aggregate CSV per account để so sánh chi phí cross-account. Có thể export ra file `cost_report_<date>.csv` thay vì chỉ in terminal.
- **Concurrency**: 100 accounts chạy tuần tự sẽ rất chậm. Dùng `concurrent.futures.ThreadPoolExecutor` để chạy song song, nhưng cần rate limiting để tránh API throttling.
- **Error isolation**: Nếu 1 account bị lỗi (credential hết hạn, permission denied), không nên crash toàn bộ. Cần try/except per account và log lỗi riêng.

## 2. `idle` vs Trusted Advisor: When do you trust `idle` more, when do you trust TA more?

- **Khi nào tin tưởng `idle` hơn**: `idle` của chúng ta dùng cửa sổ 24 giờ. Nó phù hợp để phát hiện các resources "vứt xó" do quên tắt sau khi test xong hoặc các task ngắn hạn. Nó phản ứng nhanh, hữu ích cho môi trường Dev/Sandbox nơi resource thường xuyên bật/tắt trong ngày.
- **Khi nào tin tưởng Trusted Advisor hơn**: TA dùng cửa sổ 14 ngày. Nó an toàn hơn và chính xác hơn cho môi trường Production hoặc Staging. Một instance có thể không hoạt động nhiều vào cuối tuần hoặc ngày lễ (trong 24-72h) nhưng vẫn rất quan trọng vào giữa tuần. Dùng TA sẽ tránh được rủi ro "false positive" (xóa nhầm instance đang chờ việc) cao hơn so với việc chỉ nhìn vào 24h.

## 3. `clean --apply` blast radius: What would you have wanted in place to limit damage?

Nếu chạy nhầm `clean --tag Environment=dev --apply` trong account chung với team khác:

- **Resource protection**: Dùng EC2 termination protection (`DisableApiTermination=true`) cho các instance quan trọng. `costctl` sẽ fail gracefully thay vì xóa mất.
- **Tag ownership convention**: Quy ước tag `Owner=<team-name>` hoặc `Project=<project-name>`. Clean command nên yêu cầu ít nhất 2 tag filters (ví dụ `--tag Environment=dev --tag Owner=g3`) để giảm blast radius.
- **Account isolation**: Lý tưởng nhất là mỗi team có AWS account riêng (multi-account strategy). Dev resources của team A không bao giờ nằm chung account với team B.
- **Soft delete / grace period**: Thay vì terminate ngay, có thể stop instance trước + tag `scheduled-delete=<date+7d>`. Sau 7 ngày mới thực sự terminate — cho phép rollback nếu nhầm.
- **CloudTrail audit**: Đảm bảo CloudTrail enabled để trace ai đã chạy lệnh gì, lúc nào. Kết hợp SNS alert khi có bulk termination event.
- **IAM guardrails**: Dùng SCP (Service Control Policy) ở Organization level để prevent deletion của resources có tag `Protected=true`.

## 4. AI assistance: What fraction of code came from AI tools unmodified?

- **Khoảng 80-85% code** được generate bởi AI tools (Claude) và sử dụng gần như nguyên bản, vì project này có spec rất rõ ràng (module docstrings + test cases define behavior chính xác).
- **Phần AI làm tốt**: Boilerplate boto3 calls (describe_instances, paginator pattern), error handling (try/except ClientError), và output formatting. Các pattern này lặp lại giữa các commands nên AI generate rất chính xác.
- **Phần cần review kỹ**: Logic `_tag_s3` (merge tags thay vì replace) — đây là gotcha mà nếu không đọc kỹ docstring sẽ bị sai. Và `_find_targets` trong clean_cmd cần skip đúng state (terminated, shutting-down cho EC2; chỉ available cho volume).
- **Giá trị thực sự** của AI trong project này không phải là "viết code thay mình" mà là **tốc độ**: 7 commands implement trong ~30 phút thay vì 3-4 giờ. Tuy nhiên, hiểu logic đằng sau mỗi API call vẫn cần kiến thức AWS thực tế — AI chỉ là accelerator, không phải replacement.

## 5. W7 carry-over: Which commands will you keep going into W7? Which would you drop and why?

- **Sẽ giữ lại (Keep)**: 
  - `list` và `cost`: Đây là 2 tính năng core của FinOps. Việc list tài nguyên missing-tag là bước đầu tiên để governance, và cost tracking là mục đích chính.
  - `tag`: Auto-tagging là một phần không thể thiếu trong multi-account để dán nhãn owner, project.
- **Sẽ bỏ hoặc thay đổi mạnh (Drop/Modify)**: 
  - `clean` và `terminate`: Dùng script CLI để bulk terminate cực kỳ rủi ro ở scale lớn (blast radius lớn). Ở W7 (production-style), việc xóa tài nguyên nên được xử lý tự động hóa bằng AWS Config rules (auto-remediation) hoặc theo quy trình pipeline có approve thay vì chạy tay từ CLI cá nhân.
  - `idle`: Có thể chuyển sang dùng query trực tiếp từ Cost Explorer rightsizing recommendations thay vì tự pull CloudWatch data cho từng instance (sẽ rất chậm khi scale ra 100 accounts).
