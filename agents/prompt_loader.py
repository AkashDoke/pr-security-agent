import os

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")


def load_prompt(filename: str) -> str:
    """Load a prompt file by name (e.g. 'security_system.md'), resolved
    relative to this project's prompts/ dir — works no matter what the
    current working directory is (important for test_local.py and for
    Actions runners, whose cwd is the checked-out target repo, not this
    package)."""
    with open(os.path.join(_PROMPTS_DIR, filename)) as f:
        return f.read()
