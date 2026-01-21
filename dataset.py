from datetime import date
from pathlib import Path
import os
import shutil
from typing import Annotated, Optional

import keyring

try:
    from edubag.albert import xls2csv
    from edubag.albert.client import fetch_and_save_rosters, fetch_class_details
    from edubag.gmail import filter_from_roster_command

    EDUBAG_AVAILABLE = True
except ImportError:
    EDUBAG_AVAILABLE = False

from loguru import logger
from tqdm import tqdm
import typer

from coursedata.config import (
    COURSE_NAME,
    INTERIM_DATA_DIR,
    PROCESSED_DATA_DIR,
    RAW_DATA_DIR,
    REPORTS_DIR,
    TERM_NAME,
)
from coursedata.enrollment import (
    find_roster_files,
    generate_enrollment_report,
    generate_enrollment_roster,
)

d8 = date.today().isoformat()


app = typer.Typer()


@app.command()
def daily():
    """Run all daily data processing steps."""
    albert_rosters()
    albert_class_details()
    save_gmail_filters()
    enrollment_rosters()
    enrollment_reports()


@app.command()
def albert_rosters(
    output_dir: Annotated[
        Path | None, typer.Option(help="Output directory for the rosters file")
    ] = None,
    convert_to_csv: Annotated[
        bool, typer.Option(help="Convert the fetched Excel files to CSV format")
    ] = True,
    csv_output_dir: Annotated[
        Path | None, typer.Option(help="Output directory for CSV files")
    ] = None,
    clean: Annotated[
        bool,
        typer.Option(
            help="Remove existing files in output directories before fetching"
        ),
    ] = False,
):
    """
    Fetch all rosters for the specified course and term, and save to output_dir.
    """
    if not EDUBAG_AVAILABLE:
        logger.error("edubag module is not available. Cannot fetch rosters.")
        raise typer.Exit(code=1)

    if output_dir is None:
        output_dir = RAW_DATA_DIR / "albert" / "rosters" / d8

    # Determine csv_output_dir early if needed
    if csv_output_dir is None:
        csv_output_dir = INTERIM_DATA_DIR / "albert" / "rosters" / d8

    # Clean output directories if requested
    if clean:
        if output_dir.exists():
            logger.info(f"Cleaning output directory: {output_dir}")
            shutil.rmtree(output_dir)
        if convert_to_csv and csv_output_dir is not None and csv_output_dir.exists():
            logger.info(f"Cleaning CSV output directory: {csv_output_dir}")
            shutil.rmtree(csv_output_dir)

    logger.info(
        f"Fetching rosters for course '{COURSE_NAME}' in term '{TERM_NAME}' to '{output_dir}'"
    )

    # Get credentials from environment and keychain
    username = os.getenv("SSO_USERNAME")
    if not username:
        logger.warning(
            "SSO_USERNAME not found in environment variables. Set it in your .env file."
        )
        username = None

    password = None
    if username:
        password = keyring.get_password("nyu-sso", username)
        if not password:
            logger.warning(
                f"Password for user '{username}' not found in macOS Keychain. Store it with: security add-generic-password -s nyu-sso -a {username} -w YOUR_PASSWORD"
            )
            password = None

    xls_path_list = fetch_and_save_rosters(
        COURSE_NAME, TERM_NAME, output_dir, username=username, password=password
    )
    logger.success("Rosters fetched successfully.")
    if convert_to_csv:
        csv_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Converting Excel files to CSV in '{csv_output_dir}'")
        for xls_path in tqdm(xls_path_list, desc="Converting to CSV"):
            xls2csv([xls_path], csv_output_dir)
        logger.success("Conversion to CSV complete.")


@app.command()
def albert_class_details(
    output: Annotated[
        Path | None, typer.Option(help="Output path for the class details file")
    ] = None,
):
    """
    Fetch all class details for the specified course and term, and save to output.
    """
    if not EDUBAG_AVAILABLE:
        logger.error("edubag module is not available. Cannot fetch class details.")
        raise typer.Exit(code=1)

    if output is None:
        output = PROCESSED_DATA_DIR / "albert" / "class_details" / d8 / "class_details.json"

    logger.info(
        f"Fetching class details for course '{COURSE_NAME}' in term '{TERM_NAME}' to '{output}'"
    )

    # Get credentials from environment and keychain
    username = os.getenv("SSO_USERNAME")
    if not username:
        logger.warning(
            "SSO_USERNAME not found in environment variables. Set it in your .env file."
        )
        username = None

    password = None
    if username:
        password = keyring.get_password("nyu-sso", username)
        if not password:
            logger.warning(
                f"Password for user '{username}' not found in macOS Keychain. Store it with: security add-generic-password -s nyu-sso -a {username} -w YOUR_PASSWORD"
            )
            password = None

    fetch_class_details(COURSE_NAME, TERM_NAME, output=output, username=username, password=password)
    logger.success("Class details fetched successfully.")



@app.command()
def enrollment_rosters(
    rosters_dir: Annotated[
        Path | None,
        typer.Option(help="Directory containing dated roster subdirectories"),
    ] = None,
    output_dir: Annotated[
        Path | None, typer.Option(help="Output directory for enrollment rosters")
    ] = None,
):
    """
    Generate enrollment rosters for all sections.
    """
    if rosters_dir is None:
        rosters_dir = INTERIM_DATA_DIR / "albert" / "rosters"

    if output_dir is None:
        output_dir = PROCESSED_DATA_DIR / "enrollment"

    logger.info(f"Finding roster files in {rosters_dir}")
    sections = find_roster_files(rosters_dir)

    if not sections:
        logger.warning(f"No roster files found in {rosters_dir}")
        return

    logger.info(f"Found {len(sections)} sections")

    for section_name, roster_files in sections.items():
        logger.info(f"Processing section: {section_name}")
        generate_enrollment_roster(section_name, roster_files, output_dir)

    logger.success("Enrollment roster generation complete")


@app.command()
def enrollment_reports(
    rosters_dir: Annotated[
        Path | None,
        typer.Option(help="Directory containing dated roster subdirectories"),
    ] = None,
    output_dir: Annotated[
        Path | None, typer.Option(help="Output directory for enrollment reports")
    ] = None,
):
    """
    Generate enrollment reports for all sections.
    """
    if rosters_dir is None:
        rosters_dir = INTERIM_DATA_DIR / "albert" / "rosters"

    if output_dir is None:
        output_dir = REPORTS_DIR / "enrollment"

    logger.info(f"Finding roster files in {rosters_dir}")
    sections = find_roster_files(rosters_dir)

    if not sections:
        logger.warning(f"No roster files found in {rosters_dir}")
        return

    logger.info(f"Found {len(sections)} sections")

    for section_name, roster_files in sections.items():
        logger.info(f"Processing section: {section_name}")
        generate_enrollment_report(section_name, roster_files, output_dir)

    logger.success("Enrollment report generation complete")


@app.command("gmail-filters")
def save_gmail_filters(
    roster_paths: Annotated[
        Optional[list[Path]],
        typer.Option(
            help="One or more Albert roster XLS files. If not set, the most recently downloaded rosters will be used."
        ),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option(
            help="Path to save the Gmail filter XML file. If not set, save to processed data directory."
        ),
    ] = None,
):
    """Generate Gmail filters XML from a Gradescope roster CSV file."""
    if not EDUBAG_AVAILABLE:
        logger.error("edubag module is not available. Cannot generate Gmail filters.")
        raise typer.Exit(code=1)

    if not roster_paths:
        logger.info("No roster files provided. Using most recently downloaded rosters.")
        rosters_base_dir = RAW_DATA_DIR / "albert" / "rosters"

        # Find all date subdirectories and get the most recent one
        date_dirs = sorted([d for d in rosters_base_dir.iterdir() if d.is_dir()])
        if not date_dirs:
            logger.error(f"No roster directories found in {rosters_base_dir}")
            raise typer.Exit(code=1)

        latest_date_dir = date_dirs[-1]
        logger.info(f"Using rosters from {latest_date_dir.name}")

        # Find all .XLS files in the latest date directory
        roster_paths = sorted(latest_date_dir.glob("*.XLS"))

        if not roster_paths:
            logger.error(f"No .XLS files found in {latest_date_dir}")
            raise typer.Exit(code=1)

    if not output:
        output = PROCESSED_DATA_DIR / "gmail" / "gmail_filters.xml"

    filter_from_roster_command(roster_paths, output=output)
    logger.success(f"Gmail filters saved to {output}")


if __name__ == "__main__":
    app()
