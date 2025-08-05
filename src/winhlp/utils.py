"""Utility functions for Windows Help files.

Based on the C reference utilities in doc/ref/:
- splitmrb.c: Splits MRB into SHG/BMP/WMF and SHG into BMP/WMF files
- zapres.c: Removes resolution information from Windows bitmap files

These utilities handle multi-resolution bitmaps that contain multiple versions
of the same image at different resolutions for different display devices.
"""

from typing import List, Dict, Optional, BinaryIO
import struct
from pathlib import Path


class MRBSplitter:
    """
    Utility to split MRB (Multi-Resolution Bitmap) files into individual resolution versions.

    Based on splitmrb.c from the reference implementation.
    MRB files contain multiple bitmap versions for different display resolutions:
    - EGA, VGA, CGA, 8514, MAC resolutions
    - BMP, WMF formats
    - SHG (Segmented Hotspot Graphics) files
    """

    # Resolution-dependent extensions as defined in splitmrb.c
    RESOLUTION_EXTENSIONS = {
        "EGA": ".EGA",
        "VGA": ".VGA",
        "CGA": ".CGA",
        "8514": ".854",
        "MAC": ".MAC",
        "BMP": ".BMP",
        "WMF": ".WMF",
    }

    def __init__(self, mrb_filepath: str):
        """
        Initialize MRB splitter.

        Args:
            mrb_filepath: Path to the MRB file to split
        """
        self.mrb_filepath = Path(mrb_filepath)
        self.output_dir = self.mrb_filepath.parent
        self.base_name = self.mrb_filepath.stem

    def split_mrb(self) -> List[str]:
        """
        Split MRB file into individual resolution files.

        Returns:
            List of output file paths created
        """
        output_files = []

        try:
            with open(self.mrb_filepath, "rb") as mrb_file:
                # Read MRB header to determine number of resolutions
                header = self._read_mrb_header(mrb_file)
                if not header:
                    raise ValueError("Invalid MRB file format")

                # Extract each resolution
                for i, resolution_info in enumerate(header["resolutions"]):
                    output_file = self._extract_resolution(mrb_file, resolution_info, i)
                    if output_file:
                        output_files.append(output_file)

        except Exception as e:
            raise ValueError(f"Failed to split MRB file: {e}")

        return output_files

    def _read_mrb_header(self, mrb_file: BinaryIO) -> Optional[Dict]:
        """Read MRB file header structure."""
        try:
            # MRB files start with a header indicating number of pictures
            mrb_file.seek(0)
            header_data = mrb_file.read(16)  # Read initial header

            if len(header_data) < 2:
                return None

            # Parse number of pictures (multi-resolution indicator)
            num_pictures = struct.unpack("<H", header_data[:2])[0]

            if num_pictures <= 1:
                # Not a multi-resolution bitmap
                return None

            # Parse resolution entries
            resolutions = []
            for i in range(num_pictures):
                # Each resolution entry contains offset and size info
                entry_data = mrb_file.read(8)  # Typical entry size
                if len(entry_data) < 8:
                    break

                offset, size = struct.unpack("<LL", entry_data)
                resolutions.append({"offset": offset, "size": size, "index": i})

            return {"num_pictures": num_pictures, "resolutions": resolutions}

        except (struct.error, IOError):
            return None

    def _extract_resolution(self, mrb_file: BinaryIO, resolution_info: Dict, index: int) -> Optional[str]:
        """Extract a single resolution from MRB file."""
        try:
            # Seek to resolution data
            mrb_file.seek(resolution_info["offset"])
            resolution_data = mrb_file.read(resolution_info["size"])

            if len(resolution_data) < resolution_info["size"]:
                return None

            # Determine file type and extension
            file_type = self._detect_image_type(resolution_data)
            extension = self.RESOLUTION_EXTENSIONS.get(file_type, f".{index:03d}")

            # Create output filename
            output_filename = f"{self.base_name}{extension}"
            output_path = self.output_dir / output_filename

            # Write resolution data to file
            with open(output_path, "wb") as output_file:
                output_file.write(resolution_data)

            return str(output_path)

        except (IOError, OSError) as e:
            print(f"Warning: Failed to extract resolution {index}: {e}")
            return None

    def _detect_image_type(self, data: bytes) -> str:
        """Detect image type from data header."""
        if len(data) < 4:
            return "BMP"  # Default fallback

        # Check for common image format signatures
        if data[:2] == b"BM":
            return "BMP"
        elif data[:4] == b"\xd7\xcd\xc6\x9a":  # WMF signature
            return "WMF"
        elif data[:8] == b"\x01\x00\x09\x00\x00\x03\x10\x00":  # Common WMF header
            return "WMF"
        else:
            return "BMP"  # Default to BMP


class ResolutionRemover:
    """
    Utility to remove resolution information from bitmap files.

    Based on zapres.c from the reference implementation.
    This removes resolution information so WinHelp will not rescale images
    and MRBC can be applied to specify new resolution.
    """

    def __init__(self, create_backup: bool = True):
        """
        Initialize resolution remover.

        Args:
            create_backup: Whether to create .BAK files before modification
        """
        self.create_backup = create_backup

    def remove_resolution_info(self, filepath: str) -> bool:
        """
        Remove resolution information from a bitmap file.

        Args:
            filepath: Path to the bitmap file (.BMP, .MRB, .SHG)

        Returns:
            True if successful, False otherwise
        """
        file_path = Path(filepath)

        try:
            # Create backup if requested
            if self.create_backup:
                backup_path = file_path.with_suffix(file_path.suffix + ".BAK")
                if backup_path.exists():
                    backup_path.unlink()  # Remove existing backup
                file_path.rename(backup_path)
                source_path = backup_path
            else:
                source_path = file_path

            # Read original file
            with open(source_path, "rb") as input_file:
                data = input_file.read()

            # Process based on file type
            file_ext = file_path.suffix.upper()
            if file_ext == ".BMP":
                processed_data = self._remove_bmp_resolution(data)
            elif file_ext == ".MRB":
                processed_data = self._remove_mrb_resolution(data)
            elif file_ext == ".SHG":
                processed_data = self._remove_shg_resolution(data)
            else:
                # Unknown type, copy as-is
                processed_data = data

            # Write processed file
            with open(file_path, "wb") as output_file:
                output_file.write(processed_data)

            return True

        except (IOError, OSError) as e:
            print(f"Error processing {filepath}: {e}")
            return False

    def _remove_bmp_resolution(self, data: bytes) -> bytes:
        """Remove resolution information from BMP file."""
        if len(data) < 54:  # Minimum BMP header size
            return data

        # BMP resolution is stored in the header at offsets 38-45
        # XPelsPerMeter (4 bytes) and YPelsPerMeter (4 bytes)
        data_array = bytearray(data)

        # Zero out resolution fields
        data_array[38:42] = b"\x00\x00\x00\x00"  # XPelsPerMeter
        data_array[42:46] = b"\x00\x00\x00\x00"  # YPelsPerMeter

        return bytes(data_array)

    def _remove_mrb_resolution(self, data: bytes) -> bytes:
        """Remove resolution information from MRB file."""
        # MRB files contain multiple bitmaps, process each one
        try:
            if len(data) < 2:
                return data

            data_array = bytearray(data)
            num_pictures = struct.unpack("<H", data[:2])[0]

            # Process each embedded picture
            offset = 2 + (num_pictures * 8)  # Skip header and offset table

            for i in range(num_pictures):
                # Find and process each bitmap
                while offset < len(data_array) - 54:
                    if data_array[offset : offset + 2] == b"BM":
                        # Found BMP header, remove resolution
                        if offset + 54 <= len(data_array):
                            data_array[offset + 38 : offset + 42] = b"\x00\x00\x00\x00"
                            data_array[offset + 42 : offset + 46] = b"\x00\x00\x00\x00"
                        break
                    offset += 1

            return bytes(data_array)

        except (struct.error, IndexError):
            return data

    def _remove_shg_resolution(self, data: bytes) -> bytes:
        """Remove resolution information from SHG file."""
        # SHG files are segmented hotspot graphics
        # They contain embedded bitmaps that need resolution removal
        try:
            data_array = bytearray(data)
            offset = 0

            # Scan for embedded bitmaps
            while offset < len(data_array) - 54:
                if data_array[offset : offset + 2] == b"BM":
                    # Found embedded BMP, remove resolution
                    if offset + 54 <= len(data_array):
                        data_array[offset + 38 : offset + 42] = b"\x00\x00\x00\x00"
                        data_array[offset + 42 : offset + 46] = b"\x00\x00\x00\x00"
                offset += 1

            return bytes(data_array)

        except IndexError:
            return data


def split_mrb_file(mrb_filepath: str, output_dir: Optional[str] = None) -> List[str]:
    """
    Convenience function to split an MRB file into individual resolution files.

    Args:
        mrb_filepath: Path to the MRB file
        output_dir: Output directory (defaults to same directory as input file)

    Returns:
        List of created output file paths
    """
    splitter = MRBSplitter(mrb_filepath)
    if output_dir:
        splitter.output_dir = Path(output_dir)

    return splitter.split_mrb()


def remove_bitmap_resolution(filepath: str, create_backup: bool = True) -> bool:
    """
    Convenience function to remove resolution information from a bitmap file.

    Args:
        filepath: Path to the bitmap file (.BMP, .MRB, .SHG)
        create_backup: Whether to create a .BAK backup file

    Returns:
        True if successful, False otherwise
    """
    remover = ResolutionRemover(create_backup=create_backup)
    return remover.remove_resolution_info(filepath)
