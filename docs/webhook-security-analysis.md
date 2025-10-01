# GitHub Webhook Security Analysis

## Overview

This document analyzes the security implementation of the GitHub webhook for the `llm-hosting-container` repository, which triggers AWS CodeBuild projects based on team membership verification.

## Security Architecture: Two-Workflow Pattern

### The Secure Solution

To address the "Checkout of untrusted code in trusted context" vulnerability, we've implemented a **two-workflow security pattern** that separates untrusted PR processing from privileged operations.

## Workflow Architecture

### Workflow 1: PR Team Check (Untrusted) - `pr-team-check.yml`

**Purpose**: Process untrusted PR code in an isolated environment
**Trigger**: `pull_request` (runs in unprivileged context)
**Permissions**: `contents: read` only

**Key Features**:
- ✅ Safely checks out PR code (untrusted)
- ✅ Extracts PR and commit author information
- ✅ Detects workflow file modifications
- ✅ Creates artifacts with validated data
- ✅ No access to secrets or AWS credentials

### Workflow 2: PR CodeBuild Trigger (Privileged) - `pr-codebuild-trigger.yml`

**Purpose**: Perform privileged operations with validated data
**Trigger**: `workflow_run` (triggered by completion of first workflow)
**Permissions**: `contents: read`, `pull-requests: write`, `issues: write`

**Key Features**:
- ✅ Downloads and validates artifacts from untrusted workflow
- ✅ Performs team membership checks with GitHub API
- ✅ Has access to AWS credentials and secrets
- ✅ Triggers CodeBuild projects
- ✅ Posts comments on PRs

## Security Vulnerability: Workflow Modification Attack

### The Original Problem

The initial single-workflow implementation had a critical security vulnerability:

1. **Attacker creates a malicious PR** that modifies workflow files
2. **Workflow runs with modified code** from the PR branch
3. **Security checks are bypassed** because the attacker controls the workflow logic
4. **AWS CodeBuild projects are triggered** without proper authorization
5. **AWS resources are compromised** through unauthorized access

### Attack Scenario (Previous Implementation)

```yaml
# Malicious workflow modification in attacker's PR
- name: Check team membership for PR author
  run: |
    # Attacker bypasses the real team check
    echo "pr_author_is_member=true" >> $GITHUB_OUTPUT
```

This allowed any external contributor to bypass team membership checks and trigger expensive AWS CodeBuild projects.

## Security Solution: Multi-Layered Protection

### 1. Two-Workflow Isolation Pattern

**Untrusted Workflow (`pull_request`)**:
- Processes PR code in isolated environment
- No access to secrets or AWS credentials
- Cannot trigger privileged operations
- Creates validated artifacts for privileged workflow

**Privileged Workflow (`workflow_run`)**:
- Runs trusted code from main branch
- Has access to secrets and AWS credentials
- Downloads and validates artifacts from untrusted workflow
- Performs all privileged operations

### 2. Artifact Validation and Sanitization

```yaml
# Privileged workflow validates all data from artifacts
- name: Extract and validate PR information
  run: |
    # Validate PR_NUMBER is numeric
    if ! [[ "$PR_NUMBER" =~ ^[0-9]+$ ]]; then
      echo "::error::Invalid PR number: $PR_NUMBER"
      exit 1
    fi
    
    # Validate SHA format (40 character hex)
    if ! [[ "$HEAD_SHA" =~ ^[a-f0-9]{40}$ ]]; then
      echo "::error::Invalid HEAD SHA format: $HEAD_SHA"
      exit 1
    fi
```

### 3. Security Validation Step

```yaml
- name: Security validation
  run: |
    if [[ "$workflow_modified" == "true" ]]; then
      echo "🚨 SECURITY BLOCK: This PR modifies workflow files"
      # Block execution and post security warning
    fi
```

### 4. Conditional Execution Protection

```yaml
- name: Configure AWS Credentials
  if: |
    steps.security-check.outputs.security_blocked == 'false' && 
    (team membership conditions...)
```

### 5. CODEOWNERS Protection

```
.github/workflows/ @awslabs/sagemaker-1p-algorithms
```

## Security Benefits of Two-Workflow Pattern

### ✅ **Isolation of Untrusted Code**
- PR code runs in unprivileged environment
- No access to secrets or AWS credentials
- Cannot directly trigger privileged operations

### ✅ **Trusted Execution Context**
- Privileged operations run trusted code from main branch
- Attacker cannot modify privileged workflow logic
- All data from untrusted workflow is validated

### ✅ **Defense in Depth**
- Multiple validation layers
- Artifact sanitization
- Security checks in both workflows

### ✅ **Fail-Safe Defaults**
- Block execution when validation fails
- Explicit security error messages
- No silent failures

## Implementation Phases

### Phase 1: Two-Workflow Architecture ✅
- Separate untrusted and privileged workflows
- Implement artifact-based communication
- Add comprehensive validation

### Phase 2: Enhanced Security Validation ✅
- Workflow modification detection
- Data sanitization and validation
- Security block mechanisms

### Phase 3: Access Control & Monitoring ✅
- CODEOWNERS file protection
- Explicit permissions configuration
- Comprehensive audit logging

## Security Best Practices Applied

1. **Principle of Least Privilege**: Minimal permissions for each workflow
2. **Defense in Depth**: Multiple security layers and validations
3. **Fail-Safe Defaults**: Block execution when security checks fail
4. **Input Validation**: Sanitize all data from untrusted sources
5. **Audit Trail**: Comprehensive logging of all security decisions
6. **Human Oversight**: Required reviews for workflow changes

## Comparison: Before vs After

### Before (Vulnerable)
```yaml
on: pull_request_target  # Privileged context
jobs:
  build:
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}  # ❌ Untrusted code
      - name: Team check
        run: |
          # ❌ Attacker can modify this logic
```

### After (Secure)
```yaml
# Workflow 1: Untrusted
on: pull_request  # ❌ Unprivileged context
jobs:
  check:
    steps:
      - uses: actions/checkout@v4  # ✅ Safe in unprivileged context
      - name: Create artifacts  # ✅ No secrets access

# Workflow 2: Privileged  
on: workflow_run  # ✅ Triggered by completion
jobs:
  trigger:
    steps:
      - name: Download artifacts  # ✅ Validate untrusted data
      - name: Team check  # ✅ Trusted code from main branch
```

## Monitoring and Detection

### Security Indicators to Monitor
- PRs modifying workflow files
- Unexpected CodeBuild executions
- Failed artifact validations
- Security block activations

### Audit Trail
- All team membership checks logged
- Security decisions recorded
- CodeBuild triggers tracked
- PR comments provide transparency

## Remaining Considerations

1. **Team Management**: Ensure `sagemaker-1p-algorithms` team is properly maintained
2. **Access Control**: Regular audit of team membership
3. **Monitoring**: Watch for unusual CodeBuild activity
4. **Incident Response**: Plan for handling security breaches
5. **Artifact Retention**: Artifacts are retained for 1 day only

## Conclusion

The implemented two-workflow security architecture provides robust protection against workflow modification attacks and untrusted code execution while maintaining the required functionality for team-based CodeBuild triggering. 

**Key Security Achievements**:
- ✅ Eliminated untrusted code execution in privileged context
- ✅ Implemented comprehensive input validation
- ✅ Added multiple layers of security controls
- ✅ Maintained full functionality for authorized users
- ✅ Provided clear audit trail and transparency

The multi-layered approach ensures that even if one security control fails, others will prevent unauthorized access to AWS resources. This architecture follows GitHub's recommended security best practices for handling untrusted PR content.
