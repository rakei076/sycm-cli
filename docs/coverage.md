# sycm-cli Coverage Plan

This plan tracks what the CLI should cover as new API modules are added.

## Execution Policy

- API-first: prefer read-only API calls over Excel downloads for normal automation.
- No broad crawling: do not sweep all sitemap pages or all discovered endpoints in one run.
- One module at a time: add commands only when the endpoint shape and required parameters are understood.
- Low request volume: default to one day, page 1, small limits, sequential calls, and existing random delays.
- Stop on risk signals: keep the existing slider/captcha/frequency/login checks and never retry through them.
- Do not commit runtime data: JSON, Excel, HAR, bundle, and scout outputs stay local and ignored.

## Priority Model

| Priority | Module | Why it matters |
|---:|---|---|
| 1 | Service / customer support | Highest AI leverage: chat quality, response speed, missed replies, inquiry loss, after-sales signals, CS-driven sales. |
| 2 | Transaction / sales | Daily business baseline: order detail, product sales, refund movement, sales contribution. |
| 3 | Product | Item rank, product 360, new item tracking, diagnosis, and product-level conversion issues. |
| 4 | Traffic | Shop source, item source, keyword, recommendation, and visitor diagnostics. |
| 5 | Customer / membership | Customer overview, journey, fans, members, repeat purchase, and crowd reports. |
| 6 | Content / market / competition | Useful, but broader permissions and less predictable endpoint shapes. |

## Implemented And Candidate Presets

| Preset | Priority | Status | Endpoint | Notes |
|---|---:|---|---|---|
| `reception-list` | 1 | verified | `ww/consultation/detail/list` | Existing consultation reception detail. |
| `effective-reception-list` | 1 | live-ok-empty | `effective/Reception/detail/list` | Live smoke test returned success with a standard empty table; field display still needs non-empty data. |
| `filtered-reception-list` | 1 | live-ok-empty | `reception/filtering/detail/list` | Live smoke test returned success with a standard empty table; field display still needs non-empty data. |
| `long-reception-list` | 1 | live-ok-empty | `long/rcpt/detail/list` | Live smoke test returned success with a standard empty table; field display still needs non-empty data. |
| `evaluation-list` | 1 | verified | `evaluation/detail/list` | Existing after-sales evaluation detail. |
| `inquiry-loss-list` | 1 | verified | `inquiry/loss/list` | Existing inquiry loss detail. |
| `slow-rsps-list` | 1 | verified | `slow/rsps/detail/list` | Existing slow response detail. |
| `sale-cs-list` | 1 | verified | `ww/sale/detail/list` | Existing customer-service sales detail. |
| `sale-shop-list` | 2 | verified | `shop/sale/analysis/list` | Existing shop product sales analysis. |
| `sale-item-list` | 2 | verified | `item/sale/detail/list` | Existing order/item sales detail. |

## Next Service Candidates

These endpoints appear in the customer-service-performance bundle but need parameter verification before becoming presets.

| Area | Endpoint | Expected shape | Reason to wait |
|---|---|---|---|
| Service monitor | `core/monitor/list` | Date range plus `dateRange` style params | Uses `dateRange` values such as `1d`, `7d`, `30d`, not the same day table defaults. |
| Service monitor cards | `core/monitor/overview/list` | Card summary endpoint | Needs `cardUid`; not a generic list preset. |
| CS duty | `user/duty/analyse/list` | Date range, account filters | Frontend converts `startDate/endDate` into `startTime/endTime`. |
| Service sales | `serv/sale/analysis/list` | Sales table with optional item image lookup | Requires field validation and may reject month mode. |
| Refund detail | `refund/detail/list` | DateTime range, filters | Frontend converts day dates into full-day timestamps. |
| Refund complaint | `refund/complaint/detail/list` | Complaint filters plus query type | Needs context-derived `queryType`. |
| Refund retain | `refund/retain/detail/list` | Refund retention detail | Requires filter semantics validation. |
| Shop refund analysis | `shop/refund/analysis/list` | Refund analysis table | Needs date and filter parameter validation. |

## Sitemap Summary

The local scout output shows roughly 260 leaf pages across 20 top-level menu groups. The broad order should be:

1. Service: finish high-frequency detail and monitoring endpoints.
2. Transaction: order/sales/refund rollups and detail.
3. Product: item rank, item 360, new item tracking, diagnosis.
4. Traffic: shop source, item source, search keyword, recommendation.
5. Customer: overview, journey, fans, members, purchased customers.
6. Content/market/competition: add only after stable patterns are known.

## Release Rule

Review and sanitize implementation work before publishing it to the public `origin`.
