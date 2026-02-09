# Week 9: Dashboard & Performance - Notes

## Overview
Week 9 focused on creating a user-facing dashboard and optimizing system performance through caching, memory allocation, and database indexing.

---

## Day 1: Static Dashboard

### Objective
Create a minimal static dashboard to display stock anomalies in real-time.

### Implementation

#### 1. Dashboard HTML (`dashboard/index.html`)
- **Single-page application**: HTML + CSS + JavaScript (no frameworks)
- **Design**: Gradient background, card-based layout, responsive grid
- **Features**:
  - Statistics cards: Total anomalies, monitored ticker, last scan time
  - Anomaly list: Color-coded by severity (high=red, medium=orange)
  - Health indicator: Green dot for API connectivity
  - Auto-refresh: Polls API every 60 seconds
  - Error handling: Displays error message if API fails

#### 2. CDK Stack (`cdk_app/dashboard_stack.py`)
```python
# Key components:
- S3 Bucket (private, no public access)
- BucketDeployment (uploads dashboard files)
- CloudFront Distribution (HTTPS delivery)
- CfnOutput (CloudFront URL)
```

**Why CloudFront?**
- S3 Block Public Access prevents direct public bucket access
- CloudFront provides HTTPS and global CDN
- Origin Access Identity allows CloudFront to access private S3 bucket

#### 3. Deployment
```bash
cdk deploy DashboardStack
```

**Result**: https://dqdtse490mbv1.cloudfront.net

### Key Learnings
- CloudFront is required when S3 Block Public Access is enabled
- Static dashboards are cost-effective (no server-side rendering)
- JavaScript `fetch()` API works seamlessly with API Gateway CORS

---

## Day 2: Performance Optimization

### Objective
Optimize Lambda cold starts, DynamoDB queries, and API response times.

### 1. Lambda Optimization

#### Changes to `lambda_stack.py`:
```python
memory_size=512  # Increased from 256 MB
reserved_concurrent_executions=5  # Limit concurrency
```

**Why increase memory?**
- Lambda allocates CPU proportionally to memory
- 512 MB = 2x CPU power = faster execution
- Reduces cold start time

**Why limit concurrency?**
- Prevents cost overruns from runaway invocations
- 5 concurrent executions sufficient for hourly schedule
- Acts as safety mechanism

#### Best Practices Already Implemented:
- ✅ Imports outside handler (reduces cold start)
- ✅ Reuse AWS clients (boto3 connection pooling)
- ✅ Global variables for circuit breaker state

### 2. DynamoDB Optimization

#### Changes to `storage_stack.py`:
```python
# Added SeverityIndex GSI
partition_key="severity"
sort_key="timestamp"
projection_type=ProjectionType.ALL
```

**Why add SeverityIndex?**
- Query high-severity anomalies without full table scan
- Efficient filtering by severity level
- Reduces read capacity consumption

**Existing DateIndex:**
- Query anomalies by date range
- Sort by timestamp for chronological order

**GSI Best Practices:**
- Use `ProjectionType.ALL` to avoid additional reads
- Choose partition key with good cardinality (severity: high/medium/low)
- Sort key enables range queries

### 3. API Gateway Caching

#### Changes to `api_stack.py`:
```python
# API Gateway stage options
caching_enabled=True
cache_ttl=Duration.minutes(5)
cache_cluster_size="0.5"  # 0.5 GB

# API Lambda
memory_size=512  # Increased from 256 MB
```

**Cache Configuration:**
- **TTL**: 5 minutes (balance freshness vs performance)
- **Size**: 0.5 GB (smallest cache, sufficient for low traffic)
- **Scope**: All GET requests cached by default

**Performance Results:**
```
Uncached request: 1.064s
Cached request:   0.354s
Improvement:      67% faster (710ms saved)
```

**Cost Consideration:**
- Cache costs ~$0.02/hour = $14.40/month
- Reduces Lambda invocations by ~90% during cache hits
- Cost-effective for read-heavy APIs

---

## Architecture Changes

### Before Week 9
```
User → API Gateway → Lambda → DynamoDB
                              ↓
                              S3
```

### After Week 9
```
User → CloudFront → S3 (Dashboard)
       ↓
User → API Gateway (5-min cache) → Lambda (512 MB) → DynamoDB (2 GSIs)
                                                      ↓
                                                      S3
```

---

## Performance Metrics

| Component | Before | After | Impact |
|-----------|--------|-------|--------|
| API Response (cached) | N/A | 0.35s | 67% faster |
| Lambda Memory | 256 MB | 512 MB | 2x CPU |
| Lambda Concurrency | Unlimited | 5 | Cost control |
| DynamoDB GSIs | 1 (DateIndex) | 2 (+SeverityIndex) | Efficient queries |
| Dashboard | None | CloudFront + S3 | User interface |

---

## Cost Analysis

### New Monthly Costs
- **API Gateway Cache**: $14.40/month (0.5 GB @ $0.02/hour)
- **CloudFront**: Free tier (1 TB/month), then $0.085/GB
- **Lambda Memory**: 2x cost per invocation (512 MB vs 256 MB)
- **DynamoDB GSI**: Minimal (on-demand pricing, write replication)

### Cost Savings
- **Reduced Lambda invocations**: 90% reduction during cache hits
- **Efficient DynamoDB queries**: GSIs reduce read capacity
- **S3 lifecycle rules**: Auto-delete old data after 30 days

### Net Impact
- Slightly higher fixed costs (~$15/month for cache)
- Lower variable costs (fewer Lambda invocations)
- Better user experience (faster responses)

---

## Testing & Validation

### Dashboard Testing
```bash
# Test CloudFront delivery
curl -s https://dqdtse490mbv1.cloudfront.net | head -20

# Verify HTML loads correctly
✅ Dashboard HTML served via CloudFront
✅ JavaScript fetches from API Gateway
✅ Auto-refresh works (60-second interval)
```

### API Caching Testing
```bash
# First request (uncached)
time curl -s "https://1hdrnjh4kl.execute-api.us-east-1.amazonaws.com/prod/anomalies"
# Result: 1.064s

# Second request (cached)
time curl -s "https://1hdrnjh4kl.execute-api.us-east-1.amazonaws.com/prod/anomalies"
# Result: 0.354s (67% faster)
```

### Deployment Testing
```bash
# Deploy all optimized stacks
cdk deploy StorageStack --require-approval never  # GSI
cdk deploy ApiStack --require-approval never      # Caching
cdk deploy LambdaStack --require-approval never   # Memory
cdk deploy DashboardStack --require-approval never # Dashboard

✅ All stacks deployed successfully
✅ No rollbacks or errors
```

---

## Key Takeaways

### Technical Insights
1. **Lambda Memory = CPU**: Higher memory allocation provides proportionally more CPU power
2. **API Caching**: Dramatic performance improvement with minimal configuration
3. **DynamoDB GSIs**: Essential for efficient non-key queries
4. **CloudFront OAI**: Secure way to serve S3 content without public bucket access
5. **Concurrency Limits**: Important safety mechanism for cost control

### Best Practices Applied
- ✅ Imports outside Lambda handler
- ✅ Reuse AWS SDK clients
- ✅ Use GSIs for query patterns
- ✅ Enable API caching for read-heavy endpoints
- ✅ Set concurrency limits on scheduled Lambdas
- ✅ Use CloudFront for static content delivery

### Common Pitfalls Avoided
- ❌ Public S3 buckets (used CloudFront instead)
- ❌ Unlimited Lambda concurrency (set limit of 5)
- ❌ No caching (enabled 5-minute TTL)
- ❌ Insufficient memory (increased to 512 MB)
- ❌ Full table scans (added GSIs)

---

## Files Created/Modified

### Created
- `dashboard/index.html` - Static dashboard (HTML/CSS/JS)
- `cdk-app/cdk_app/dashboard_stack.py` - Dashboard infrastructure
- `WEEK9_SUMMARY.md` - Week 9 summary document

### Modified
- `cdk-app/app.py` - Added DashboardStack import and instantiation
- `cdk-app/cdk_app/lambda_stack.py` - Memory 512 MB, concurrency limit 5
- `cdk-app/cdk_app/storage_stack.py` - Added SeverityIndex GSI
- `cdk-app/cdk_app/api_stack.py` - Enabled caching, memory 512 MB

---

## Commands Reference

```bash
# Deploy dashboard
cd "project/Stock Tracker App/cdk-app"
cdk deploy DashboardStack --require-approval never

# Deploy optimizations
cdk deploy StorageStack --require-approval never
cdk deploy ApiStack --require-approval never
cdk deploy LambdaStack --require-approval never

# Test dashboard
curl -s https://dqdtse490mbv1.cloudfront.net

# Test API caching
time curl -s "https://1hdrnjh4kl.execute-api.us-east-1.amazonaws.com/prod/anomalies"
```

---

## Next Steps

**Week 10: CI/CD & Documentation** (Final Week)
- Day 1: GitHub Actions pipeline for automated CDK deployment
- Day 2: Complete project documentation and cleanup

---

## Week 9 Status: ✅ COMPLETE

- ✅ Day 1: Static dashboard with CloudFront CDN
- ✅ Day 2: Performance optimizations (caching, memory, GSIs)
- ✅ 67% API response time improvement
- ✅ All infrastructure deployed successfully
- ✅ Ready for Week 10 (CI/CD & Documentation)
