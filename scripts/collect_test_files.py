#!/usr/bin/env python3
"""
Collect test files for maximum coverage with minimum dataset size, and collect error examples.

This script scans a directory for HLP files, measures code coverage when parsing each file,
uses a greedy algorithm to select the minimum set of files that provides maximum coverage,
and also collects one example file for each unique error type.
"""

import os
import sys
import shutil
from pathlib import Path
import struct
from typing import Dict, List, Optional
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import threading
from collections import defaultdict
import json

# Add src to path so we can import winhlp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import coverage


def get_error_signature(exc_info):
    """Extract a unique signature from an exception."""
    exc_type, exc_value, exc_traceback = exc_info

    # Get the deepest traceback frame that's in our code
    tb = exc_traceback
    while tb.tb_next is not None:
        tb = tb.tb_next

    # Extract source file, line number, and error message
    filename = os.path.basename(tb.tb_frame.f_code.co_filename)
    line_number = tb.tb_lineno
    error_message = str(exc_value).split("\n")[0]  # First line only

    return f"{filename}:{line_number}:{type(exc_value).__name__}:{error_message}"


def measure_coverage_for_file_worker(file_path: str) -> Optional[dict]:
    """Worker function for measuring coverage - must be at module level for pickling."""
    try:
        # Import HelpFile here to avoid import-time execution in coverage
        from winhlp.lib.hlp import HelpFile

        # Create coverage instance with unique data file for this process
        pid = os.getpid()
        data_file = f".coverage.{pid}"
        cov = coverage.Coverage(source=["src/winhlp"], data_file=data_file)
        cov.erase()
        cov.start()

        success = True
        error = None
        error_signature = None

        try:
            # Parse the file - this is what we want to measure
            hlp = HelpFile(file_path)

            # Also try to serialize to JSON to catch serialization errors
            data = json_serializable(hlp.model_dump())
            json.dumps(data)

        except Exception:
            success = False
            error = str(sys.exc_info()[1])
            error_signature = get_error_signature(sys.exc_info())

        cov.stop()
        cov.save()

        # Collect truly covered lines
        covered_lines = set()
        for source_file in cov.get_data().measured_files():
            if "src/winhlp" in source_file and not source_file.endswith("__init__.py"):
                analysis = cov.analysis2(source_file)
                executed_lines = set(analysis[1])  # all executable lines
                missing_lines = set(analysis[3])  # lines that were NOT executed

                # Truly executed = executable - missing
                truly_executed = executed_lines - missing_lines

                for line in truly_executed:
                    covered_lines.add(f"{source_file}:{line}")

        # Get file size
        file_size = os.path.getsize(file_path)

        # Clean up temporary coverage file
        try:
            if os.path.exists(data_file):
                os.remove(data_file)
        except OSError:
            pass  # Ignore cleanup errors

        return {
            "file_path": file_path,
            "file_size": file_size,
            "covered_lines": covered_lines,
            "success": success,
            "error": error,
            "error_signature": error_signature,
        }

    except Exception as e:
        # Clean up temporary coverage file on error too
        try:
            pid = os.getpid()
            data_file = f".coverage.{pid}"
            if os.path.exists(data_file):
                os.remove(data_file)
        except OSError:
            pass  # Ignore cleanup errors

        return {
            "file_path": file_path,
            "file_size": 0,
            "covered_lines": set(),
            "success": False,
            "error": f"Coverage measurement failed: {e}",
            "error_signature": None,
        }


class CoverageCollector:
    """Collects coverage data for HLP files and selects optimal subset."""

    def __init__(self, search_path: str, verbose: bool = True):
        self.search_path = search_path
        self.verbose = verbose
        self.coverage_data: Dict[str, dict] = {}  # filepath -> {size, lines, coverage_obj}
        self.error_files: Dict[str, List[str]] = defaultdict(list)  # error_signature -> [filepaths]

    def log(self, message: str, end: str = "\n") -> None:
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(message, end=end)

    def has_hlp_magic_number(self, file_path: str) -> bool:
        """Check if file has the correct HLP magic number (0x00035F3F)."""
        try:
            with open(file_path, "rb") as f:
                data = f.read(4)
                if len(data) < 4:
                    return False
                magic = struct.unpack("<L", data)[0]
                return magic == 0x00035F3F
        except (IOError, struct.error):
            return False

    def collect_hlp_files(self) -> List[str]:
        """Find all HLP files recursively in the given path that have valid HLP magic numbers."""
        hlp_files = []
        skipped_files = []

        for root, dirs, files in os.walk(self.search_path):
            for file in files:
                if file.upper().endswith(".HLP"):
                    file_path = os.path.join(root, file)
                    if self.has_hlp_magic_number(file_path):
                        hlp_files.append(file_path)
                    else:
                        skipped_files.append(file_path)

        if skipped_files:
            self.log(f"Skipped {len(skipped_files)} files with invalid HLP magic numbers:")
            for f in skipped_files[:5]:  # Show first 5
                self.log(f"  - {os.path.basename(f)}")
            if len(skipped_files) > 5:
                self.log(f"  ... and {len(skipped_files) - 5} more")

        return hlp_files

    def measure_coverage_for_file(self, file_path: str) -> Optional[dict]:
        """Measure code coverage when parsing a single HLP file in-process."""

        try:
            # Import HelpFile here to avoid import-time execution in coverage
            from winhlp.lib.hlp import HelpFile

            # Create coverage instance for this measurement
            cov = coverage.Coverage(source=["src/winhlp"])
            cov.erase()
            cov.start()

            success = True
            error = None

            try:
                # Parse the file - this is what we want to measure
                HelpFile(file_path)
            except Exception as e:
                success = False
                error = str(e)

            cov.stop()
            cov.save()

            # Collect truly covered lines
            covered_lines = set()
            for source_file in cov.get_data().measured_files():
                if "src/winhlp" in source_file and not source_file.endswith("__init__.py"):
                    analysis = cov.analysis2(source_file)
                    executed_lines = set(analysis[1])  # all executable lines
                    missing_lines = set(analysis[3])  # lines that were NOT executed

                    # Truly executed = executable - missing
                    truly_executed = executed_lines - missing_lines

                    for line in truly_executed:
                        covered_lines.add(f"{source_file}:{line}")

            # Get file size
            file_size = os.path.getsize(file_path)

            return {
                "file_path": file_path,
                "file_size": file_size,
                "covered_lines": covered_lines,
                "success": success,
                "error": error,
            }

        except Exception as e:
            self.log(f"Coverage measurement failed for {os.path.basename(file_path)}: {e}")
            return None

    def collect_all_coverage_data(self, hlp_files: List[str]) -> Dict[str, dict]:
        """Collect coverage data for all HLP files using multiprocessing."""
        coverage_data = {}
        successful_files = 0
        failed_files = 0

        # Determine number of workers (cores)
        num_workers = min(mp.cpu_count(), len(hlp_files))
        self.log(f"Using {num_workers} worker processes")

        completed_count = 0
        lock = threading.Lock()

        def log_progress(result):
            nonlocal completed_count, successful_files, failed_files
            with lock:
                completed_count += 1
                basename = os.path.basename(result["file_path"])

                if result is None:
                    self.log(f"[{completed_count:4d}/{len(hlp_files):4d}] {basename}... ✗ (coverage failed)")
                    failed_files += 1
                elif result["success"]:
                    covered = len(result["covered_lines"])
                    self.log(
                        f"[{completed_count:4d}/{len(hlp_files):4d}] {basename}... ✓ ({covered} lines, {result['file_size']} bytes)"
                    )
                    successful_files += 1
                else:
                    self.log(
                        f"[{completed_count:4d}/{len(hlp_files):4d}] {basename}... ✗ (parse failed: {result['error'][:50]}...)"
                    )
                    failed_files += 1

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(measure_coverage_for_file_worker, file_path): file_path for file_path in hlp_files
            }

            # Process results as they complete
            for future in as_completed(future_to_file):
                try:
                    result = future.result()
                    if result:
                        log_progress(result)
                        # Keep files that have coverage data and parsed successfully for coverage
                        if result["covered_lines"] and result["success"]:
                            coverage_data[result["file_path"]] = result
                        # Also track error files for error collection
                        elif not result["success"] and result["error_signature"]:
                            self.error_files[result["error_signature"]].append(result["file_path"])
                except Exception as e:
                    file_path = future_to_file[future]
                    self.log(f"Worker exception for {os.path.basename(file_path)}: {e}")
                    failed_files += 1

        self.log("\nCoverage collection complete:")
        self.log(f"  Total files: {len(hlp_files)}")
        self.log(f"  Successful: {successful_files}")
        self.log(f"  Failed: {failed_files}")
        self.log(f"  With coverage: {len(coverage_data)}")
        self.log(f"  Unique error types: {len(self.error_files)}")

        return coverage_data

    def select_optimal_files(self, coverage_data: Dict[str, dict]) -> List[str]:
        """Use greedy algorithm to select minimum set of files for maximum coverage."""
        if not coverage_data:
            return []

        selected_files = []
        all_covered_lines = set()
        remaining_files = dict(coverage_data)  # Copy for modification

        self.log(f"\nSelecting optimal subset from {len(remaining_files)} files...")

        iteration = 1
        while remaining_files:
            best_file = None
            best_efficiency = 0
            best_new_lines = set()

            # Calculate efficiency for each remaining file
            for file_path, data in remaining_files.items():
                file_lines = data["covered_lines"]
                new_lines = file_lines - all_covered_lines  # Lines not yet covered

                if not new_lines:
                    # This file adds no new coverage, skip it
                    continue

                # Calculate efficiency: new lines per byte
                efficiency = len(new_lines) / data["file_size"]

                if efficiency > best_efficiency:
                    best_efficiency = efficiency
                    best_file = file_path
                    best_new_lines = new_lines

            # If no file adds new coverage, we're done
            if best_file is None:
                break

            # Select the best file
            selected_files.append(best_file)
            all_covered_lines.update(best_new_lines)

            basename = os.path.basename(best_file)
            file_size = remaining_files[best_file]["file_size"]
            new_lines_count = len(best_new_lines)

            self.log(
                f"  {iteration:2d}. {basename} "
                f"(+{new_lines_count} lines, {file_size} bytes, "
                f"eff={best_efficiency:.4f} lines/byte)"
            )

            # Remove selected file from remaining
            del remaining_files[best_file]

            # Remove covered lines from all remaining files and clean up empty ones
            files_to_remove = []
            for file_path, data in remaining_files.items():
                data["covered_lines"] -= all_covered_lines
                if not data["covered_lines"]:
                    files_to_remove.append(file_path)

            for file_path in files_to_remove:
                del remaining_files[file_path]

            iteration += 1

        self.log(f"\nSelected {len(selected_files)} files covering {len(all_covered_lines)} unique lines")

        # Calculate total size and efficiency
        total_size = sum(coverage_data[f]["file_size"] for f in selected_files)
        avg_efficiency = len(all_covered_lines) / total_size if total_size > 0 else 0

        self.log(f"Total size: {total_size:,} bytes")
        self.log(f"Average efficiency: {avg_efficiency:.4f} lines/byte")

        return selected_files

    def copy_selected_files(self, selected_files: List[str], target_dir: Path) -> None:
        """Copy selected files to target directory."""
        if not selected_files:
            self.log("No files to copy!")
            return

        self.log(f"\nCopying {len(selected_files)} files to {target_dir}...")

        for i, file_path in enumerate(selected_files, 1):
            basename = os.path.basename(file_path)
            target_path = target_dir / basename

            # Handle name conflicts by adding a number
            counter = 1
            while target_path.exists():
                name, ext = os.path.splitext(basename)
                target_path = target_dir / f"{name}_{counter}{ext}"
                counter += 1

            try:
                shutil.copy2(file_path, target_path)
                self.log(f"  {i:2d}. {basename} -> {target_path.name}")
            except Exception as e:
                self.log(f"  {i:2d}. {basename} -> FAILED: {e}")

        self.log(f"\nCopy complete! Files saved to: {target_dir}")

    def copy_error_files(self, target_dir: Path) -> None:
        """Copy one example file for each unique error type."""
        if not self.error_files:
            self.log("No error files to copy!")
            return

        self.log(f"\nCopying error examples to {target_dir}...")

        for signature, files in self.error_files.items():
            # Use the first file as the representative
            src_file = files[0]
            basename = os.path.basename(src_file)

            # Create a safe filename from the signature
            safe_signature = signature.replace(":", "_").replace("/", "_").replace(" ", "_")
            safe_signature = "".join(c for c in safe_signature if c.isalnum() or c in "_-.")

            # Copy the file
            dst_file = target_dir / f"{safe_signature}_{basename}"

            try:
                shutil.copy2(src_file, dst_file)
                self.log(f"  {basename} -> {dst_file.name}")
                self.log(f"    Error: {signature}")
                self.log(f"    Files with this error: {len(files)}")
            except Exception as e:
                self.log(f"  {basename} -> FAILED: {e}")

        self.log(f"\nError file copy complete! Files saved to: {target_dir}")

    def run(self) -> None:
        """Run the complete coverage collection and file selection process."""
        # Set up directories with atomic operation
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        coverage_dir = project_root / "tests" / "data" / "coverage"
        coverage_dir_new = project_root / "tests" / "data" / "coverage.new"
        error_dir = project_root / "tests" / "data" / "errors"
        error_dir_new = project_root / "tests" / "data" / "errors.new"

        # Create new directories (clean slate)
        if coverage_dir_new.exists():
            shutil.rmtree(coverage_dir_new)
        coverage_dir_new.mkdir(parents=True, exist_ok=True)

        if error_dir_new.exists():
            shutil.rmtree(error_dir_new)
        error_dir_new.mkdir(parents=True, exist_ok=True)

        self.log(f"Searching for HLP files in: {self.search_path}")
        hlp_files = self.collect_hlp_files()
        self.log(f"Found {len(hlp_files)} HLP files")

        if not hlp_files:
            self.log("No HLP files found!")
            return

        self.log("\nPhase 1: Collecting coverage data for each file...")
        coverage_data = self.collect_all_coverage_data(hlp_files)

        if not coverage_data:
            self.log("No files with coverage data found!")
            return

        self.log("\nPhase 2: Selecting optimal subset...")
        selected_files = self.select_optimal_files(coverage_data)

        if not selected_files:
            self.log("No files selected!")
            return

        self.log("\nPhase 3: Copying selected files...")
        self.copy_selected_files(selected_files, coverage_dir_new)

        self.log("\nPhase 4: Copying error examples...")
        self.copy_error_files(error_dir_new)

        # Atomic replacement for coverage directory
        if coverage_dir.exists():
            coverage_dir_old = project_root / "tests" / "data" / "coverage.old"
            if coverage_dir_old.exists():
                shutil.rmtree(coverage_dir_old)
            coverage_dir.rename(coverage_dir_old)

        coverage_dir_new.rename(coverage_dir)

        # Clean up old coverage directory
        if (project_root / "tests" / "data" / "coverage.old").exists():
            shutil.rmtree(project_root / "tests" / "data" / "coverage.old")

        # Atomic replacement for error directory
        if error_dir.exists():
            error_dir_old = project_root / "tests" / "data" / "errors.old"
            if error_dir_old.exists():
                shutil.rmtree(error_dir_old)
            error_dir.rename(error_dir_old)

        error_dir_new.rename(error_dir)

        # Clean up old error directory
        if (project_root / "tests" / "data" / "errors.old").exists():
            shutil.rmtree(project_root / "tests" / "data" / "errors.old")

        self.log("\nProcess complete!")
        self.log(f"Coverage files: {coverage_dir.relative_to(project_root)}")
        self.log(f"Error files: {error_dir.relative_to(project_root)}")


def json_serializable(obj):
    """Convert object to JSON-serializable format by handling bytes."""
    if isinstance(obj, bytes):
        return f"<bytes: {len(obj)} bytes>"
    elif isinstance(obj, dict):
        return {k: json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [json_serializable(item) for item in obj]
    else:
        return obj


def main():
    if len(sys.argv) not in [2, 3]:
        print("Usage: ./scripts/collect_test_files.py <path_to_search> [--quiet]")
        sys.exit(1)

    search_path = sys.argv[1]
    verbose = "--quiet" not in sys.argv

    if not os.path.exists(search_path):
        print(f"Error: Path '{search_path}' does not exist")
        sys.exit(1)

    collector = CoverageCollector(search_path, verbose)
    collector.run()


if __name__ == "__main__":
    # Required for multiprocessing on Windows and some Linux systems
    mp.set_start_method("spawn", force=True)
    main()
