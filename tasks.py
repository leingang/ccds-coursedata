from typing import Annotated, Optional
import os

import keyring
from loguru import logger
import typer

try:
    from edubag.gradescope.client import sync_roster
    EDUBAG_AVAILABLE = True
except ImportError:
    EDUBAG_AVAILABLE = False

from coursedata.config import GRADESCOPE_CONFIG

app = typer.Typer()


@app.command("sync-gradescope-rosters")
def sync_gradescope_rosters(
    courses: Annotated[
        Optional[list[str]],
        typer.Option(
            help="Overrides the course IDs from pyproject.toml; if omitted, uses tool.coursedata.gradescope.courses",
        ),
    ] = None,
    username: Annotated[
        Optional[str],
        typer.Option(help="Gradescope username; defaults to $GRADESCOPE_USERNAME from environment"),
    ] = None,
    keyring_service: Annotated[
        str,
        typer.Option(help="Keyring service name for Gradescope password storage"),
    ] = "gradescope.com",
):
    """Sync Gradescope rosters for configured courses.

    Reads course IDs from [tool.coursedata.gradescope] in pyproject.toml unless overridden.
    Auth uses $GRADESCOPE_USERNAME and password from the specified keyring service.
    """
    if not EDUBAG_AVAILABLE:
        logger.error("edubag module is not available. Cannot sync Gradescope rosters.")
        raise typer.Exit(code=1)

    configured_courses = GRADESCOPE_CONFIG.get("courses", [])
    course_ids = courses or configured_courses
    if not course_ids:
        logger.error("No Gradescope courses configured. Set tool.coursedata.gradescope.courses in pyproject.toml or pass --courses.")
        raise typer.Exit(code=1)

    # Resolve credentials (do not pass to sync_roster; let edubag handle)
    if not username:
        username = os.getenv("GRADESCOPE_USERNAME")
    if not username:
        logger.warning(
            "GRADESCOPE_USERNAME not found in environment. Set it in .env or pass --username."
        )
    else:
        # Ensure the environment variable is set for any downstream use
        os.environ["GRADESCOPE_USERNAME"] = username
        # Check for password presence in keyring and guide setup if missing
        pw = keyring.get_password(keyring_service, username)
        if not pw:
            logger.warning(
                f"Password for '{username}' not found in Keychain (service '{keyring_service}'). Add it via:"
            )
            logger.warning(
                f"security add-generic-password -s {keyring_service} -a {username} -w YOUR_PASSWORD"
            )

    # Iterate and sync
    success = 0
    for cid in course_ids:
        try:
            logger.info(f"Syncing Gradescope roster for course {cid}...")
            # edubag handles auth internally via env/keyring; no kwargs
            sync_roster(cid)
            logger.success(f"Roster synced for course {cid}")
            success += 1
        except Exception as e:
            logger.error(f"Failed to sync roster for course {cid}: {e}")

    if success == 0:
        raise typer.Exit(code=1)


@app.command()
def daily():
    """Run all non-data local tasks for the day.

    Currently runs Gradescope roster sync; add additional tasks here as needed.
    """
    # Uses defaults from configuration and environment
    sync_gradescope_rosters()


if __name__ == "__main__":
    app()
