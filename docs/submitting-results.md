# Submitting results

1. Run scenarios against your gateway:

```bash
aab run --target http://your-gateway --backend http://your-backend --admin-key <key> --scenarios scenarios --label your-gateway --out reports/your-gateway.json
```

2. Validate and inspect outputs.
3. Submit via:
   - GitHub issue using `.github/ISSUE_TEMPLATE/gateway_results.md`, or
   - PR adding a file under `results/community/`.

Do not fabricate results. Include product/version and setup notes.
