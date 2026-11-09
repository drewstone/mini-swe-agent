import logging
import os
import platform
import shlex
import uuid
from typing import Any

from pydantic import BaseModel
from tangle_sandbox import ExecOptions, Sandbox, SandboxResources

from minisweagent.exceptions import Submitted
from minisweagent.utils.serialize import recursive_merge


class TangleEnvironmentConfig(BaseModel):
    image: str | None = None
    """Container image to run in. `None` uses Tangle's default environment (Ubuntu with Python, Node.js and git)."""
    cwd: str = "/home/agent"
    """Working directory in which to execute commands. The image's root filesystem is read-only;
    `/home/agent` and `/tmp` are writable."""
    env: dict[str, str] = {}
    """Environment variables to set for every command."""
    forward_env: list[str] = []
    """Environment variables to forward to the sandbox.
    Variables are only forwarded if they are set in the host environment.
    In case of conflict with `env`, the `env` variables take precedence.
    """
    timeout: int = 60
    """Timeout in seconds for executing each command."""
    interpreter: list[str] = ["bash", "-lc"]
    """Interpreter to execute commands with. The command is appended as its last argument."""
    cpu_cores: int | None = None
    """vCPUs for the sandbox. Tangle's default when unset."""
    memory_mb: int | None = None
    """Memory for the sandbox in MB. Tangle's default when unset."""
    disk_gb: int | None = None
    """Disk for the sandbox in GB. Tangle's default when unset."""
    max_lifetime_seconds: int = 7200
    """Tangle deletes the sandbox after this many seconds, even if `cleanup` never runs."""
    base_url: str = os.getenv("TANGLE_BASE_URL", "https://sandbox.tangle.tools")
    """Tangle Sandbox API URL. The API key is read from `TANGLE_API_KEY`."""


class TangleEnvironment:
    def __init__(
        self,
        *,
        config_class: type = TangleEnvironmentConfig,
        logger: logging.Logger | None = None,
        **kwargs,
    ):
        """Executes bash commands in a [Tangle](https://tangle.tools) sandbox using the
        [tangle-sandbox](https://pypi.org/project/tangle-sandbox/) SDK.
        See `TangleEnvironmentConfig` for keyword arguments.
        """
        self.logger = logger or logging.getLogger("minisweagent.environment")
        self.config = config_class(**kwargs)
        self.sandbox = None
        self.client = Sandbox(api_key=os.environ["TANGLE_API_KEY"], base_url=self.config.base_url)
        resources = {"cpu_cores": self.config.cpu_cores, "memory_mb": self.config.memory_mb, "disk_gb": self.config.disk_gb}
        self.sandbox = self.client.create(
            name=f"minisweagent-{uuid.uuid4().hex[:8]}",
            environment=self.config.image,
            resources=SandboxResources(**resources) if any(v is not None for v in resources.values()) else None,
            max_lifetime_seconds=self.config.max_lifetime_seconds,
            metadata={"created_by": "mini-swe-agent"},
        )
        self.sandbox.wait_for("running")
        self.logger.info(f"Started Tangle sandbox {self.sandbox.id}")

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return recursive_merge(self.config.model_dump(), platform.uname()._asdict(), kwargs)

    def serialize(self) -> dict:
        return {
            "info": {
                "config": {
                    "environment": self.config.model_dump(mode="json"),
                    "environment_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                }
            }
        }

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        """Execute a command in the sandbox and return the raw output."""
        command = action.get("command", "")
        env = {k: v for k in self.config.forward_env if (v := os.getenv(k)) is not None}
        env.update(self.config.env)
        try:
            result = self.sandbox.exec(
                shlex.join([*self.config.interpreter, command]),
                ExecOptions(
                    cwd=cwd or self.config.cwd,
                    env=env or None,
                    timeout_ms=(timeout or self.config.timeout) * 1000,
                ),
            )
            output = {"output": result.stdout + result.stderr, "returncode": result.exit_code, "exception_info": ""}
        except Exception as e:
            output = {
                "output": "",
                "returncode": -1,
                "exception_info": f"An error occurred while executing the command: {e}",
                "extra": {"exception_type": type(e).__name__, "exception": str(e)},
            }
        self._check_finished(output)
        return output

    def _check_finished(self, output: dict):
        """Raises Submitted if the output indicates task completion."""
        lines = output.get("output", "").lstrip().splitlines(keepends=True)
        if lines and lines[0].strip() == "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" and output["returncode"] == 0:
            submission = "".join(lines[1:])
            raise Submitted(
                {
                    "role": "exit",
                    "content": submission,
                    "extra": {"exit_status": "Submitted", "submission": submission},
                }
            )

    def cleanup(self):
        """Delete the sandbox."""
        sandbox, self.sandbox = getattr(self, "sandbox", None), None
        if sandbox is not None:
            sandbox.delete()

    def __del__(self):
        self.cleanup()
