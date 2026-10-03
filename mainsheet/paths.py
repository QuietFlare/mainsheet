"""Where Mainsheet keeps what it writes, and where it finds what it ships."""
import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
TEMPLATE = PACKAGE / "agent.yaml"
TAXONOMY = PACKAGE / "evals" / "taxonomy.yaml"


def home() -> Path:
    """The working folder: MAINSHEET_HOME when set, else the folder Mainsheet is run from."""
    return Path(os.environ.get("MAINSHEET_HOME") or Path.cwd()).resolve()


HOME = home()


def default_agent() -> Path:
    """agent.yaml in the working folder when there is one, else the example that ships with the package."""
    own = HOME / "agent.yaml"
    return own if own.exists() else TEMPLATE
