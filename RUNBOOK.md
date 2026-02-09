# Operational Runbook - Stock Market Anomaly Monitor

## Table of Contents
1. [Deployment Procedures](#deployment-procedures)
2. [Monitoring & Health Checks](#monitoring--health-checks)
3. [Troubleshooting Guide](#troubleshooting-guide)
4. [Incident Response](#incident-response)
5. [Backup & Recovery](#backup--recovery)
6. [Rollback Procedures](#rollback-procedures)

---

## Deployment Procedures

### Initial Deployment

**Prerequisites:**
- AWS CLI configured
- Python 3.11+
- Node.js 18+
- CDK CLI installed: `npm install -g aws-cdk`

**Steps:**

```bash
# 1. Bootstrap CDK (one-time per account/region)
cd cdk-app
cdk bootstrap aws://529088281783/us-east-1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Synthesize CloudFormation templates
cdk synth

# 4. Deploy all stacks
cdk deploy --all --require-approval never

# 5. Verify deployment
aws lambda invoke --function-name stock-scanner /tmp/output.json
curl https://1hdrnjh4kl.execute-api.us-east-1.amazonaws.com/prod/health
```

**Expected Duration:** 10-15 minutes

### Update Deployment

```bash
# 1. Pull latest code
git pull origin main

# 2. Review changes
cd cdk-app
cdk diff

# 3. Deploy specific stack
cdk deploy LambdaStack --require-approval never

# Or deploy all stacks
cdk deploy --all --require-approval never
```

### Configuration Updates

**Update ticker or threshold:**

```bash
# Update ticker
aws ssm put-parameter \
  --name /stock-tracker/ticker \
  --value "MSFT" \
  --overwrite

# Update threshold
aws ssm put-parameter \
  --name /stock-tracker/threshold \
  --value "2.5" \
  --overwrite
```

---

## Monitoring & Health Checks

### Daily Health Checks

**1. API Health Check**
```bash
curl https://1hdrnjh4kl.execute-api.us-east-1.amazonaws.com/prod/health
# Expected: {"status": "healthy"}
```

**2. Dashboard Check**
```bash
curl -I https://dqdtse490mbv1.cloudfront.net
# Expected: HTTP/2 200
```

**3. Lambda Function Status**
```bash
aws lambda get-function --function-name stock-scanner \
  --query 'Configuration.[State,LastUpdateStatus]'
# Expected: ["Active", "Successful"]
```

**4. Recent Lambda Executions**
```bash
aws logs tail /aws/lambda/stock-scanner --since 1h --format short
# Check for errors or failures
```

**5. DLQ Messages**
```bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/529088281783/stock-scanner-dlq \
  --attribute-names ApproximateNumberOfMessages
# Expected: 0 messages
```

### CloudWatch Metrics to Monitor

**Lambda Metrics:**
- Invocations (should be ~7-8 per day during market hours)
- Errors (should be 0)
- Duration (should be <5s)
- Throttles (should be 0)

**API Gateway Metrics:**
- 4XXError (client errors)
- 5XXError (server errors - should be 0)
- Latency (p95 should be <500ms with cache)
- CacheHitCount / CacheMissCount

**DynamoDB Metrics:**
- UserErrors (should be 0)
- SystemErrors (should be 0)
- ThrottledRequests (should be 0)

### Automated Alerts

**Set up CloudWatch Alarms:**

```bash
# Lambda error alarm
aws cloudwatch put-metric-alarm \
  --alarm-name stock-scanner-errors \
  --alarm-description "Alert on Lambda errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=stock-scanner

# API 5xx error alarm
aws cloudwatch put-metric-alarm \
  --alarm-name api-5xx-errors \
  --alarm-description "Alert on API 5xx errors" \
  --metric-name 5XXError \
  --namespace AWS/ApiGateway \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold
```

---

## Troubleshooting Guide

### Problem: Lambda Function Timing Out

**Symptoms:**
- Lambda duration > 120 seconds
- Task timed out errors in CloudWatch Logs

**Diagnosis:**
```bash
# Check recent execution times
aws logs filter-log-events \
  --log-group-name /aws/lambda/stock-scanner \
  --filter-pattern "REPORT" \
  --max-items 10
```

**Solutions:**
1. Increase timeout in `lambda_stack.py`:
   ```python
   timeout=Duration.seconds(180)
   ```
2. Optimize data processing logic
3. Check for slow external API calls
4. Redeploy: `cdk deploy LambdaStack`

---

### Problem: API Gateway 5xx Errors

**Symptoms:**
- API returns 500, 502, 503, or 504
- Users cannot access anomaly data

**Diagnosis:**
```bash
# Check Lambda logs for errors
aws logs tail /aws/lambda/api-handler --since 30m

# Check Lambda function status
aws lambda get-function --function-name stock-api-handler
```

**Solutions:**
1. Check Lambda function errors in CloudWatch
2. Verify IAM permissions for DynamoDB access
3. Test Lambda directly:
   ```bash
   aws lambda invoke \
     --function-name stock-api-handler \
     --payload '{"path":"/health","httpMethod":"GET"}' \
     /tmp/test.json
   ```
4. Check DynamoDB table status
5. Redeploy if needed: `cdk deploy ApiStack`

---

### Problem: No Anomalies Detected

**Symptoms:**
- DynamoDB table empty
- API returns empty anomalies array
- No alerts received

**Diagnosis:**
```bash
# Check if Lambda is running
aws logs tail /aws/lambda/stock-scanner --since 2h

# Check EventBridge rule
aws events list-rules --name-prefix Stock

# Check DynamoDB table
aws dynamodb scan --table-name stock-anomalies --limit 5
```

**Solutions:**
1. Verify EventBridge rule is enabled
2. Check Lambda execution role permissions
3. Verify mock data generation logic
4. Lower threshold temporarily for testing:
   ```bash
   aws ssm put-parameter \
     --name /stock-tracker/threshold \
     --value "1.0" \
     --overwrite
   ```
5. Manually invoke Lambda to test:
   ```bash
   aws lambda invoke --function-name stock-scanner /tmp/test.json
   ```

---

### Problem: Dashboard Not Loading

**Symptoms:**
- CloudFront returns 403 or 404
- Dashboard shows blank page

**Diagnosis:**
```bash
# Check CloudFront distribution status
aws cloudfront list-distributions \
  --query 'DistributionList.Items[?contains(Origins.Items[0].DomainName, `stock-dashboard`)].{Id:Id,Status:Status}'

# Check S3 bucket contents
aws s3 ls s3://stock-dashboard-529088281783/
```

**Solutions:**
1. Verify S3 bucket has index.html
2. Redeploy dashboard:
   ```bash
   cdk deploy DashboardStack
   ```
3. Invalidate CloudFront cache:
   ```bash
   aws cloudfront create-invalidation \
     --distribution-id YOUR_DISTRIBUTION_ID \
     --paths "/*"
   ```
4. Check CloudFront origin configuration

---

### Problem: DynamoDB Throttling

**Symptoms:**
- ProvisionedThroughputExceededException
- Slow API responses
- Lambda errors

**Diagnosis:**
```bash
# Check throttled requests
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ThrottledRequests \
  --dimensions Name=TableName,Value=stock-anomalies \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

**Solutions:**
1. On-demand billing should auto-scale (already configured)
2. Check for hot partition keys
3. Verify retry logic is working (exponential backoff)
4. Review query patterns - use GSIs instead of scans

---

### Problem: High AWS Costs

**Symptoms:**
- Unexpected AWS bill
- Cost alerts triggered

**Diagnosis:**
```bash
# Check Lambda invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=stock-scanner \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum

# Check API Gateway requests
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name Count \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum
```

**Solutions:**
1. Verify concurrency limit is set (5)
2. Check for runaway Lambda invocations
3. Review API Gateway cache hit rate
4. Disable API cache if not needed:
   ```python
   caching_enabled=False
   ```
5. Review S3 lifecycle policies
6. Check DynamoDB read/write patterns

---

## Incident Response

### Severity Levels

**P1 - Critical (Response: Immediate)**
- Complete system outage
- Data loss
- Security breach

**P2 - High (Response: <1 hour)**
- Partial system outage
- Performance degradation >50%
- Failed deployments

**P3 - Medium (Response: <4 hours)**
- Minor functionality issues
- Performance degradation <50%

**P4 - Low (Response: <24 hours)**
- Cosmetic issues
- Documentation errors

### Incident Response Steps

**1. Identify & Assess**
- Check CloudWatch Logs
- Review CloudWatch Metrics
- Check DLQ for failed messages
- Determine severity level

**2. Contain**
- If Lambda errors: Disable EventBridge rule
  ```bash
  aws events disable-rule --name StockScannerSchedule
  ```
- If API errors: Consider disabling API temporarily
- If security issue: Rotate credentials immediately

**3. Investigate**
- Review recent deployments
- Check CloudWatch Logs for error patterns
- Review CloudTrail for unauthorized access
- Check DLQ messages

**4. Resolve**
- Apply fix (code change, configuration update, rollback)
- Test in isolation
- Deploy fix
- Verify resolution

**5. Recover**
- Re-enable disabled services
- Clear DLQ if needed
- Monitor for recurrence

**6. Document**
- Create incident report
- Update runbook with lessons learned
- Implement preventive measures

---

## Backup & Recovery

### DynamoDB Backup

**Point-in-Time Recovery (Enabled):**
- Automatic continuous backups
- Restore to any point in last 35 days

**Manual Backup:**
```bash
# Create on-demand backup
aws dynamodb create-backup \
  --table-name stock-anomalies \
  --backup-name stock-anomalies-backup-$(date +%Y%m%d)
```

**Restore from Backup:**
```bash
# List backups
aws dynamodb list-backups --table-name stock-anomalies

# Restore to new table
aws dynamodb restore-table-from-backup \
  --target-table-name stock-anomalies-restored \
  --backup-arn arn:aws:dynamodb:us-east-1:529088281783:table/stock-anomalies/backup/BACKUP_ARN
```

### S3 Backup

**Versioning (Enabled):**
- All object versions retained
- Can restore previous versions

**Restore Previous Version:**
```bash
# List versions
aws s3api list-object-versions \
  --bucket stock-scan-data-529088281783 \
  --prefix raw-data/AAPL/

# Restore specific version
aws s3api copy-object \
  --bucket stock-scan-data-529088281783 \
  --copy-source stock-scan-data-529088281783/KEY?versionId=VERSION_ID \
  --key KEY
```

### Infrastructure Backup

**CDK Code (Version Controlled):**
- All infrastructure in Git
- Can redeploy from any commit

**CloudFormation Stack Export:**
```bash
# Export stack template
aws cloudformation get-template \
  --stack-name LambdaStack \
  --query TemplateBody \
  > lambda-stack-backup.json
```

---

## Rollback Procedures

### Lambda Function Rollback

**Option 1: Redeploy Previous Version**
```bash
# Checkout previous commit
git log --oneline
git checkout PREVIOUS_COMMIT

# Redeploy
cd cdk-app
cdk deploy LambdaStack --require-approval never

# Return to main
git checkout main
```

**Option 2: CloudFormation Rollback**
```bash
# Rollback stack
aws cloudformation rollback-stack --stack-name LambdaStack

# Monitor rollback
aws cloudformation describe-stacks \
  --stack-name LambdaStack \
  --query 'Stacks[0].StackStatus'
```

### Configuration Rollback

**Revert Parameter Store Values:**
```bash
# Get parameter history
aws ssm get-parameter-history --name /stock-tracker/ticker

# Restore previous value
aws ssm put-parameter \
  --name /stock-tracker/ticker \
  --value "AAPL" \
  --overwrite
```

### Complete System Rollback

**Emergency Rollback:**
```bash
# 1. Disable EventBridge
aws events disable-rule --name StockScannerSchedule

# 2. Rollback all stacks
cd cdk-app
git checkout LAST_KNOWN_GOOD_COMMIT
cdk deploy --all --require-approval never

# 3. Verify
aws lambda invoke --function-name stock-scanner /tmp/test.json
curl https://1hdrnjh4kl.execute-api.us-east-1.amazonaws.com/prod/health

# 4. Re-enable EventBridge
aws events enable-rule --name StockScannerSchedule
```

---

## Maintenance Windows

### Recommended Maintenance Schedule

**Weekly:**
- Review CloudWatch Logs for errors
- Check DLQ for failed messages
- Review cost reports
- Update dependencies if needed

**Monthly:**
- Review and update documentation
- Test backup/restore procedures
- Review security configurations
- Update CDK and dependencies

**Quarterly:**
- Conduct disaster recovery drill
- Review and update runbooks
- Security audit
- Performance optimization review

---

## Contact Information

**On-Call Engineer:** Sahr Malik  
**Escalation:** DevOps Team Lead  
**AWS Support:** Enterprise Support Plan

**Useful Links:**
- CloudWatch Dashboard: [Link to dashboard]
- GitHub Repository: [Link to repo]
- Documentation: [Link to docs]

---

**Runbook Version:** 1.0  
**Last Updated:** 2026-02-09  
**Next Review:** 2026-03-09
