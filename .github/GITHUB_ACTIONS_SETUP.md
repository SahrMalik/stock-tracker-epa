# GitHub Actions Setup Guide

## Prerequisites

1. **GitHub Repository**: Push your code to GitHub
2. **AWS Account**: Account ID 529088281783
3. **IAM OIDC Provider**: For GitHub Actions authentication

## Setup Steps

### 1. Create IAM OIDC Provider (One-time)

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 2. Create IAM Role for GitHub Actions

Create a file `github-actions-trust-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::529088281783:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_USERNAME/YOUR_REPO_NAME:*"
        }
      }
    }
  ]
}
```

Create the role:

```bash
aws iam create-role \
  --role-name GitHubActionsDeployRole \
  --assume-role-policy-document file://github-actions-trust-policy.json

# Attach AdministratorAccess (or create custom policy)
aws iam attach-role-policy \
  --role-name GitHubActionsDeployRole \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
```

### 3. Configure GitHub Secrets

Go to your GitHub repository → Settings → Secrets and variables → Actions

Add the following secret:
- **Name**: `AWS_ROLE_ARN`
- **Value**: `arn:aws:iam::529088281783:role/GitHubActionsDeployRole`

### 4. Push Code to GitHub

```bash
cd "/home/malisahm/project/Stock Tracker App"

# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Add CI/CD workflows"

# Add remote (replace with your repo URL)
git remote add origin https://github.com/YOUR_USERNAME/stock-anomaly-monitor.git

# Push
git push -u origin main
```

### 5. Verify Workflows

1. Go to your GitHub repository
2. Click on "Actions" tab
3. You should see workflows running automatically

## Workflow Triggers

### CI Workflow (ci.yml)
- Triggers on: Push to `main` or `develop`, Pull Requests
- Runs: Tests, linting, security scans, CDK synth
- Duration: ~3-5 minutes

### CD Workflow (cd.yml)
- Triggers on: Push to `main` only
- Runs: CDK deployment to AWS
- Duration: ~5-10 minutes

## Manual Deployment (Alternative)

If GitHub Actions is not set up, deploy manually:

```bash
cd cdk-app
cdk deploy --all --require-approval never
```

## Troubleshooting

**Problem**: "Error: Credentials could not be loaded"
- **Solution**: Verify AWS_ROLE_ARN secret is set correctly

**Problem**: "Error: User is not authorized to perform: sts:AssumeRoleWithWebIdentity"
- **Solution**: Check trust policy includes your GitHub repo

**Problem**: "CDK synth failed"
- **Solution**: Ensure all CDK dependencies are in requirements.txt

**Problem**: "Tests failed"
- **Solution**: Run tests locally first: `cd tests && pytest -v`

## Best Practices

1. **Branch Protection**: Require CI to pass before merging
2. **Code Review**: Require pull request reviews
3. **Secrets Management**: Never commit AWS credentials
4. **Testing**: Run tests locally before pushing
5. **Monitoring**: Check GitHub Actions logs for failures

## Next Steps

- Set up branch protection rules
- Add status badges to README
- Configure Slack/email notifications for failures
- Add deployment approval gates for production
