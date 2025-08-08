import os
import asyncio
from pathlib import Path
from collections import defaultdict
import shutil

MAX_CONCURRENT_TASKS = 8

def check_dependencies():
    """Check PATH for ffprobe and magick"""
    required_commands = ['ffprobe', 'magick']
    missing = []

    for cmd in required_commands:
        if shutil.which(cmd) is None:
            missing.append(cmd)

    if missing:
        print(f"Error: next commands is not found in PATH: {', '.join(missing)}")
        print("Please, install:")
        print("- FFmpeg (for ffprobe)")
        print("- ImageMagick (for magick)")
        return False

    return True

def get_input_path():
    """Request and check input path"""
    while True:
        path = input("Input path: ").strip()
        if os.path.isdir(path):
            return os.path.normpath(path)
        print(f"Error: folder '{path}' doesn't exist. Please enter correct path.")

def get_output_path():
    """Request and check output path"""
    while True:
        path = input("Output path: ").strip()
        path = os.path.normpath(path)

        if not os.path.exists(path):
            try:
                os.makedirs(path)
                return path
            except OSError as e:
                print(f"Error when creating folder: {e}")
                continue

        # Check folder to be empty
        if os.listdir(path):
            print(f"Error: folder '{path}' is not empty. Please chose empty folder.")
            continue

        return path

def get_quality():
    """Request quality"""
    default = 89
    while True:
        inp = input(f"Enter quality (1-100, default {default}): ").strip()
        if not inp:
            return default

        try:
            quality = int(inp)
            if 1 <= quality <= 100:
                return quality
            print("Error: quality should be from 1 to 100.")
        except ValueError:
            print("Error: quality should be integer.")

def get_lossless():
    """Request lossless on/off"""
    default = False
    inp = input("Use lossless-compression? (default false, enter 'true' for lossless): ").strip()
    return inp.lower() == 'true'

def get_append_name():
    """Request filename iterator mode"""
    default = True
    inp = input("Add iterator to filenames to avoid collision? (default true, enter 'false' to turn it off): ").strip()
    return inp.lower() != 'false'

def confirm_settings(settings):
    """Show settings and await for confirmation"""
    print("\nConvertion settings:")
    print(f"Quality: {settings['quality']}")
    print(f"Lossless: {settings['lossless']}")
    print(f"Append_name: {settings['append_name']}")
    print(f"Input path: {settings['input_dir']}")
    print(f"Output path: {settings['output_dir']}")
    input("\nPress Enter to start...")

async def get_image_codec(filepath):
    """Check image codec with ffprobe"""
    cmd = [
        'ffprobe',
        '-i', filepath,
        '-v', 'error',
        '-loglevel', 'quiet',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name',
        '-of', 'default=nw=1:nk=1'
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip()

def get_magick_command(input_path, output_path, is_apng=False, quality=89, lossless=False):
    """ImageMagick command"""
    base_cmd = [
        'magick',
        'apng:' + input_path if is_apng else input_path,
        '-auto-orient',
        '-coalesce',
        '-strip',
        '-quality', str(quality),
        '-define', 'webp:alpha-compression=1',
        '-define', 'webp:alpha-filtering=2',
        '-define', 'webp:alpha-quality=100',
        '-define', 'webp:auto-filter=true',
        '-define', 'webp:filter-sharpness=4',
        '-define', 'webp:filter-strength=50',
        '-define', 'webp:filter-type=1',
        '-define', f'webp:lossless={"true" if lossless else "false"}',
        '-define', 'webp:method=6',
        '-define', 'webp:preprocessing=1',      # 0 - none, 1 - segment-smooth, 2 - pseudo-random dithering
        '-define', 'webp:partitions=3',
        '-define', 'webp:partition-limit=0',
        '-define', 'webp:pass=10',
        '-define', 'webp:segment=4',
        '-define', 'webp:sns-strength=80',      # 0-100, default 80. higher value = more bits to edges, less to plain part of the image
        '-define', 'webp:thread-level=1',
        '-define', 'webp:use-sharp-yuv=true',
        output_path
    ]
    return base_cmd

async def convert_to_webp(input_path, output_path, codec, quality, lossless):
    """Convertion and apng switch"""
    is_apng = (codec == 'apng')
    command = get_magick_command(input_path, output_path, is_apng, quality, lossless)

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return input_path

def generate_output_filename(base_name, counter, used_names):
    """Iterator to prevent filename collision"""
    if counter == 1:
        return base_name

    name, ext = os.path.splitext(base_name)
    new_name = f"{name}({counter}){ext}"

    # Check name in use
    while new_name in used_names:
        counter += 1
        new_name = f"{name}({counter}){ext}"

    return new_name

async def process_file(input_path, output_path, semaphore, used_names, quality, lossless, append_name):
    async with semaphore:
        try:
            # Check input file format
            codec = await get_image_codec(input_path)
            print(f"Queued: {input_path} (format: {codec})")

            # Converting
            result = await convert_to_webp(input_path, output_path, codec, quality, lossless)

            # Check for output file
            if not os.path.exists(output_path):
                print(f"Error: output file doesn't exist {output_path}")
                return False, None, input_path

            # Check for output file codec
            output_codec = await get_image_codec(output_path)
            if output_codec != 'webp':
                print(f"Error: output file is not webp (format: {output_codec})")
                try:
                    os.remove(output_path)  # Remove if file is not webp
                except OSError:
                    pass
                return False, None, input_path

            print(f"Converted: {input_path} -> {output_path}")
            return True, codec, None

        except Exception as e:
            print(f"Error when converting {input_path}: {str(e)}")
            # Try to remove corrupted file
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            return False, None, input_path

async def main():
    if not check_dependencies():
        return  # Terminate if dependencies are not installed

    # Getting settings from user
    input_dir = get_input_path()
    output_dir = get_output_path()
    quality = get_quality()
    lossless = get_lossless()
    append_name = get_append_name()

    # Show settings and waiting for confirmation
    settings = {
        'quality': quality,
        'lossless': lossless,
        'append_name': append_name,
        'input_dir': input_dir,
        'output_dir': output_dir
    }
    confirm_settings(settings)

    # Main convertion
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    valid_exts = ('.webp', '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif')

    # We collect files in two stages: first webp, then the rest
    webp_files = []
    other_files = []

    for root, _, files in os.walk(input_dir):
        for filename in files:
            if filename.lower().endswith(valid_exts):
                input_path = os.path.join(root, filename)
                if filename.lower().endswith('.webp'):
                    webp_files.append(input_path)
                else:
                    other_files.append(input_path)

    # Merge lists with priority for webp
    all_files = webp_files + other_files

    # List to check filenames in use
    output_names = defaultdict(int)
    used_names = set()
    skipped_files = []

    tasks = []

    for input_path in all_files:
        rel_path = os.path.relpath(input_path, input_dir)
        base_name = os.path.splitext(os.path.basename(rel_path))[0] + ".webp"
        rel_dir = os.path.dirname(rel_path)

        # Full relative path for the output file (including subdirectories)
        full_rel_path = os.path.join(rel_dir, base_name) if rel_dir else base_name

        # Define the output file name
        if append_name:
            # Increment the counter for this full relative path
            output_names[full_rel_path] += 1
            counter = output_names[full_rel_path]

            # Generate a unique name only if
            if counter > 1:
                name, ext = os.path.splitext(base_name)
                output_filename = f"{name}({counter}){ext}"
                output_path = os.path.join(output_dir, rel_dir, output_filename)
            else:
                output_path = os.path.join(output_dir, rel_dir, base_name)
        else:
            output_path = os.path.join(output_dir, full_rel_path)

            # Checking if we already process file with that name
            if output_path in used_names:
                skipped_files.append(input_path)
                continue

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        tasks.append(process_file(input_path, output_path, semaphore, used_names, quality, lossless, append_name))
        used_names.add(output_path)

    success_count = 0
    failed_files = []

    for future in asyncio.as_completed(tasks):
        success, codec, failed_file = await future
        if success:
            success_count += 1
        elif failed_file:
            failed_files.append(failed_file)

    # Add skipped files to log (only if append_name = False)
    if not append_name and skipped_files:
        skipped_log_path = os.path.join(input_dir, "skipped_files.log")
        with open(skipped_log_path, 'w', encoding='utf-8') as f:
            f.write("Next file was skipped due to the names collision:\n")
            for file in skipped_files:
                f.write(f"{file}\n")
        print(f"\nAdded to skipped files in {skipped_log_path}")

    # Add error files to log
    if failed_files:
        error_log_path = os.path.join(input_dir, "failed_files.log")
        with open(error_log_path, 'w', encoding='utf-8') as f:
            f.write("Next files was not converted due to the errors:\n")
            for file in failed_files:
                f.write(f"{file}\n")
        print(f"\nAdded to error log in {error_log_path}")

    print(f"\nDone! Converted {success_count} files.")

if __name__ == "__main__":
    asyncio.run(main())