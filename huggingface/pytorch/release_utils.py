import base64
import dataclasses
import datetime
import enum
import json
import logging
import os
import re
import subprocess
import time
import typing
from typing import Dict, List

import boto3
import docker
import git
from packaging.version import parse

# The source-of-truth dictionary mapping framework names to lists of device types.
FRAMEWORK_DEVICE_DICT: Dict[str, List[str]] = {
    "TGI": ["GPU", "INF2"],
    "TEI": ["GPU", "CPU"],
    "TGILLAMACPP": ["CPU"],
}
Framework = enum.Enum("Framework", ["TGI", "OPTIMUM", "TEI", "TGILLAMACPP"])
Device = enum.Enum("Device", ["GPU", "INF2", "CPU"])
Mode = enum.Enum("Mode", ["PR", "BUILD", "TEST", "RELEASE"])
PipelineStatus = enum.Enum(
    "PipelineStatus", ["IN_PROGRESS", "SUCCESSFUL", "UNSUCCESSFUL"]
)
VulnerabilitySeverity = enum.Enum("VulnerabilitySeverity", ["CRITICAL", "HIGH"])
EnvironmentVariable = enum.Enum(
    "EnvironmentVariable",
    [
        "CODEBUILD_RESOLVED_SOURCE_VERSION",
        "DEVICE_TYPE",
        "FRAMEWORK",
        "JS_ECR_REPO_URI",
        "DLC_ECR_REPO_URI",
        "DLC_ENABLE_PIPELINE_EXECUTION",
        "DLC_ENABLE_PIPELINE_STATUS_CHECK",
        "DLC_ROLE_ARN",
        "DOCKER_MAX_JOBS",
        "INTERNAL_STAGING_REPO_URI",
        "MAX_JOBS",
        "MODE",
        "TEST_ROLE_ARN",
    ],
)

DEFAULT_CRED_REFRESH_INTERVAL_IN_SECONDS = 1800
DEFAULT_WAIT_INTERVAL_IN_SECONDS = 60
DLC_PIPELINE_NAME_BY_DEVICE = {
    Device.GPU.name.lower(): "HFTgiReleasePipeline-huggingface-pytorch-tgi-inference-gpu",
    Device.INF2.name.lower(): "HFTgiReleasePipeline-huggingface-pytorch-tgi-inference-neuronx",
}
ECR_RELEASED_SUFFIX_TAG = "-released"
ECR_TAG_DIGEST_PREFIX = "sha256"
ECR_URI_REGEX = r"^([\d\w\.-]*)\/([\w\d-]*)[:@]([\d\w\.:-]*)$"
ECR_SCAN_TIMEOUT_IN_SECONDS = 900
GIT_REPO_DOCKERFILE_NAME = "Dockerfile"
GIT_REPO_DOCKERFILE_PATH_TEMPLATE = "huggingface/pytorch/{framework}/docker/{version}"
GIT_REPO_DOCKERFILE_PATH_TEMPLATE_WITH_DEVICE = (
    "huggingface/pytorch/{framework}/docker/{version}/{device}"
)
GIT_REPO_DOCKERFILES_ROOT_DIRECTORY = "huggingface"
GIT_REPO_RELEASE_CONFIG_FILENAME = "releases.json"
GIT_REPO_PYTEST_PATH = "tests/huggingface"
LOG = logging.getLogger(__name__)
SESSION_NAME = "JumpStartLLMHosing"


class ReleaseConfigs:
    """Object representation of release config JSON file in the GitHub repo.

    Sample:
    {
        "permitted_combinations": {
        "TGI": [
            {
                "device": "gpu",
                "min_version": "0.8.2",
                "max_version": "1.1.0",
                "os_version": "ubuntu20.04",
                "cuda_version": "cu118",
                "python_version": "py39",
                "pytorch_version": "2.0.1"
            },
            {
                # Note that there is no cuda_version for inf2.
                "device": "inf2",
                "min_version": "0.0.16",
                "max_version": "0.0.16",
                "os_version": "ubuntu22.04",
                "python_version": "py39",
                "pytorch_version": "1.13.1"
            }
        ],
        "TEI": [
            {
                "device": "gpu",
                "min_version": "0.9.0",
                "max_version": "1.2.0",
                "os_version": "ubuntu20.04",
                "cuda_version": "cu120"
            },
            {
                "device": "inf2",
                "min_version": "0.0.20",
                "max_version": "0.0.20",
                "os_version": "ubuntu22.04",
                "python_version": "py39",
                "pytorch_version": "1.15.0"
            }
        ]}
        "ignore_vulnerabilities": ["CVE‑2023‑38737"],
        "releases": [
            {
                "framework": "TGI"
                "device": "gpu",
                "version": "1.1.0",
                "os_version": "ubuntu20.04",
                "cuda_version": "cu118",
                "python_version": "py39",
                "pytorch_version": "2.0.1"
            }
        ]
    }
    """

    @dataclasses.dataclass
    class ReleaseConfig:
        framework: str
        device: str
        version: str
        os_version: str
        python_version: typing.Optional[str] = None
        pytorch_version: typing.Optional[str] = None
        cuda_version: typing.Optional[str] = None

        def get_dockerfile_path(self) -> str:
            """Retrieves the expected path of Dockerfile associated with the given config."""
            framework = self.framework.lower()
            dockerfile_path = ""

            if (
                self.framework.lower() == Framework.TGI.name.lower()
                and self.device.lower() == Device.INF2.name.lower()
            ):
                framework = Framework.OPTIMUM.name.lower()

            # Determine the path template to use based on the framework
            if framework in [
                Framework.TGI.name.lower(),
                Framework.OPTIMUM.name.lower(),
            ]:
                dockerfile_path = GIT_REPO_DOCKERFILE_PATH_TEMPLATE.format(
                    framework=framework, version=self.version
                )
            else:
                dockerfile_path = GIT_REPO_DOCKERFILE_PATH_TEMPLATE_WITH_DEVICE.format(
                    framework=framework,
                    version=self.version,
                    device=self.device.lower(),
                )

            return os.path.join(os.getcwd(), dockerfile_path, GIT_REPO_DOCKERFILE_NAME)

        def get_image_uri_for_staging(self) -> str:
            """Gets unique image URI that can be referenced across the pipeline within the same execution."""
            commit_hash = os.getenv(
                EnvironmentVariable.CODEBUILD_RESOLVED_SOURCE_VERSION.name
            )
            if commit_hash is None:
                commit_hash = git.Repo().head.commit.hexsha

            tag = f"{self.version}-{self.device.lower()}-{commit_hash}"
            repo_uri = os.getenv(EnvironmentVariable.INTERNAL_STAGING_REPO_URI.name)
            return f"{repo_uri}:{tag}"

        def get_image_uri_for_released(self) -> str:
            """Gets the image URI for a staged image that has been successfully released."""
            image_uri = self.get_image_uri_for_staging()
            return f"{image_uri}{ECR_RELEASED_SUFFIX_TAG}"

        def get_image_uris_for_dlc(self) -> typing.List[str]:
            """Get the image URIs for DLC with the contractual tagging for integration purposes."""
            base_tag = None
            if self.device.lower() == Device.GPU.name.lower():
                base_tag = (
                    f"{self.pytorch_version}-tgi{self.version}-{self.device.lower()}-{self.python_version}-"
                    f"{self.cuda_version}-{self.os_version}-benchmark-tested"
                )
            elif self.device.lower() == Device.INF2.name.lower():
                base_tag = f"{self.pytorch_version}-optimum{self.version}-neuronx-{self.python_version}-{self.os_version}-benchmark-tested"
            assert base_tag is not None, (
                f"No associated DLC tag pattern associated with device type '{self.device}'."
            )
            dated_tag = (
                f"{base_tag}-{datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
            )
            repo_uri = os.getenv(EnvironmentVariable.DLC_ECR_REPO_URI.name)
            return [f"{repo_uri}:{tag}" for tag in [base_tag, dated_tag]]

        def get_image_uris_for_jumpstart(self) -> typing.List[str]:
            """Get the image URIs for JumpStart"""
            base_tag = None
            repo_uri = (
                os.getenv(EnvironmentVariable.JS_ECR_REPO_URI.name)  # type: ignore
                + f"{self.framework.lower()}"
            )
            if self.device.lower() == Device.GPU.name.lower():
                base_tag = (
                    f"{self.pytorch_version}-{self.framework.lower()}{self.version}-gpu-{self.python_version}-"
                    f"{self.cuda_version}-{self.os_version}"
                )
            elif self.device.lower() == Device.CPU.name.lower():
                base_tag = (
                    f"{self.pytorch_version}-{self.framework.lower()}{self.version}-cpu-{self.python_version}-"
                    f"{self.os_version}"
                )
                repo_uri += f"-{self.device.lower()}"
            assert base_tag is not None, (
                f"No associated JumpStart tag pattern associated with device type '{self.device}'."
            )
            dated_tag = (
                f"{base_tag}-{datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
            )
            return [f"{repo_uri}:{tag}" for tag in [base_tag, dated_tag]]

    @dataclasses.dataclass
    class PermittedCombination:
        framework: str
        device: str
        min_version: str
        max_version: str
        os_version: str
        python_version: typing.Optional[str] = None
        pytorch_version: typing.Optional[str] = None
        cuda_version: typing.Optional[str] = None

        def __init__(
            self,
            framework: str,
            device: str,
            min_version: str,
            max_version: str,
            os_version: str,
            python_version: typing.Optional[str] = None,
            pytorch_version: typing.Optional[str] = None,
            cuda_version: typing.Optional[str] = None,
        ):
            self.framework = framework.upper()
            self.device = device.upper()
            self.min_version = min_version
            self.max_version = max_version
            self.os_version = os_version
            self.python_version = python_version
            self.pytorch_version = pytorch_version
            self.cuda_version = cuda_version

    def __init__(self, filepath_override=None):
        filepath = (
            filepath_override if filepath_override else GIT_REPO_RELEASE_CONFIG_FILENAME
        )
        with open(filepath) as file_in:
            configs = json.load(file_in)
            framework = os.getenv(EnvironmentVariable.FRAMEWORK.name)
            self.permitted_combinations = []
            for combination in configs.get("permitted_combinations", {}).get(
                framework, {}
            ):
                pc = self.PermittedCombination(framework=framework, **combination)  # type: ignore
                self.permitted_combinations.append(pc)

            LOG.info(
                f"Loaded permitted combinations for {framework}: {self.permitted_combinations}."
            )
            self.ignore_vulnerabilities: typing.List[str] = configs.get(
                "ignore_vulnerabilities", []
            )
            LOG.info(f"Loaded ignore vulnerabilities: {self.ignore_vulnerabilities}.")
            device = os.getenv(EnvironmentVariable.DEVICE_TYPE.name)
            releases = configs.get("releases", [])
            for release in releases:
                release["device"] = release.get("device").upper()
                release["framework"] = release.get("framework").upper()
            supported_releases = [
                item for item in releases if item.get("framework").upper() == framework
            ]
            LOG.info(f"supported_releases are {supported_releases}")
            release_devices = [
                item.get("device").upper()
                for item in supported_releases
                if item.get("device")
            ]
            LOG.info(f"release_devices are {release_devices}")
            allowed_devices = FRAMEWORK_DEVICE_DICT.get(framework)  # type: ignore
            assert set(release_devices).issubset(allowed_devices), (  # type: ignore
                f"Releases contain an unsupported device type: {release_devices}."
            )
            self.releases = [
                self.ReleaseConfig(**item)
                for item in supported_releases
                if item.get("device").upper() == device.upper()  # type: ignore
            ]
            LOG.info(
                f"Loaded releases for container {framework} with device type'{device}': {self.releases}."
            )

    def validate(self):
        """Confirms that the releases match one of the permitted combinations."""
        codebuild_device = os.getenv(EnvironmentVariable.DEVICE_TYPE.name)
        device_set = set()
        for config in self.releases:
            is_valid = False
            for allowed in self.permitted_combinations:
                version = parse(config.version)
                min_version = parse(allowed.min_version)
                max_version = parse(allowed.max_version)
                if (
                    codebuild_device.upper() == config.device.upper()  # type: ignore
                    and allowed.device.upper() == config.device.upper()
                    and min_version <= version <= max_version
                ):
                    if config.device == Device.INF2.name.lower():
                        assert config.cuda_version is None, (
                            f"Optimum framework should not have a cuda_version specified: {config}."
                        )
                    elif config.device.lower() == Device.GPU.name.lower():
                        assert (
                            "cu" in config.cuda_version  # type: ignore
                            and config.cuda_version == allowed.cuda_version
                        ), (
                            f"Invalid CUDA version specified: {config}.\nAllowed: {allowed}"
                        )
                    assert re.search(r"\d+\.\d+\.\d+", config.version), (
                        f"Invalid framework version specified: {config}.\nAllowed: {allowed}"
                    )
                    assert (
                        "ubuntu" in config.os_version
                        and config.os_version == allowed.os_version
                    ), f"Invalid OS version specified: {config}.\nAllowed: {allowed}"
                    # Since Text Embeddings Inference (TEI) is Rust-only, both Python and PyTorch versions don't apply
                    if config.framework != "TEI":
                        assert (
                            "py" in config.python_version  # type: ignore
                            and config.python_version == allowed.python_version
                        ), (
                            f"Invalid Python version specified: {config}.\nAllowed: {allowed}"
                        )
                        assert (
                            re.search(r"\d+\.\d+\.\d+", config.pytorch_version)  # type: ignore
                            and config.pytorch_version == allowed.pytorch_version
                        ), (
                            f"Invalid PyTorch version specified: {config}.\nAllowed: {allowed}"
                        )
                    is_valid = True
                    LOG.info(
                        f"The following release: {config} is permitted with: {allowed}."
                    )
                    device_set.add((config.device, config.version))
                    break

            assert is_valid, (
                f"No permitted combination found matching framework version and device: {config}."
            )

        assert len(self.releases) == len(device_set), (
            f"There are duplicate device/framework releases: {self.releases}."
        )


class DockerClient:
    @dataclasses.dataclass
    class ImageUriParts:
        aws_account_id: str
        url_repo: str
        url: str
        repo: str
        tag: str

    def __init__(self):
        self.client = docker.from_env()

    def build(
        self,
        image_uri: str,
        dockerfile_path: str,
        build_path: str = ".",
        target: str = "sagemaker",
    ):
        """Builds the Docker image.

        We are using a subprocess as opposed to the client as the client does not support buildx. There is another
        library that we can potentially use in lieu of docker-py for such support, but a further look is required to
        assess the ramifications of the switch. This might also not be necessary anyways since there is an ongoing
        discussion on not building the container from source like we are doing today.
        """
        max_jobs = os.getenv(EnvironmentVariable.DOCKER_MAX_JOBS.name, "4")
        command = [
            "docker",
            "buildx",
            "build",
            "--build-arg",
            f"MAX_JOBS={max_jobs}",
            "--file",
            dockerfile_path,
            "--target",
            target,
            "--platform",
            "linux/amd64",
            "--provenance",
            "false",
            "--tag",
            image_uri,
            "--load",
            build_path,
        ]

        # Logging the commands
        LOG.info(f"Going to run the following build command: {' '.join(command)}")
        process = subprocess.run(command, shell=False, text=True, capture_output=True)
        LOG.info(process.stdout)
        LOG.info(process.stderr)
        assert process.returncode == 0, f"Failed building {image_uri}."
        LOG.info(f"Completed building Docker image: {image_uri}.")

    def login(self, username: str, password: str, url: str):
        """Logs in to the specified registry."""
        LOG.info(f"Logging into url: {url}.")
        self.client.login(username=username, password=password, registry=url)

    def pull(self, image_uri: str):
        """Pulls the external Docker image locally."""
        LOG.info(f"Pulling image URI: {image_uri}.")
        parts = self.split_ecr_image_uri(image_uri)
        self.client.images.pull(parts.url_repo, tag=parts.tag)
        LOG.info(f"Pulled image URI: {image_uri}.")

    def push(self, image_uri: str):
        """Pushes the Docker image to its ECR repo."""
        LOG.info(f"Pushing image URI: {image_uri}.")
        parts = self.split_ecr_image_uri(image_uri)
        LOG.info(f"tags are {parts.tag}, url is {parts.url_repo}")
        streamed_output = self.client.images.push(
            parts.url_repo, tag=parts.tag, stream=True, decode=True
        )
        for text in streamed_output:
            LOG.info(text)
        LOG.info(f"Pushed image URI: {image_uri}.")

    def tag(self, source_uri: str, target_uri: str):
        """Tags a source image URI available locally to the repo and tag of the target URI."""
        LOG.info(f"Tagging {source_uri} to {target_uri}.")
        image = self.client.images.get(source_uri)
        target_image_uri_parts = self.split_ecr_image_uri(target_uri)
        image.tag(target_image_uri_parts.url_repo, tag=target_image_uri_parts.tag)

    def prune_all(self):
        """Removes all images."""
        LOG.info("Going to prune all images.")
        self.client.images.prune(filters={"dangling": False})

    @staticmethod
    def split_ecr_image_uri(image_uri: str) -> ImageUriParts:
        """Splits up the image URI into parts accessible directly through an aggregate object."""
        match = re.search(ECR_URI_REGEX, image_uri)
        assert match, (
            f"The following ECR image URI does not match regex '{ECR_URI_REGEX}': {image_uri}"
        )
        url, repo, tag = match.groups()
        aws_account_id = url.split(".")[0]
        url_repo = f"{url}/{repo}"
        return DockerClient.ImageUriParts(
            aws_account_id=aws_account_id,
            url_repo=url_repo,
            url=url,
            repo=repo,
            tag=tag,
        )


class Aws:
    def __init__(self, session: typing.Optional[boto3.Session] = None):
        self.session = session if session else boto3.Session()
        self.sts = self.session.client("sts")
        self.ecr = self.session.client("ecr")
        self.ssm = self.session.client("ssm")
        self.pipeline = self.session.client("codepipeline")

    def get_session_for_role(self, role_arn: str) -> boto3.Session:
        """Gets session with credentials of provided role."""
        LOG.info(f"Getting session for role: {role_arn}.")
        response = self.sts.assume_role(RoleArn=role_arn, RoleSessionName=SESSION_NAME)
        credentials = response["Credentials"]
        return boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )

    def get_ecr_credentials(self, image_uri: str) -> typing.Tuple[str, str]:
        """Gets the username and password for the given ECR image URI."""
        image_uri_parts = DockerClient.split_ecr_image_uri(image_uri)
        response = self.ecr.get_authorization_token(
            registryIds=[image_uri_parts.aws_account_id]
        )
        encoded_token = response["authorizationData"][0]["authorizationToken"]
        token_bytes = base64.b64decode(encoded_token)
        username, password = token_bytes.decode("utf-8").split(":")
        return username, password

    def does_ecr_image_exist(self, image_uri: str) -> bool:
        """Checks if the given image URI exists in the specified ECR repo."""
        result = True
        try:
            image_uri_parts = DockerClient.split_ecr_image_uri(image_uri)
            tag = image_uri_parts.tag
            image_ids = [
                {"imageDigest": tag}
                if ECR_TAG_DIGEST_PREFIX in tag
                else {"imageTag": tag}
            ]
            self.ecr.describe_images(
                registryId=image_uri_parts.aws_account_id,
                repositoryName=image_uri_parts.repo,
                imageIds=image_ids,
            )
        except self.ecr.exceptions.ImageNotFoundException:
            result = False

        LOG.info(f"Does image URI {image_uri} already exist? {result}.")
        return result

    def _get_ecr_scan_results(
        self, image_uri: str, max_pagination: int = 5
    ) -> typing.Tuple[str, List[Dict[str, str]]]:
        uri_parts = DockerClient.split_ecr_image_uri(image_uri)
        tag = uri_parts.tag
        image_id = (
            {"imageDigest": tag} if ECR_TAG_DIGEST_PREFIX in tag else {"imageTag": tag}
        )

        iteration = 0
        # Call the describe_image_scan_findings method with pagination
        response = self.ecr.describe_image_scan_findings(
            repositoryName=uri_parts.repo, imageId=image_id, maxResults=1000
        )
        status = response["imageScanStatus"]["status"]
        enhanced_findings = response["imageScanFindings"].get("enhancedFindings", [])

        # Iterate through the paginated results
        while iteration < max_pagination and "nextToken" in response:
            iteration += 1
            # Get the next page of results
            response = self.ecr.describe_image_scan_findings(
                repositoryName=uri_parts.repo,
                imageId=image_id,
                maxResults=1000,
                nextToken=response["nextToken"],
            )
            enhanced_findings.extend(
                response["imageScanFindings"].get("enhancedFindings", [])
            )

        if "nextToken" in response:
            LOG.warning(
                "There are more scan results not loaded from pagination, consider increase max count."
            )

        return status, enhanced_findings

    def is_ecr_image_scan_pending(self, image_uri: str) -> bool:
        """Checks if the specified image in ECR is still pending scanning."""
        result = True
        try:
            status, _ = self._get_ecr_scan_results(image_uri)
            result = status == "PENDING"
        except self.ecr.exceptions.ScanNotFoundException:
            pass

        return result

    def get_image_scan_findings(
        self, image_uri: str, severities: typing.Set[str], excluded_ids: typing.Set[str]
    ) -> typing.List[str]:
        """Gets all vulnerabilities of the provided image matching the specified severities."""
        results = []
        _, enhanced_findings = self._get_ecr_scan_results(image_uri)
        for finding in enhanced_findings:
            if (
                finding["severity"] in severities
                and finding["title"] not in excluded_ids
            ):
                results.append(finding["title"])
            else:
                LOG.info(
                    f"Excluding vulnerability '{finding['title']}' with severity: {finding['severity']}."
                )

        LOG.info(f"{image_uri} has the following filtered vulnerabilities: {results}.")
        return results

    def set_parameter(self, name: str, value: str):
        """Sets the SSM parameter."""
        self.ssm.put_parameter(Name=name, Value=value, Overwrite=True)
        LOG.info(f"Set parameter name: '{name}' to value: {value}.")

    def start_pipeline(self, name: str) -> str:
        """Starts the specified CodePipeline."""
        response = self.pipeline.start_pipeline_execution(name=name)
        execution_id = response["pipelineExecutionId"]
        LOG.info(f"Started pipeline: '{name}' with execution ID: '{execution_id}'.")
        return execution_id

    def get_pipeline_status(self, name: str, execution_id: str) -> str:
        """Gets the status of the specified execution of the given CodePipeline."""
        response = self.pipeline.get_pipeline_execution(
            pipelineName=name, pipelineExecutionId=execution_id
        )
        status = response["pipelineExecution"]["status"]
        result = PipelineStatus.UNSUCCESSFUL.name
        if status == "InProgress":
            result = PipelineStatus.IN_PROGRESS.name
        elif status == "Succeeded":
            result = PipelineStatus.SUCCESSFUL.name

        return result


class DlcPipeline:
    def __init__(self, aws: Aws, docker_client: DockerClient):
        self.aws = aws
        self.docker_client = docker_client
        self.dlc_aws, self.last_refresh_time = None, None
        self._refresh_credentials()

    def _refresh_credentials(self):
        """Refreshes assume-role credentials for DLC integrations as role chaining has a hard limit of 1 hour."""
        if (
            self.dlc_aws is None
            or time.time() - self.last_refresh_time  # type: ignore
            > DEFAULT_CRED_REFRESH_INTERVAL_IN_SECONDS
        ):
            LOG.info(
                f"Refreshing AWS credentials for DLC integrations. Last refresh at: {self.last_refresh_time}."
            )
            dlc_role_arn = os.getenv(EnvironmentVariable.DLC_ROLE_ARN.name)
            dlc_session = self.aws.get_session_for_role(dlc_role_arn)  # type: ignore
            self.dlc_aws = Aws(session=dlc_session)
            self.last_refresh_time = time.time()

    def stage_image(self, config: ReleaseConfigs.ReleaseConfig):
        """Pushes the local image associated with the given configs to the DLC staging repo."""
        staged_image_uri = config.get_image_uri_for_staging()
        dlc_uris = config.get_image_uris_for_dlc()
        username, password = self.dlc_aws.get_ecr_credentials(dlc_uris[0])  # type: ignore
        self.docker_client.login(username, password, dlc_uris[0])
        for dlc_uri in dlc_uris:
            self.docker_client.tag(staged_image_uri, dlc_uri)
            self.docker_client.push(dlc_uri)

    def set_parameters(self, config: ReleaseConfigs.ReleaseConfig):
        """Sets all configuration parameters for the given config for the release pipeline execution."""
        parameters = {}
        if config.device.lower() == Device.GPU.name.lower():
            parameters = {
                "/huggingface-pytorch-tgi/gpu/tgi-version": config.version,
                "/huggingface-pytorch-tgi/gpu/os-version": config.os_version,
                "/huggingface-pytorch-tgi/gpu/cuda-version": config.cuda_version,
                "/huggingface-pytorch-tgi/gpu/python-version": config.python_version,
                "/huggingface-pytorch-tgi/gpu/pytorch-version": config.pytorch_version,
            }
        elif config.device.lower() == Device.INF2.name.lower():
            parameters = {
                "/huggingface-pytorch-tgi/neuronx/tgi-optimum-version": config.version,
                "/huggingface-pytorch-tgi/neuronx/os-version": config.os_version,
                "/huggingface-pytorch-tgi/neuronx/python-version": config.python_version,
                "/huggingface-pytorch-tgi/neuronx/pytorch-version": config.pytorch_version,
            }

        assert parameters, (
            f"No parameter configurations associated with device: {config.device}"
        )
        for name, value in parameters.items():
            self.dlc_aws.set_parameter(name, value)  # type: ignore

    @staticmethod
    def get_pipeline_for_device(device: typing.Optional[str]):
        """Gets the DLC pipeline name for the given device."""
        pipeline = DLC_PIPELINE_NAME_BY_DEVICE.get(device.lower())  # type: ignore
        assert pipeline is not None, (
            f"No DLC pipeline name associated with device type: {device}."
        )
        return pipeline

    def start_pipeline(self, config: ReleaseConfigs.ReleaseConfig):
        """Starts the DLC pipeline associated with the given config."""
        if (
            os.getenv(
                EnvironmentVariable.DLC_ENABLE_PIPELINE_EXECUTION.name, ""
            ).lower()
            == "true"
        ):
            pipeline_name = self.get_pipeline_for_device(config.device)
            execution_id = self.dlc_aws.start_pipeline(pipeline_name)  # type: ignore
            LOG.info(
                f"Started pipeline '{pipeline_name}' with execution ID: {execution_id}"
            )
            if (
                os.getenv(
                    EnvironmentVariable.DLC_ENABLE_PIPELINE_STATUS_CHECK.name, ""
                ).lower()
                == "true"
            ):
                status = PipelineStatus.IN_PROGRESS.name
                while status == PipelineStatus.IN_PROGRESS.name:
                    time.sleep(DEFAULT_WAIT_INTERVAL_IN_SECONDS)
                    self._refresh_credentials()
                    status = self.dlc_aws.get_pipeline_status(  # type: ignore
                        pipeline_name, execution_id
                    )
                    LOG.info(
                        f"Pipeline: '{pipeline_name}' with execution: {execution_id} has status: {status}."
                    )

                assert status == PipelineStatus.SUCCESSFUL.name, (
                    f"Pipeline: '{pipeline_name}' with execution ID: {execution_id} was not successful."
                )

