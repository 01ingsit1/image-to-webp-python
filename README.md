# image-to-webp-python

Image to WebP Converter

An asynchronous Python script for batch converting images to WebP format with advanced compression settings using ImageMagick and FFprobe.


Features

    Multi-threaded processing

    APNG support

    Configurable quality

    Optional lossless compression mode

    File collision handling

    Preserved directory structure

    Progress tracking

    Error handling


Requirements
System Dependencies

    FFmpeg (for ffprobe)

    ImageMagick (for magick command)


Python Requirements

    Python 3.7 or higher (comes with asyncio support)

    No additional Python packages required


Installation

    Clone or download the script to your local machine

    Ensure FFmpeg and ImageMagick are installed and accessible in your PATH

    The script is ready to run - no Python package installation needed


Usage
Basic Interactive Mode

Run the script and follow the prompts:
bash

python script_name.py

You will be prompted for:

    Input path: Directory containing source images

    Output path: Directory where WebP files will be saved

    Quality: Compression quality (1-100, default: 89)

    Lossless compression: Enable lossless mode (default: false)

    Filename collision handling: Add iterator to avoid overwrites (default: true)


Configuration

You can customize the script by editing the following variables directly in the code:
Global Settings (near the top of the script)

MAX_CONCURRENT_TASKS = 8  # Maximum simultaneous conversion task


ImageMagick WebP Settings (in magick_command function)

The script uses optimized WebP encoding parameters. Key settings include:

    -quality: Set by user input (1-100)

    -define webp:lossless: Set by user choice

    -define webp:method=6: Compression method (0=fast, 6=slowest/best)

    -define webp:pass=10: Filter pass count

    -define webp:preprocessing=1: Preprocessing filter

    -define webp:sns-strength=80: Spatial noise shaping

You can modify these -define parameters to adjust compression characteristics.


How It Works

    Dependency Check: Verifies ffprobe and magick are available

    File Discovery: Recursively scans input directory for supported image files

    Codec Detection: Uses FFprobe to identify each image's format

    Parallel Processing: Processes multiple images concurrently (up to 8)

    Conversion: Uses ImageMagick with optimized WebP settings

    Verification: Checks output files are valid WebP format

    Error Handling: Logs skipped and failed files with reasons

Output Structure

    Output directory mirrors input directory structure

    Files are renamed with .webp extension

    If filename collision occurs (and append_name=True), files get (2), (3), etc. appended

    Original files are never modified

Error Handling

The script provides detailed error information:

    Skipped files: Already exist in output or naming conflicts

    Failed files: Conversion errors with specific error messages

    Unrecognized codecs: Files with unsupported formats

All errors are summarized at the end of the process.
Performance Tips

    Adjust MAX_CONCURRENT_TASKS: Increase for more parallelism (consider CPU/RAM limits)

    Quality setting: Higher values (80-100) provide better quality but larger files

    Lossless mode: Use for exact preservation, results in larger files

    Input/output on different drives: Can improve performance for large batches

Limitations

    Requires FFmpeg and ImageMagick installation

    Only converts to WebP format

    Metadata may be stripped during conversion (due to -strip option)

    Animated images only supported for APNG format

Troubleshooting
"Command not found" errors

    Ensure FFmpeg and ImageMagick are installed

    Verify they're in your system PATH

    Restart terminal after installation

Permission errors

    Ensure write permissions for output directory

    Run as administrator if needed (Windows) or use sudo (Linux/macOS)

Conversion failures

    Check input files are valid images

    Verify sufficient disk space

    Ensure ImageMagick supports WebP (usually enabled by default)

License

This script is provided as-is. Feel free to modify and distribute.