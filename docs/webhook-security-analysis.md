# Webhook Security Analysis: How It Works and Potential Vulnerabilities

## How the Webhook Works

### Overview
The GitHub Actions webhook (`.github/workflows/pr-codebuild-webhook.yml`) is designed to automatically trigger AWS CodeBuild projects when pull requests are created by members of the `sagemaker-1p-algorithms` team.

### Workflow Execution Flow

1. **Trigger Events**
   - Activates on PR events: `opened`, `synchronize`, `reopened`
   - Runs on GitHub-hosted Ubuntu runners

2. **Author Identification**
   - Extracts PR author from `github.event.pull_request.user.login`
   - Analyzes git history to find all commit authors in the PR
   - Attempts to map commit emails to GitHub usernames

3. **Team Membership Verification**
   - Uses GitHub API to check if PR author is in `awslabs/sagemaker-1p-algorithms` team
   - Checks each commit author's team membership
   - Uses `GITHUB_TOKEN` (automatically provided by GitHub Actions)

4. **CodeBuild Triggering**
   - If any author is a team member, configures AWS credentials
   - Triggers both `tgi-pr-GPU` and `tei-pr-CPU` CodeBuild projects
   - Posts success/failure comments on the PR

## Security Vulnerability: Workflow Modification Attack

### The Problem
**Yes, someone can bypass the team check by modifying the workflow file in their PR.**

### Attack Scenario
1. **Attacker creates a PR** that includes changes to `.github/workflows/pr-codebuild-webhook.yml`
2. **Modifies the workflow** to remove or bypass team membership checks
3. **GitHub Actions runs the modified workflow** from the PR branch
4. **CodeBuild projects are triggered** without proper authorization

### Example Malicious Modifications

#### 1. Remove Team Check Entirely
```yaml
# Attacker removes the team membership check steps
- name: Trigger CodeBuild Projects
  # Remove the 'if' condition that checks team membership
  run: |
    echo "🚀 Triggering CodeBuild projects..."
    # ... rest of CodeBuild triggering code
```

#### 2. Always Pass Team Check
```yaml
- name: Fake team check
  id: check-pr-author
  run: |
    echo "pr_author_is_member=true" >> $GITHUB_OUTPUT
```

#### 3. Modify Team Name
```yaml
# Change team name to a team the attacker controls
"https://api.github.com/orgs/awslabs/teams/attacker-controlled-team/members/$username"
```

## Why This Vulnerability Exists

### GitHub Actions Security Model
- **PR workflows run with the PR's code**: GitHub Actions executes the workflow file from the PR branch
- **Access to secrets**: PR workflows have access to repository secrets (AWS credentials)
- **No built-in protection**: GitHub doesn't prevent workflow modifications in PRs by default

## Security Mitigations and Recommendations

### 1. Branch Protection Rules (Recommended)
```yaml
# Configure in GitHub repository settings
branch_protection:
  required_status_checks:
    - "check-team-and-trigger-builds"
  enforce_admins: true
  required_pull_request_reviews:
    required_approving_review_count: 2
    dismiss_stale_reviews: true
    require_code_owner_reviews: true
```

### 2. Use `pull_request_target` Instead of `pull_request`
```yaml
# More secure trigger - runs workflow from main branch
on:
  pull_request_target:
    types: [opened, synchronize, reopened]
```

**Benefits:**
- Workflow code comes from the target branch (main), not PR branch
- Attacker cannot modify the workflow logic
- Still has access to PR information via `github.event`

### 3. Separate Workflow for Security Checks
Create a separate workflow that cannot be modified:

```yaml
# .github/workflows/security-gate.yml (protected)
name: Security Gate
on:
  pull_request_target:
    types: [opened, synchronize, reopened]

jobs:
  security-check:
    runs-on: ubuntu-latest
    steps:
      - name: Team membership check
        # Immutable team check logic
      - name: Set status check
        # Create a required status check
```

### 4. CODEOWNERS File Protection
```
# CODEOWNERS file
.github/workflows/ @awslabs/sagemaker-1p-algorithms
```

### 5. Environment Protection Rules
- Use GitHub Environments with protection rules
- Require manual approval for deployments
- Restrict environment access to specific teams

### 6. External Webhook (Most Secure)
Instead of GitHub Actions, use an external webhook service:

```yaml
# External service validates team membership
# Only triggers CodeBuild after verification
# Cannot be modified by PR authors
```

## Recommended Implementation Strategy

### Phase 1: Immediate Security (Low Risk)
1. **Switch to `pull_request_target`**
2. **Add CODEOWNERS protection**
3. **Enable branch protection rules**

### Phase 2: Enhanced Security (Medium Risk)
1. **Implement environment protection**
2. **Add manual approval gates**
3. **Create separate security workflow**

### Phase 3: Maximum Security (High Risk)
1. **External webhook service**
2. **Zero-trust verification**
3. **Audit logging and monitoring**

## Current Risk Assessment

### Risk Level: **HIGH**
- ✅ **Easy to exploit**: Simple workflow modification
- ✅ **High impact**: Unauthorized CodeBuild execution
- ✅ **AWS resource access**: Potential cost and security implications
- ✅ **No current protections**: Workflow can be freely modified

### Immediate Actions Required
1. **Switch to `pull_request_target` trigger**
2. **Add CODEOWNERS file**
3. **Enable branch protection**
4. **Monitor for suspicious PRs**

## Detection and Monitoring

### Signs of Attack
- PRs that modify `.github/workflows/` files
- Unexpected CodeBuild executions
- PRs from unknown contributors with workflow changes
- Failed team membership API calls

### Monitoring Setup
```bash
# GitHub webhook to monitor workflow changes
# AWS CloudTrail for CodeBuild API calls
# GitHub audit logs for team membership changes
```

## Conclusion

The current webhook implementation has a **critical security vulnerability** that allows attackers to bypass team membership checks by modifying the workflow file in their PR. This is a common GitHub Actions security issue that requires immediate attention.

**The most effective immediate fix is switching to `pull_request_target` trigger combined with branch protection rules and CODEOWNERS file protection.**
