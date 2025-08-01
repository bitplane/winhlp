#!/usr/bin/env python3
"""
Extract HLP files from ISO collection.

This script processes ISO files from ~/src/rip/5.sip/, extracts them,
and copies all HLP files to ~/src/textual/windows-help/ with organized structure.
"""

import sys
import shutil
import subprocess
import tempfile
from pathlib import Path
import argparse
import logging
from typing import List, Tuple


def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")


def find_hlp_candidates(rip_dir: Path) -> List[Tuple[str, Path]]:
    """
    Find all directories with tree.txt files containing .hlp references.

    Returns:
        List of (directory_name, directory_path) tuples
    """
    candidates = []

    for item in rip_dir.iterdir():
        if not item.is_dir():
            continue

        tree_file = item / "tree.txt"
        if not tree_file.exists():
            continue

        try:
            with open(tree_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().lower()
                if ".hlp" in content:
                    candidates.append((item.name, item))
                    logging.debug(f"Found HLP candidate: {item.name}")
        except Exception as e:
            logging.warning(f"Could not read {tree_file}: {e}")

    return candidates


def find_iso_file(directory: Path) -> Path:
    """Find the ISO file (*.iso.xz) in the given directory."""
    iso_files = list(directory.glob("*.iso.xz"))
    if not iso_files:
        raise FileNotFoundError(f"No *.iso.xz file found in {directory}")
    if len(iso_files) > 1:
        logging.warning(f"Multiple ISO files found in {directory}, using first: {iso_files[0]}")
    return iso_files[0]


def extract_iso(iso_path: Path, extract_dir: Path) -> None:
    """Extract ISO file to the specified directory."""
    logging.info(f"  Decompressing {iso_path.name}...")

    # Decompress XZ file
    decompressed_iso = extract_dir / iso_path.stem  # Remove .xz extension
    try:
        subprocess.run(
            ["xz", "-d", "-c", str(iso_path)], stdout=open(decompressed_iso, "wb"), check=True, stderr=subprocess.PIPE
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to decompress {iso_path}: {e.stderr.decode()}")

    logging.info("  Extracting ISO contents...")

    # Extract ISO contents
    try:
        subprocess.run(
            ["7z", "x", "-y", str(decompressed_iso), f"-o{extract_dir}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to extract ISO {decompressed_iso}: {e.stderr.decode()}")

    # Remove the decompressed ISO file to save space
    decompressed_iso.unlink()


def find_hlp_files(directory: Path) -> List[Path]:
    """Find all HLP files in directory recursively (case-insensitive)."""
    hlp_files = []

    try:
        # Use find command for case-insensitive search
        result = subprocess.run(["find", str(directory), "-iname", "*.hlp"], capture_output=True, text=True, check=True)

        for line in result.stdout.strip().split("\n"):
            if line:
                hlp_files.append(Path(line))

    except subprocess.CalledProcessError as e:
        logging.error(f"Error finding HLP files in {directory}: {e}")

    return hlp_files


def copy_hlp_file(source: Path, target_base: Path, iso_name: str, extract_dir: Path) -> bool:
    """
    Copy HLP file to target directory with preserved path structure.

    Args:
        source: Source HLP file path
        target_base: Base target directory (~/src/textual/windows-help/)
        iso_name: Name of the ISO (for organizing)
        extract_dir: Temporary extraction directory

    Returns:
        True if file was copied, False if skipped
    """
    try:
        # Calculate relative path from extraction directory
        rel_path = source.relative_to(extract_dir)

        # Create target path: target_base/iso_name/preserved/path/file.hlp
        target_path = target_base / iso_name / rel_path

        # Skip if target already exists
        if target_path.exists():
            logging.debug(f"    Skipping existing: {target_path}")
            return False

        # Create target directory
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(source, target_path)
        logging.debug(f"    Copied: {rel_path} -> {target_path}")
        return True

    except Exception as e:
        logging.error(f"    Failed to copy {source}: {e}")
        return False


def process_iso(iso_info: Tuple[str, Path], target_base: Path, dry_run: bool = False) -> Tuple[int, int]:
    """
    Process a single ISO file and extract HLP files.

    Returns:
        Tuple of (files_found, files_copied)
    """
    iso_name, iso_dir = iso_info

    logging.info(f"Processing: {iso_name}")

    if dry_run:
        logging.info("  DRY RUN - would process this ISO")
        return (0, 0)

    try:
        # Find ISO file
        iso_path = find_iso_file(iso_dir)

        # Create temporary extraction directory
        with tempfile.TemporaryDirectory(dir=Path.home() / "src/textual/windows-help/tmp") as temp_dir:
            extract_dir = Path(temp_dir)

            # Extract ISO
            extract_iso(iso_path, extract_dir)

            # Find HLP files
            hlp_files = find_hlp_files(extract_dir)
            files_found = len(hlp_files)

            if files_found == 0:
                logging.info("  No HLP files found")
                return (0, 0)

            logging.info(f"  Found {files_found} HLP files")

            # Copy HLP files
            files_copied = 0
            for hlp_file in hlp_files:
                if copy_hlp_file(hlp_file, target_base, iso_name, extract_dir):
                    files_copied += 1

            logging.info(f"  Copied {files_copied} new files")
            return (files_found, files_copied)

    except Exception as e:
        logging.error(f"  Failed to process {iso_name}: {e}")
        return (0, 0)


def main():
    parser = argparse.ArgumentParser(description="Extract HLP files from ISO collection")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without actually doing it")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--limit", type=int, help="Limit number of ISOs to process (for testing)")
    args = parser.parse_args()

    setup_logging(args.verbose)

    # Set up directories
    rip_dir = Path.home() / "src/rip/5.sip"
    target_base = Path.home() / "src/textual/windows-help"

    if not rip_dir.exists():
        logging.error(f"Source directory does not exist: {rip_dir}")
        sys.exit(1)

    target_base.mkdir(exist_ok=True)

    # Ensure tmp directory exists
    tmp_dir = target_base / "tmp"
    tmp_dir.mkdir(exist_ok=True)

    # Find HLP candidates
    logging.info("Scanning for ISOs with HLP files...")
    candidates = find_hlp_candidates(rip_dir)

    if not candidates:
        logging.info("No ISOs found containing HLP files")
        return

    logging.info(f"Found {len(candidates)} ISOs containing HLP files")

    if args.limit:
        candidates = candidates[: args.limit]
        logging.info(f"Limited to first {args.limit} ISOs")

    # Process each ISO
    total_found = 0
    total_copied = 0
    processed = 0

    for i, candidate in enumerate(candidates, 1):
        print(f"\n[{i:3d}/{len(candidates):3d}] ", end="", flush=True)

        try:
            found, copied = process_iso(candidate, target_base, args.dry_run)
            total_found += found
            total_copied += copied
            processed += 1

        except KeyboardInterrupt:
            logging.info("\n\nInterrupted by user")
            break
        except Exception as e:
            logging.error(f"Unexpected error processing {candidate[0]}: {e}")

    # Summary
    logging.info("\n" + "=" * 60)
    logging.info("SUMMARY:")
    logging.info(f"  ISOs processed: {processed}/{len(candidates)}")
    logging.info(f"  HLP files found: {total_found}")
    logging.info(f"  HLP files copied: {total_copied}")
    logging.info(f"  Target directory: {target_base}")

    if args.dry_run:
        logging.info("  (DRY RUN - no files actually copied)")


if __name__ == "__main__":
    main()
