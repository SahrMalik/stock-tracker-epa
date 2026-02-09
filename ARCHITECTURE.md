# Architecture Diagram - Stock Market Anomaly Monitor

## High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER LAYER                                      │
│                                                                              │
│  ┌──────────────┐                          ┌──────────────────────┐         │
│  │   Browser    │─────HTTPS────────────────▶│   CloudFront CDN    │         │
│  │              │                          │  (Dashboard Delivery) │         │
│  └──────────────┘                          └──────────┬───────────┘         │
│                                                       │                      │
│                                                       ▼                      │
│                                            ┌──────────────────┐             │
│                                            │   S3 Bucket      │             │
│                                            │  (Dashboard HTML)│             │
│                                            └──────────────────┘             │
│                                                                              │
│  ┌──────────────┐                          ┌──────────────────────┐         │
│  │   Browser    │─────HTTPS────────────────▶│   API Gateway       │         │
│  │   / cURL     │                          │  (REST API)          │         │
│  └──────────────┘                          │  - 5-min cache       │         │
│                                            │  - Throttling        │         │
│                                            └──────────┬───────────┘         │
└────────────────────────────────────────────────────────┼──────────────────────┘
                                                        │
                                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          APPLICATION LAYER                                   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │                    Lambda: api_handler                        │           │
│  │  - Runtime: Python 3.11                                       │           │
│  │  - Memory: 512 MB                                             │           │
│  │  - Timeout: 30s                                               │           │
│  │  - Handles: /health, /anomalies, /anomalies/{ticker}         │           │
│  └────────────────────────────────┬─────────────────────────────┘           │
│                                   │                                          │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────┐            │
│  │                    DynamoDB: stock-anomalies                 │            │
│  │  - Partition Key: ticker                                     │            │
│  │  - Sort Key: timestamp                                       │            │
│  │  - GSI: DateIndex (date + timestamp)                         │            │
│  │  - GSI: SeverityIndex (severity + timestamp)                 │            │
│  └─────────────────────────────────────────────────────────────┘            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │
┌──────────────────────────────────┼───────────────────────────────────────────┐
│                          SCHEDULED PROCESSING                                │
│                                  │                                           │
│  ┌───────────────────────────────┴──────────────────────────┐               │
│  │              EventBridge Rule                             │               │
│  │  - Schedule: cron(30 14-21 ? * MON-FRI *)                │               │
│  │  - Trigger: Hourly during market hours (9:30 AM - 4:30 PM ET)            │
│  └───────────────────────────┬──────────────────────────────┘               │
│                              │                                               │
│                              ▼                                               │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │                Lambda: stock_scanner                          │           │
│  │  - Runtime: Python 3.11                                       │           │
│  │  - Memory: 512 MB                                             │           │
│  │  - Timeout: 120s                                              │           │
│  │  - Concurrency: 5 (reserved)                                  │           │
│  │  - Retry: 2 attempts                                          │           │
│  │  - DLQ: SQS queue (14-day retention)                          │           │
│  └────┬─────────────────────────────────────┬──────────────┬────┘           │
│       │                                     │              │                 │
│       ▼                                     ▼              ▼                 │
│  ┌─────────────┐                  ┌──────────────┐  ┌──────────────┐       │
│  │ Parameter   │                  │  S3 Bucket   │  │  DynamoDB    │       │
│  │   Store     │                  │ (Raw Data)   │  │ (Anomalies)  │       │
│  │ - Ticker    │                  │ - 30-day     │  │              │       │
│  │ - Threshold │                  │   lifecycle  │  │              │       │
│  └─────────────┘                  └──────────────┘  └──────┬───────┘       │
│                                                             │                │
│                                                             ▼                │
│                                                    ┌──────────────┐          │
│                                                    │  SNS Topic   │          │
│                                                    │  (Alerts)    │          │
│                                                    └──────┬───────┘          │
│                                                           │                  │
│                                                           ▼                  │
│                                              ┌────────────────────────┐     │
│                                              │ Lambda: notification   │     │
│                                              │        _handler        │     │
│                                              │ - Slack webhook        │     │
│                                              └────────────────────────┘     │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          OBSERVABILITY LAYER                                 │
│                                                                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │  CloudWatch      │  │  CloudWatch      │  │  CloudWatch      │          │
│  │  Logs            │  │  Metrics         │  │  Alarms          │          │
│  │  - Lambda logs   │  │  - Invocations   │  │  - Error rate    │          │
│  │  - API logs      │  │  - Duration      │  │  - Throttling    │          │
│  │  - 1-week        │  │  - Errors        │  │  - DLQ messages  │          │
│  │    retention     │  │  - Throttles     │  │                  │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagrams

### 1. Scheduled Anomaly Detection Flow

```
EventBridge Timer (Hourly)
         │
         ▼
Lambda: stock_scanner
         │
         ├──▶ Parameter Store (Get ticker, threshold)
         │
         ├──▶ Generate Mock Data (30 days)
         │
         ├──▶ Calculate Z-scores
         │         │
         │         ├─ Price Z-score
         │         └─ Volume Z-score
         │
         ├──▶ Detect Anomalies (threshold > 2.0)
         │
         ├──▶ S3 (Store raw data)
         │
         ├──▶ DynamoDB (Store anomalies)
         │
         └──▶ SNS (Publish alerts)
                   │
                   ▼
         Lambda: notification_handler
                   │
                   ▼
         Slack Webhook (Alert notification)
```

### 2. API Request Flow

```
User Request (GET /anomalies)
         │
         ▼
API Gateway
         │
         ├─ Check Cache (5-min TTL)
         │      │
         │      ├─ Cache Hit ──▶ Return Cached Response (354ms)
         │      │
         │      └─ Cache Miss
         │             │
         │             ▼
         └──▶ Lambda: api_handler
                      │
                      ▼
              DynamoDB Query (DateIndex GSI)
                      │
                      ▼
              Format Response (JSON)
                      │
                      ▼
              Return to User (1.064s)
                      │
                      └──▶ Cache Response
```

### 3. Error Handling Flow

```
Lambda Invocation
         │
         ├─ Success ──▶ Return 200
         │
         └─ Failure
                │
                ├──▶ Retry #1 (1s delay)
                │         │
                │         ├─ Success ──▶ Return 200
                │         │
                │         └─ Failure
                │                │
                │                └──▶ Retry #2 (2s delay)
                │                         │
                │                         ├─ Success ──▶ Return 200
                │                         │
                │                         └─ Failure
                │                                │
                │                                └──▶ AWS Retry #1
                │                                         │
                │                                         └──▶ AWS Retry #2
                │                                                  │
                │                                                  └─ Failure
                │                                                         │
                │                                                         ▼
                └──────────────────────────────────────────▶ Dead Letter Queue (SQS)
                                                                         │
                                                                         ▼
                                                              Manual Investigation
```

## Security Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      SECURITY LAYERS                             │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Network Security                                       │     │
│  │  - HTTPS only (API Gateway, CloudFront)                │     │
│  │  - TLS 1.2+ for all AWS service calls                  │     │
│  │  - API throttling (100 req/s, 200 burst)               │     │
│  │  - S3 Block Public Access enabled                      │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Identity & Access Management                           │     │
│  │  - Least privilege IAM roles                            │     │
│  │  - Lambda execution roles (scoped permissions)          │     │
│  │  - CloudFront Origin Access Identity                    │     │
│  │  - No hardcoded credentials                             │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Data Protection                                        │     │
│  │  - Encryption at rest (DynamoDB, S3, Secrets Manager)  │     │
│  │  - Encryption in transit (HTTPS, TLS)                  │     │
│  │  - S3 versioning enabled                                │     │
│  │  - DynamoDB point-in-time recovery                      │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Secrets Management                                     │     │
│  │  - Parameter Store (configuration)                      │     │
│  │  - Secrets Manager (API keys)                           │     │
│  │  - Environment variables (Lambda config)                │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Monitoring & Auditing                                  │     │
│  │  - CloudWatch Logs (all invocations)                    │     │
│  │  - CloudTrail (API calls)                               │     │
│  │  - Structured logging (JSON format)                     │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Component Details

### Lambda Functions

| Function | Runtime | Memory | Timeout | Trigger | Purpose |
|----------|---------|--------|---------|---------|---------|
| stock_scanner | Python 3.11 | 512 MB | 120s | EventBridge | Anomaly detection |
| api_handler | Python 3.11 | 512 MB | 30s | API Gateway | API requests |
| notification_handler | Python 3.11 | 256 MB | 30s | SNS | Slack alerts |

### Storage

| Service | Configuration | Purpose |
|---------|--------------|---------|
| DynamoDB | On-demand, 2 GSIs, PITR | Anomaly records |
| S3 | Versioned, 30-day lifecycle, SSE-S3 | Raw scan data |
| Parameter Store | Standard tier | Configuration |

### Networking

| Service | Configuration | Purpose |
|---------|--------------|---------|
| API Gateway | REST, 5-min cache, throttling | API endpoints |
| CloudFront | HTTPS, OAI, global CDN | Dashboard delivery |

---

**Architecture Version**: 1.0  
**Last Updated**: 2026-02-09  
**Status**: Production
