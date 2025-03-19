import git
import logging
import os
import shutil
import subprocess
import time

from huggingface.pytorch.release_utils import (
    ECR_SCAN_TIMEOUT_IN_SECONDS,
    GIT_REPO_DOCKERFILES_ROOT_DIRECTORY,
    GIT_REPO_PYTEST_PATH,
    LOG,
    Aws,
    Device,
    DlcPipeline,
    DockerClient,
    EnvironmentVariable,
    Mode,
    ReleaseConfigs,
    VulnerabilitySeverity,
)

GIT_REPO_TGI_LOCAL_FOLDER_NAME = "text-generation-inference"
GIT_REPO_TGI_TAG_PATTERN = "v{version}"
GIT_REPO_TGI_URL = "https://github.com/huggingface/text-generation-inference.git"

def build(configs: ReleaseConfigs):
    """Builds the Docker image for the provided configs."""
    aws = Aws()
    docker_client = DockerClient()
    for config in configs.releases:
        LOG.info(f"Going to build image for config: {config}.")
        image_uri = config.get_image_uri_for_staging()
        if aws.does_ecr_image_exist(image_uri):
            LOG.info(f"Skipping already built image '{image_uri}'. Config: {config}.")
            continue

        build_path = "."
        if config.device.lower() == Device.GPU.name.lower():
            LOG.info(f"Setting up build prerequisites for GPU release config with version: {config.version}")
            build_path = GIT_REPO_TGI_LOCAL_FOLDER_NAME
            shutil.rmtree(GIT_REPO_TGI_LOCAL_FOLDER_NAME, ignore_errors=True)
            hf_tgi_repo = git.Repo.clone_from(GIT_REPO_TGI_URL, GIT_REPO_TGI_LOCAL_FOLDER_NAME, no_checkout=True)
            hf_tgi_repo_tag = GIT_REPO_TGI_TAG_PATTERN.format(version=config.version)
            hf_tgi_repo.git.checkout(hf_tgi_repo_tag)
            LOG.info(f"Checked out {hf_tgi_repo} with tag: {hf_tgi_repo_tag} to {GIT_REPO_TGI_LOCAL_FOLDER_NAME}.")
            shutil.copytree(GIT_REPO_DOCKERFILES_ROOT_DIRECTORY,
                os.path.join(GIT_REPO_TGI_LOCAL_FOLDER_NAME, GIT_REPO_DOCKERFILES_ROOT_DIRECTORY))
            LOG.info(f"Copied '{GIT_REPO_DOCKERFILES_ROOT_DIRECTORY}' directory to TGI directory for 'COPY' command.")

        dockerfile_path = config.get_dockerfile_path()
        LOG.info(f"Building Dockerfile: '{dockerfile_path}'. This may take a while...")
        docker_client.build(image_uri=image_uri, dockerfile_path=dockerfile_path, build_path=build_path)

        username, password = aws.get_ecr_credentials(image_uri)
        docker_client.login(username, password, image_uri)
        docker_client.push(image_uri)

def test(configs: ReleaseConfigs):
    """Runs SageMaker tests for the Docker images associated with the provided configs and current git commit."""
    aws = Aws()
    for config in configs.releases:
        LOG.info(f"Going to test built image for config: {config}.")
        test_role_arn = os.getenv(EnvironmentVariable.TEST_ROLE_ARN.name)
        test_session = aws.get_session_for_role(test_role_arn)
        test_credentials = test_session.get_credentials()
        environ = os.environ.copy()
        environ.update({
            "DEVICE_TYPE": config.device.lower(),
            "AWS_ACCESS_KEY_ID": test_credentials.access_key,
            "AWS_SECRET_ACCESS_KEY": test_credentials.secret_key,
            "AWS_SESSION_TOKEN": test_credentials.token,
            "IMAGE_URI": config.get_image_uri_for_staging(),
            "TEST_ROLE_ARN": test_role_arn })

        command = ["pytest", "-m", config.device.lower(), "-n", "auto", "--log-cli-level", "info", GIT_REPO_PYTEST_PATH]
        LOG.info(f"Running test command: {command}.")
        process = subprocess.run(command, env=environ, encoding="utf-8", capture_output=True)
        LOG.info(process.stdout)
        assert process.returncode == 0, f"Failed with config: {config}.\nError: {process.stderr}."
        LOG.info(f"Finished testing image with config: {config}.")

        start_time = time.time()
        image_uri = config.get_image_uri_for_staging()
        while aws.is_ecr_image_scan_pending(image_uri):
            LOG.info(f"Waiting for image scan results for image: {image_uri}.")
            assert time.time() - start_time <= ECR_SCAN_TIMEOUT_IN_SECONDS, \
                f"{image_uri} with config {config} has not completed scanning beyond permitted wait time."

        severities = {VulnerabilitySeverity.CRITICAL.name}
        vulnerability_ids = aws.get_image_scan_findings(image_uri, severities, set(configs.ignore_vulnerabilities))
        assert len(vulnerability_ids) == 0, f"{image_uri} with {config} has vulnerabilities: {vulnerability_ids}."
        LOG.info(f"Finished checking vulnerabilities for image: {image_uri}.")

def pr(configs: ReleaseConfigs):
    """Executes both build and test modes."""
    build(configs)
    test(configs)

def release(configs: ReleaseConfigs):
    """Integrates with DLC to release the tested images associated for the provided configs."""
    aws = Aws()
    docker_client = DockerClient()
    for config in configs.releases:
        LOG.info(f"Releasing image associated for config: {config}.")
        released_image_uri = config.get_image_uri_for_released()
        if aws.does_ecr_image_exist(released_image_uri):
            LOG.info(f"Skipping already released image '{released_image_uri}'. Config: {config}.")
            continue

        staged_image_uri = config.get_image_uri_for_staging()
        username, password = aws.get_ecr_credentials(staged_image_uri)
        docker_client.login(username, password, staged_image_uri)
        docker_client.prune_all()
        docker_client.pull(staged_image_uri)

        pipeline = DlcPipeline(aws, docker_client)
        pipeline.stage_image(config)
        pipeline.set_parameters(config)
        pipeline.start_pipeline(config)
        LOG.info(f"DLC pipeline completed for staged image URI: {staged_image_uri}.")

        username, password = aws.get_ecr_credentials(staged_image_uri)
        docker_client.login(username, password, staged_image_uri)
        released_image_uri = config.get_image_uri_for_released()
        docker_client.tag(staged_image_uri, released_image_uri)
        docker_client.push(released_image_uri)
        LOG.info(f"Release marked as complete for following config ({released_image_uri}): {config}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    configs = ReleaseConfigs()
    configs.validate()
    mode = os.getenv(EnvironmentVariable.MODE.name)
    LOG.info(f"Mode has been set to: {mode}.")
    if mode == Mode.PR.name:
        pr(configs)
    elif mode == Mode.BUILD.name:
        build(configs)
    elif mode == Mode.TEST.name:
        test(configs)
    elif mode == Mode.RELEASE.name:
        release(configs)
    else:
        raise ValueError(f"The mode '{mode}' is not recognized. Please set it correctly.'")