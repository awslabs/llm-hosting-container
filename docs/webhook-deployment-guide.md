# GitHub Webhook Deployment Guide

## Overview

This guide explains how to properly deploy the two-workflow GitHub webhook architecture for the llm-hosting-container repository. The architecture consists of two workflows that work together to securely check team membership and trigger AWS CodeBuild projects.

## Deployment Challenge

The two-workflow architecture presents a deployment challenge:
- The privileged workflow (`pr-codebuild-trigger.yml`) references the untrusted workflow by name ("PR Team Check (Untrusted)")
- When deploying via PR, the untrusted workflow doesn't exist in the main branch yet
- This creates a chicken-and-egg problem where the privileged workflow fails to find the referenced workflow

## Deployment Strategies

### Strategy 1: Sequential Deployment (Recommended)

Deploy the workflows in two separate PRs to avoid the chicken-and-egg problem:

#### Phase 1: Deploy Untrusted Workflow Only
1. Create a PR with only the untrusted workflow:
   - `.github/workflows/pr-team-check.yml`
   - `docs/webhook-security-analysis.md`
   - `docs/github-webhook-setup.md`
   - `docs/webhook-deployment-guide.md` (this file)

2. Merge this PR to main branch

#### Phase 2: Deploy Privileged Workflow
1. Create a second PR with the privileged workflow:
   - `.github/workflows/pr-codebuild-trigger.yml`
   - Updated `CODEOWNERS` file

2. Merge this PR to main branch

#### Phase 3: Test the Complete System
1. Create a test PR to verify both workflows work together
2. Confirm team membership checks and CodeBuild triggering

### Strategy 2: Temporary Workflow Name (Alternative)

If you prefer single-PR deployment:

1. Temporarily modify the privileged workflow to use a generic workflow name
2. Deploy both workflows in the same PR
3. Update the workflow reference in a follow-up commit

### Strategy 3: Manual Workflow Creation (Advanced)

For immediate deployment:

1. Manually create the untrusted workflow file directly in the main branch via GitHub UI
2. Then deploy the privileged workflow via PR

## Pre-Deployment Checklist

Before deploying either workflow, ensure:

- [ ] AWS credentials are configured in GitHub repository secrets:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
- [ ] The `sagemaker-1p-algorithms` team exists in the awslabs GitHub organization
- [ ] Team members are properly added to the team
- [ ] AWS CodeBuild projects exist:
  - `tgi-pr-GPU` in us-west-2 region
  - `tei-pr-CPU` in us-west-2 region

## Post-Deployment Configuration

After both workflows are deployed:

1. **Enable Branch Protection Rules**:
   - Require PR reviews for main branch
   - Require status checks to pass
   - Restrict pushes to main branch

2. **Verify CODEOWNERS Protection**:
   - Ensure `.github/workflows/` requires team review
   - Test that workflow modifications trigger proper reviews

3. **Test the Complete Flow**:
   - Create a test PR from a team member account
   - Verify team membership check passes
   - Confirm CodeBuild projects are triggered
   - Test with non-team member to verify rejection

## Workflow Dependencies

The workflows have the following dependency chain:

```
PR Created/Updated
       ↓
pr-team-check.yml (Untrusted)
   - Extracts PR info
   - Creates artifacts
   - Completes
       ↓
pr-codebuild-trigger.yml (Privileged)
   - Triggered by workflow_run
   - Downloads artifacts
   - Checks team membership
   - Triggers CodeBuild (if authorized)
```

## Troubleshooting

### Common Issues

1. **"Workflow not found" error**:
   - Ensure the untrusted workflow exists in the main branch
   - Check workflow name matches exactly in the privileged workflow

2. **Team membership check fails**:
   - Verify team exists and user is a member
   - Check GitHub token permissions
   - Ensure team visibility settings allow API access

3. **CodeBuild not triggered**:
   - Verify AWS credentials are configured
   - Check CodeBuild project names and regions
   - Review AWS IAM permissions

4. **Artifacts not found**:
   - Ensure untrusted workflow completed successfully
   - Check artifact names match between workflows
   - Verify workflow_run trigger conditions

### Debug Steps

1. Check GitHub Actions logs for both workflows
2. Verify artifact creation and download
3. Test team membership API calls manually
4. Validate AWS CLI commands in isolation

## Security Considerations

- Never merge both workflows simultaneously without proper testing
- Always test with non-team members to verify access control
- Monitor workflow logs for security events
- Regularly review team membership and access patterns

## Rollback Plan

If issues occur after deployment:

1. **Immediate**: Disable the workflows via GitHub UI
2. **Short-term**: Revert the PR that introduced the problematic workflow
3. **Long-term**: Fix issues and redeploy using proper sequence

## Support

For issues with this deployment:
1. Check the troubleshooting section above
2. Review workflow logs in GitHub Actions
3. Consult the security analysis document for architecture details
