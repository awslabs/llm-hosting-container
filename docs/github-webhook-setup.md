# GitHub Webhook Setup for CodeBuild Integration

This document describes how to set up the GitHub webhook that triggers AWS CodeBuild projects when pull requests are created by members of the `sagemaker-1p-algorithms` team.

## Overview

The webhook (`.github/workflows/pr-codebuild-webhook.yml`) performs the following actions:

1. **Triggers on PR events**: opened, synchronize, reopened
2. **Checks team membership**: Verifies if PR author or commit authors are members of `awslabs/sagemaker-1p-algorithms` team
3. **Triggers CodeBuild**: If team membership check passes, triggers both:
   - `tgi-pr-GPU` project
   - `tei-pr-CPU` project

## Required GitHub Repository Secrets

You need to configure the following secrets in your GitHub repository:

### 1. AWS Credentials
- `AWS_ACCESS_KEY_ID`: AWS access key with CodeBuild permissions
- `AWS_SECRET_ACCESS_KEY`: AWS secret access key

### 2. GitHub Token (Already Available)
- `GITHUB_TOKEN`: Automatically provided by GitHub Actions (no setup required)

## Setting up AWS Credentials

### Option 1: IAM User with Access Keys (Recommended for initial setup)

1. **Create an IAM User:**
   ```bash
   aws iam create-user --user-name github-codebuild-trigger
   ```

2. **Create access keys:**
   ```bash
   aws iam create-access-key --user-name github-codebuild-trigger
   ```

3. **Create IAM Policy:**
   ```bash
   cat > codebuild-trigger-policy.json << EOF
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "codebuild:StartBuild",
                   "codebuild:BatchGetBuilds"
               ],
               "Resource": [
                   "arn:aws:codebuild:us-west-2:515193369038:project/tgi-pr-GPU",
                   "arn:aws:codebuild:us-west-2:515193369038:project/tei-pr-CPU"
               ]
           }
       ]
   }
   EOF
   
   aws iam create-policy --policy-name CodeBuildTriggerPolicy --policy-document file://codebuild-trigger-policy.json
   ```

4. **Attach policy to user:**
   ```bash
   aws iam attach-user-policy --user-name github-codebuild-trigger --policy-arn arn:aws:iam::515193369038:policy/CodeBuildTriggerPolicy
   ```

### Option 2: OIDC (Recommended for production)

For better security, you can use OIDC instead of long-lived access keys. This requires setting up an OIDC provider in AWS and using role assumption.

## Adding Secrets to GitHub Repository

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the following secrets:
   - Name: `AWS_ACCESS_KEY_ID`, Value: `<your-access-key-id>`
   - Name: `AWS_SECRET_ACCESS_KEY`, Value: `<your-secret-access-key>`

## Team Setup Requirements

### GitHub Team Configuration

The workflow checks membership of the `sagemaker-1p-algorithms` team in the `awslabs` organization. Ensure:

1. **Team exists**: The team `sagemaker-1p-algorithms` must exist in the `awslabs` GitHub organization
2. **Team visibility**: The team should be visible (not secret) or the `GITHUB_TOKEN` needs appropriate permissions
3. **Members added**: Users who should trigger builds must be added to this team

### Team Management Commands

To manage the team membership:

```bash
# List team members (requires appropriate permissions)
gh api orgs/awslabs/teams/sagemaker-1p-algorithms/members

# Add a user to the team (requires admin permissions)
gh api -X PUT orgs/awslabs/teams/sagemaker-1p-algorithms/memberships/USERNAME
```

## CodeBuild Project Requirements

Your CodeBuild projects should be configured to:

1. **Source**: GitHub repository
2. **Webhook**: Not required (GitHub Actions will trigger directly)
3. **Environment**: Appropriate compute type for your builds
4. **Service Role**: Has permissions to access source and any required AWS services

### Environment Variables

The workflow passes the following environment variables to CodeBuild:

- `GITHUB_PR_NUMBER`: Pull request number
- `GITHUB_PR_HEAD_SHA`: Head commit SHA of the PR
- `GITHUB_PR_BASE_SHA`: Base commit SHA of the PR
- `GITHUB_REPOSITORY`: Repository name (awslabs/llm-hosting-container)

## Workflow Behavior

### Success Flow
1. PR is opened/updated by a team member
2. Team membership check passes
3. Both CodeBuild projects are triggered
4. GitHub comment is posted with build IDs and links

### Failure Flow
1. PR is opened/updated by a non-team member
2. Team membership check fails
3. GitHub comment is posted explaining the access denial
4. Workflow exits with error status

## Monitoring and Troubleshooting

### Check Workflow Runs
- Go to **Actions** tab in your GitHub repository
- Look for "PR Team Check and CodeBuild Trigger" workflow runs

### Common Issues

1. **Team membership check fails**: Verify team exists and user is a member
2. **AWS credentials error**: Check that secrets are set correctly
3. **CodeBuild start fails**: Verify project names and AWS permissions
4. **No commit usernames found**: This is normal for commits made with email addresses not linked to GitHub

### Debug Information

The workflow logs provide detailed information about:
- PR author identification
- Commit authors and their GitHub usernames
- Team membership check results
- CodeBuild trigger responses

## Security Considerations

1. **Principle of least privilege**: AWS IAM user only has permissions to start specific CodeBuild projects
2. **Team-based access**: Only members of the designated team can trigger builds
3. **Audit trail**: All actions are logged in GitHub Actions and AWS CloudTrail
4. **Limited scope**: Webhook only triggers on PR events, not on main branch pushes

## Testing the Setup

1. **Create a test PR** from a team member account
2. **Verify workflow runs** in GitHub Actions
3. **Check CodeBuild console** for triggered builds
4. **Review PR comments** for success/failure notifications

The workflow will automatically comment on PRs with build status and relevant information.
