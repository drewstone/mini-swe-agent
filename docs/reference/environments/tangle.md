# Tangle

!!! note "Tangle Environment class"

    - [Read on GitHub](https://github.com/swe-agent/mini-swe-agent/blob/main/src/minisweagent/environments/extra/tangle.py)
    - Requires a [Tangle](https://tangle.tools) API key

    ??? note "Full source code"

        ```python
        --8<-- "src/minisweagent/environments/extra/tangle.py"
        ```

::: minisweagent.environments.extra.tangle

This environment executes commands in [Tangle](https://tangle.tools) sandboxes using the [tangle-sandbox](https://pypi.org/project/tangle-sandbox/) SDK.
Each environment creates one sandbox and deletes it on cleanup.

## Setup

1. Install the dependencies:
   ```bash
   pip install "mini-swe-agent[tangle]"
   ```

2. Set your API key:
   ```bash
   export TANGLE_API_KEY="your-tangle-api-key"
   ```

## Usage

Run mini-swe-agent in a Tangle sandbox:
```bash
mini --environment-class tangle
```

Use a container image instead of Tangle's default environment:
```bash
mini -c mini.yaml -c environment.environment_class=tangle -c environment.image=python:3.12
```

The image's root filesystem is read-only. Commands run in `/home/agent` by default, and `/home/agent` and `/tmp` are writable.

{% include-markdown "../../_footer.md" %}
