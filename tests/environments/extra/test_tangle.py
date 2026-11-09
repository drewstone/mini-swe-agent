import os

import pytest

from minisweagent.exceptions import Submitted

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not os.getenv("TANGLE_API_KEY"), reason="TANGLE_API_KEY not set"),
]


@pytest.fixture(scope="module")
def env():
    from minisweagent.environments.extra.tangle import TangleEnvironment

    env = TangleEnvironment(env={"MY_VAR": "from-config"}, forward_env=["TANGLE_TEST_FORWARDED"], timeout=30)
    yield env
    env.cleanup()


def test_tangle_execute(env, monkeypatch):
    """Commands run in the sandbox with merged output, exit codes, cwd and environment."""
    assert env.execute({"command": "echo out; echo err >&2"}) == {
        "output": "out\nerr\n",
        "returncode": 0,
        "exception_info": "",
    }
    assert env.execute({"command": "exit 3"})["returncode"] == 3
    assert env.execute({"command": "pwd"})["output"].strip() == "/home/agent"
    assert env.execute({"command": "pwd"}, cwd="/tmp")["output"].strip() == "/tmp"
    assert env.execute({"command": "pwd"}, cwd="/nonexistent")["returncode"] != 0
    monkeypatch.setenv("TANGLE_TEST_FORWARDED", "from-host")
    assert env.execute({"command": "echo $MY_VAR $TANGLE_TEST_FORWARDED"})["output"].strip() == "from-config from-host"


def test_tangle_files_persist_between_commands(env):
    """Files written by one command are visible to the next, as in an agent run."""
    assert env.execute({"command": "printf 'a\\nb\\n' > notes.txt"})["returncode"] == 0
    assert env.execute({"command": "wc -l < notes.txt"})["output"].strip() == "2"


def test_tangle_timeout(env):
    """A command that exceeds its timeout returns an error instead of hanging."""
    result = env.execute({"command": "sleep 10"}, timeout=2)
    assert result["returncode"] == -1
    assert result["exception_info"].startswith("An error occurred while executing the command:")


def test_tangle_submitted(env):
    """The submission marker ends the run with the rest of the output as the submission."""
    with pytest.raises(Submitted) as exc_info:
        env.execute({"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; echo diff --git a/f b/f"})
    assert exc_info.value.messages[0]["extra"]["submission"] == "diff --git a/f b/f\n"


def test_tangle_image_and_cleanup():
    """A sandbox starts from the given image, keeps its root read-only, and is deleted on cleanup."""
    from tangle_sandbox import Sandbox

    from minisweagent.environments.extra.tangle import TangleEnvironment

    env = TangleEnvironment(image="python:3.11-slim")
    sandbox_id = env.sandbox.id
    assert env.execute({"command": "python --version"})["output"].startswith("Python 3.11")
    assert env.execute({"command": "pwd"})["output"].strip() == "/home/agent"
    assert env.execute({"command": "touch /tmp/x && touch /home/agent/x && ! touch /usr/x"})["returncode"] == 0
    assert env.serialize()["info"]["config"]["environment"]["image"] == "python:3.11-slim"
    env.cleanup()
    assert env.sandbox is None
    with Sandbox(api_key=os.environ["TANGLE_API_KEY"], base_url=env.config.base_url) as client:
        assert client.get(sandbox_id).status.value == "deleted"
