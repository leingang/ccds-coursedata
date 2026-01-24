"""
Generate lecture cover PDFs from a CSV schedule file.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import pandas as pd
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
import re
from datetime import datetime
import shutil

from pathlib import Path

from loguru import logger
from tqdm import tqdm
import typer
import click
from typing import Optional, Annotated, Generator

from coursedata.config import (
    PROJ_ROOT,
    REPORTS_DIR,
    LECTURE_COVERS_CONFIG,
    TERM_NAME,
)


app = typer.Typer()


DEFAULT_SOURCE_TYPE = "mpl"


@dataclass
class LectureCoversSettings:
    source: Path
    source_type: str
    sections: list[str] | None
    output: Path


class LectureScheduleParser(ABC):
    def __init__(self, csv_path: Path):
        self.csv_path = csv_path

    @abstractmethod
    def parse(self) -> Generator[tuple[datetime, int, str], None, None]:
        """Yield tuples of (date, number, topic)."""
        raise NotImplementedError


class MPLLectureScheduleParser(LectureScheduleParser):
    def parse(self) -> Generator[tuple[datetime, int, str], None, None]:
        def to_date(date_str: str) -> datetime | None:
            date_str = date_str.strip().replace("\xa0", " ")
            try:
                return datetime.strptime(date_str, "%m/%d/%Y")
            except ValueError as e:
                logger.debug(f"Error parsing date '{date_str}': {e}")
                return None

        df = pd.read_csv(self.csv_path, header=0, dtype=str, converters={"Date": to_date})
        df.dropna(subset=["Date", "Topic", "Type"], inplace=True)
        df = df[df["Type"].str.lower() == "lecture"]
        for lecture_number, row in enumerate(df.iterrows(), start=1):
            lecture_date = datetime.fromisoformat(row[1]["Date"])
            lecture_topic = row[1]["Topic"].strip()
            if pd.isna(lecture_date) or lecture_topic == "" or lecture_number is None:
                logger.debug(f"Skipping row due to missing data: {row}")
                continue
            yield (lecture_date, lecture_number, lecture_topic)


class JuliusLectureScheduleParser(LectureScheduleParser):
    def parse(self) -> Generator[tuple[datetime, int, str], None, None]:
        def to_date(date_str: str) -> datetime | None:
            # Extract year from TERM_NAME (e.g., "Spring 2026" -> 2026)
            year_str = TERM_NAME.split()[-1]
            date_str = date_str.strip().replace("\xa0", " ")
            try:
                return datetime.strptime(date_str + f", {year_str}", "%B %d, %Y").replace(
                    hour=8, minute=0, second=0, microsecond=0
                )
            except ValueError as e:
                logger.debug(f"Error parsing date '{date_str}': {e}")
                return None

        df = pd.read_csv(self.csv_path, header=2, dtype=str, converters={"Date": to_date})
        df.dropna(subset=["Date", "Topic", "Class #"], inplace=True)
        for _, row in df.iterrows():
            lecture_date = datetime.fromisoformat(row["Date"])
            lecture_topic = row["Topic"].strip()
            lecture_number = int(row["Class #"].strip())
            if pd.isna(lecture_date) or lecture_topic == "" or lecture_number is None:
                logger.debug(f"Skipping row due to missing data: {row}")
                continue
            yield (lecture_date, lecture_number, lecture_topic)


def _resolve_path(path: Path) -> Path:
    resolved = path if path.is_absolute() else PROJ_ROOT / path
    return resolved.resolve()


# Map of parser types to parser classes
PARSER_MAP: dict[str, type[LectureScheduleParser]] = {
    "mpl": MPLLectureScheduleParser,
    "julius": JuliusLectureScheduleParser,
}


def load_lecture_covers_settings(
    source: Optional[Path],
    source_type: Optional[str],
    sections: Optional[list[str]],
    output: Optional[Path],
) -> LectureCoversSettings:
    config_data = LECTURE_COVERS_CONFIG

    resolved_source = source or config_data.get("source")
    if resolved_source is None:
        raise ValueError("A source CSV path is required (pyproject.toml or CLI --source).")
    source_path = _resolve_path(Path(resolved_source))
    if not source_path.exists():
        raise FileNotFoundError(f"Could not find schedule CSV at {source_path}")

    # Determine source_type - required parameter
    resolved_source_type = source_type or config_data.get("source_type")
    if not resolved_source_type:
        available_types = ", ".join(f"'{t}'" for t in PARSER_MAP.keys())
        raise ValueError(
            f"source_type is required. Specify it via --source-type option or in pyproject.toml "
            f"[tool.coursedata.lecture_covers] section. Options: {available_types}."
        )
    resolved_source_type = resolved_source_type.lower()
    
    resolved_sections = sections or config_data.get("sections")
    if resolved_sections is not None:
        resolved_sections = [str(section) for section in resolved_sections]

    resolved_output = output or config_data.get("output")
    if resolved_output is None:
        resolved_output = REPORTS_DIR / "covers"
    resolved_output = _resolve_path(Path(resolved_output))

    return LectureCoversSettings(
        source=source_path,
        source_type=resolved_source_type,
        sections=resolved_sections,
        output=resolved_output,
    )


def get_parser(source_type: str, csv_path: Path) -> LectureScheduleParser:
    try:
        parser_cls = PARSER_MAP[source_type]
    except KeyError as exc:
        available_types = ", ".join(f"'{t}'" for t in PARSER_MAP.keys())
        raise ValueError(
            f"Unsupported source_type '{source_type}'. Choose from: {available_types}."
        ) from exc
    return parser_cls(csv_path)


def get_pdf_filename(
    date: datetime, lecnum: int, topic: str, section: str | None = None
) -> str:
    """Generate a sanitized filename for the lecture PDF."""

    def sanitize_filename(text: str) -> str:
        """Sanitize text to be safe for filenames. Spaces are OK."""
        text = (
            text.strip()
            .replace("\xa0", " ")
            .replace(", ", " ")
            .replace(": ", " ")
            .replace("(", "")
            .replace(")", "")
        )
        return re.sub(r"[^A-Za-z0-9\-§ ]+", "_", text)

    iso_date = date.strftime("%Y-%m-%d")
    lecnum_fmt = f"Lec{lecnum:02d}"
    sanitized_topic = sanitize_filename(topic)
    if section is not None:
        filename = f"{iso_date} {section} {lecnum_fmt} {sanitized_topic}.pdf"
    else:
        filename = f"{iso_date} {lecnum_fmt} {sanitized_topic}.pdf"
    return filename


def get_lectures_from_mpl_csv(
    csv_path: Path,
) -> Generator[tuple[datetime, int, str], None, None]:
    """Wrapper to retain the previous functional interface."""

    yield from MPLLectureScheduleParser(csv_path).parse()


def get_lectures_from_julius_csv(
    csv_path: Path,
) -> Generator[tuple[datetime, int, str], None, None]:
    """Wrapper to retain the previous functional interface."""

    yield from JuliusLectureScheduleParser(csv_path).parse()


def make_pdf(date: datetime, lecnum: int, topic: str, output_path: Path) -> Path:
    """Generate a single lecture cover PDF."""
    # Register a font with broad Unicode support

    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))

    styles = getSampleStyleSheet()
    styleN = styles["Normal"]
    styleH = styles["Heading1"]

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # PDF size: 160mm × 90mm
    # ReportLab expects a filename or file-like object; convert Path to str
    doc = SimpleDocTemplate(str(output_path), pagesize=(160 * mm, 90 * mm))
    elements = []
    elements.append(Paragraph(f"Lecture {lecnum}: {topic}", styleH))
    elements.append(Spacer(1, 12))
    formatted_date = date.strftime("%B %-d, %Y")
    elements.append(Paragraph(f"Date: {formatted_date}", styleN))
    doc.build(elements)
    logger.info(f"Generated PDF: {output_path}")
    return output_path


@app.command()
def make_lecture_covers(
    source: Annotated[
        Optional[Path],
        typer.Argument(help="Path to the schedule CSV file. Defaults to pyproject.toml config."),
    ] = None,
    source_type: Annotated[
        Optional[str],
        typer.Option(
            help="Parser to use for input CSV file.",
            click_type=click.Choice(list(PARSER_MAP.keys()), case_sensitive=False),
            show_default=False,
        ),
    ] = None,
    sections: Annotated[
        list[str] | None, typer.Option(help="Sections to generate covers for")
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            help="Output directory. Defaults to pyproject.toml config or reports directory.",
        ),
    ] = None,
):
    """
    Generate lecture cover PDFs from a CSV file into an output directory.
    """
    settings = load_lecture_covers_settings(
        source=source,
        source_type=source_type,
        sections=sections,
        output=output,
    )
    parser = get_parser(settings.source_type, settings.source)

    pdf_output_dir = settings.output
    if pdf_output_dir.exists():
        if pdf_output_dir.is_dir():
            shutil.rmtree(pdf_output_dir)
        else:
            pdf_output_dir.unlink()
    pdf_output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = []
    for lecture_date, lecture_number, lecture_topic in tqdm(
        parser.parse(),
        desc="Generating lecture PDFs",
    ):
        if settings.sections is not None:
            for section in settings.sections:
                pdf_filename = get_pdf_filename(
                    lecture_date, lecture_number, lecture_topic, section=section
                )
                output_path = pdf_output_dir / pdf_filename
                pdf_file = make_pdf(
                    lecture_date, lecture_number, lecture_topic, output_path
                )
                pdf_files.append(pdf_file)
        else:
            pdf_filename = get_pdf_filename(
                lecture_date, lecture_number, lecture_topic
            )
            output_path = pdf_output_dir / pdf_filename
            pdf_file = make_pdf(
                lecture_date, lecture_number, lecture_topic, output_path
            )
            pdf_files.append(pdf_file)

    logger.info(f"PDFs written to: {settings.output}")
    logger.info(f"Generated {len(pdf_files)} lecture PDFs.")


if __name__ == "__main__":
    app()
