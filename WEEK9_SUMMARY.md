# Week 9: Dashboard & Performance - Summary

## Day 1: Static Dashboard ✅

### Dashboard Features
- **Modern UI**: Gradient background, card-based layout, responsive design
- **Real-time Updates**: Auto-refresh every 60 seconds via API polling
- **Statistics Display**:
  - Total anomalies count
  - Monitored ticker (AAPL)
  - Last scan timestamp
- **Anomaly Cards**: Color-coded by severity (high=red, medium=orange)
- **Health Indicator**: Visual status indicator for API connectivity

### Infrastructure
- **S3 Bucket**: `stock-dashboard-529088281783`
- **CloudFront Distribution**: HTTPS delivery with global CDN
- **Dashboard URL**: https://dqdtse490mbv1.cloudfront.net
- **Deployment**: Automated via CDK BucketDeployment

### Files Created
- `/dashboard/index.html` - Single-page dashboard (HTML/CSS/JavaScript)
- `/cdk-app/cdk_app/dashboard_stack.py` - CDK stack for S3 + CloudFront

---

## Day 2: Performance Optimization ✅

### 1. Lambda Cold Start Optimization
**Changes to LambdaStack:**
- Increased memory: 256 MB → 512 MB (faster CPU allocation)
- Added concurrency limit: 5 concurrent executions (cost control)
- Imports already outside handler (best practice)

**Impact:**
- Faster execution with more CPU power
- Reduced cold start time with higher memory allocation

### 2. DynamoDB Query Optimization
**Changes to StorageStack:**
- Added `SeverityIndex` GSI for filtering by severity
- Configured `DateIndex` with ALL projection type
- Both indexes use timestamp as sort key for efficient range queries

**Benefits:**
- Query anomalies by severity without full table scan
- Efficient date-based queries via GSI
- Reduced read capacity consumption

### 3. API Gateway Caching
**Changes to ApiStack:**
- Enabled caching: 5-minute TTL
- Cache cluster size: 0.5 GB
- Increased API Lambda memory: 256 MB → 512 MB

**Performance Results:**
```
First request (uncached):  1.064s
Second request (cached):   0.354s
Improvement:               67% faster
```

---

## Architecture Improvements

### Before Week 9
- No dashboard (CLI/API only)
- Lambda: 256 MB memory
- No API caching
- Single DynamoDB GSI

### After Week 9
- Live dashboard with CloudFront CDN
- Lambda: 512 MB memory + concurrency limits
- API Gateway: 5-minute caching enabled
- DynamoDB: 2 GSIs (DateIndex + SeverityIndex)

---

## Performance Metrics

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| API Response (uncached) | ~1.0s | ~1.0s | - |
| API Response (cached) | N/A | 0.35s | 67% faster |
| Lambda Memory | 256 MB | 512 MB | 2x |
| DynamoDB Indexes | 1 | 2 | +1 GSI |
| Dashboard Delivery | N/A | CloudFront | Global CDN |

---

## Cost Considerations

### Added Costs
- **API Gateway Cache**: ~$0.02/hour for 0.5 GB cache = ~$14.40/month
- **CloudFront**: Free tier covers 1 TB/month, then $0.085/GB
- **Lambda Memory**: 512 MB vs 256 MB = 2x cost per invocation
- **DynamoDB GSI**: Additional write capacity for index maintenance

### Cost Optimization
- Concurrency limit (5) prevents runaway costs
- 5-minute cache TTL reduces Lambda invocations
- S3 lifecycle rules delete old data after 30 days
- On-demand DynamoDB pricing (pay per request)

---

## Testing Performed

1. ✅ Dashboard loads via CloudFront
2. ✅ Dashboard fetches anomalies from API
3. ✅ API caching reduces response time by 67%
4. ✅ All stacks deployed successfully
5. ✅ No errors in CloudWatch logs

---

## Next Steps (Week 10)

According to PROJECT_PLAN.md:
- **Day 1**: CI/CD Pipeline (GitHub Actions)
- **Day 2**: Documentation & Cleanup

---

## Files Modified

### Created
- `dashboard/index.html`
- `cdk-app/cdk_app/dashboard_stack.py`

### Modified
- `cdk-app/app.py` - Added DashboardStack
- `cdk-app/cdk_app/lambda_stack.py` - Memory + concurrency
- `cdk-app/cdk_app/storage_stack.py` - Added SeverityIndex GSI
- `cdk-app/cdk_app/api_stack.py` - Enabled caching

---

## Key Learnings

1. **API Gateway Caching**: Dramatically reduces Lambda invocations and improves response time
2. **Lambda Memory**: Higher memory = more CPU = faster execution (not just more RAM)
3. **DynamoDB GSIs**: Essential for efficient queries on non-key attributes
4. **CloudFront**: Required for S3 static hosting when Block Public Access is enabled
5. **Concurrency Limits**: Important safety mechanism to prevent cost overruns

---

## Week 9 Status: ✅ COMPLETE

Both days completed successfully:
- ✅ Day 1: Static dashboard deployed with CloudFront
- ✅ Day 2: Performance optimizations implemented and tested
