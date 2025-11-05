import asyncio
import shutil
import subprocess
from pathlib import Path


MAX_CONCURRENT_TASKS = 8

EXTENSIONS = [
    '.avif',
    '.bmp',
    '.gif',
    '.jpeg',
    '.jpg',
    '.png',
    '.tiff',
    '.tif',
    '.webp'
]

CODECS = [
    'apng',
    'av1',
    'gif',
    'mjpeg',
    'png',
    'tiff',
    'webp'
]


def check_dependencies():
    required_commands = ['ffprobe', 'magick']
    missing: list[str] = []
    for cmd in required_commands:
        if shutil.which(cmd) is None:
            missing.append(cmd)
    if missing:
        print(f"Error: the following commands were not found in PATH: {', '.join(missing)}")
        print("Please install:")
        if 'ffprobe' in missing:
            print("- FFmpeg (for ffprobe)")
        if 'magick' in missing:
            print("- ImageMagick (for magick)")
        return False
    return True


class AsyncCounter:
    def __init__(self, initial=0):
        self.value = initial
        self._lock = asyncio.Lock()
    async def increment(self):
        async with self._lock:
            self.value += 1
            return self.value


def get_dir_path(path_message):
    while True:
        userinput = input(path_message).strip().lower()
        if not userinput:
            print('Path does not exist!')
            continue
        inputpath = Path(userinput).resolve()
        if not (inputpath.exists()):
            print('Path does not exist!')
            continue
        if not (inputpath.is_dir()):
            print('Path is not dir!')
            continue
        return inputpath


def get_quality():
    default = 89
    input_message = (
        f"Enter quality (1-100, default {default}): "
    )
    while True:
        if not (inp := input(input_message).strip()):
            return default
        try:
            quality = int(inp)
            if 1 <= quality <= 100:
                return quality
            print('Error: quality should be from 1 to 100.')
        except ValueError:
            print('Error: quality should be an integer.')


def get_lossless():
    default = False
    input_message = (
        "Use lossless-compression? (default false, 'true' for lossless): "
    )
    while True:
        if not (inp := input(input_message).strip()):
            return default
        inp = str(inp)
        if inp.lower() == 'true':
            return True
        print("Error: please enter 'true' or leave empty for false")


def get_append_name():
    default = True
    input_message = (
        "Add iterator to filenames to avoid collision? "
        "(default true, 'false' to turn it off): ")
    while True:
        if not (inp := input(input_message).strip()):
            return default
        inp = str(inp)
        if inp.lower() == 'false':
            return False
        print("Error: please enter 'false' or leave empty for true")


def get_image_codec(filepath):
    if not Path(filepath).exists():
        return "Error: file doesn't exist"
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        str(filepath)
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Error: Timeout"
    except Exception as e:
        return f"Error: {str(e)}"


def iterate_filename(collision_path, iterator):
    iteratepath = collision_path.parent
    iteratepath = iteratepath / (f"{collision_path.stem} "
                                 f"({iterator}){collision_path.suffix}")
    return iteratepath


def magick_command(params):
    input_path, output_path, is_apng, quality, lossless = params
    cmd = [
        'magick',
        # this correctly process apng files as animated
        ('apng:' + input_path) if is_apng else input_path,
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
        '-define', f"webp:lossless={'true' if lossless else 'false'}",
        '-define', 'webp:method=6',
        # 0 - none, 1 - segment-smooth, 2 - pseudo-random dithering
        '-define', 'webp:preprocessing=1',
        '-define', 'webp:partitions=3',
        '-define', 'webp:partition-limit=0',
        '-define', 'webp:pass=10',
        '-define', 'webp:segment=4',
        # 0-100, default 80. higher value = more bits to edges,
        # less to plain part of the image
        '-define', 'webp:sns-strength=80',
        '-define', 'webp:thread-level=1',
        '-define', 'webp:use-sharp-yuv=true',
        output_path
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=True,
            text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error processing {params[0]}: {e}")
        if e.stderr:
            print(f"Error: {str(e.stderr.strip())}")
            return f"Error: {str(e.stderr.strip())}"
    except Exception as e:
        if e:
            print(f"Error: {str(e)}")
            return f"Error: {str(e)}"


def should_process_file(file: Path):
    if file.suffix.lower() not in EXTENSIONS:
        return False
    if file.name.startswith('.'):
        return False
    if not file.is_file():
        return False
    if not file.is_file() or file.is_symlink():
        return False
    return True


inputpath = get_dir_path('Input path: ')
outputpath = get_dir_path('Output path: ')
quality = get_quality()
lossless = get_lossless()
append_name = get_append_name()

print("\nConvertion settings:")
print(f"Quality:        {quality}")
print(f"Lossless:       {lossless}")
print(f"Append_name:    {append_name}")
print(f"Input path:     {inputpath}")
print(f"Output path:    {outputpath}")
input("\nPress Enter to start...")


files = [file for file in Path(inputpath).rglob('*')
         if should_process_file(file)]
total_files = len(files)


async def process_image(file: Path, semaphore: asyncio.Semaphore,
                        names_lock: asyncio.Lock, used_names: set,
                        skipped_files: dict, failed_files: dict,
                         counter: AsyncCounter, total_files: int):
    async with semaphore:
        await counter.increment()
        file_path = file.absolute()
        # check image codec before encoding
        image_codec = await asyncio.to_thread(get_image_codec, file_path)
        if image_codec not in CODECS:
            async with names_lock:
                failed_message = f"Unrecognized codec: {image_codec}"
                failed_files.setdefault(str(file_path), failed_message)
                return
        is_apng = (image_codec == 'apng')
        # setting output image name
        image_output_path = str(file.parent)
        image_output_path = image_output_path.replace(
            str(inputpath), str(outputpath))
        image_output_path = Path(image_output_path) / (file.stem + '.webp')
        # checking for collisions, creating output dir if not exist
        async with names_lock:
            image_output_path.parent.mkdir(parents=True, exist_ok=True)
        if append_name:
            iterator = 2
            collision_path = image_output_path
            async with names_lock:
                while True:
                    is_exist = image_output_path.exists()
                    check_name = str(image_output_path.absolute())
                    name_in_use = check_name in used_names # this is bool
                    if not is_exist and not name_in_use:
                        used_names.add(str(image_output_path.absolute()))
                        break
                    image_output_path = iterate_filename(collision_path,
                                                         iterator)
                    iterator += 1
        else:
            async with names_lock:
                is_exist = image_output_path.exists()
                check_name = str(image_output_path.absolute())
                name_in_use = check_name in used_names # this is bool
                if is_exist or name_in_use:
                    print(f"Conflict: {image_output_path} is "
                          "already being processed or exist, skipping")
                    skipped_files.setdefault(str(file_path), 'exist')
                    return
                used_names.add(str(image_output_path.absolute()))
        # console output for files in encoding
        async with names_lock:
            processed_name = str(file_path)
            processed_name = processed_name.replace(str(inputpath), '*')
            print(f"Processing({counter.value}/{total_files}) "
                  f"{processed_name}")
        # encoding
        params = str(file_path), image_output_path, is_apng, quality, lossless
        result = await asyncio.to_thread(magick_command, params)
        async with names_lock:
            if isinstance(result, str) and result.startswith('Error:'):
                failed_files.setdefault(str(file_path), result)
                if (image_output_path.exists()):
                    image_output_path.unlink()
                return
        image_codec = await asyncio.to_thread(get_image_codec,
                                              image_output_path)
        async with names_lock:
            if image_codec != 'webp':
                failed_message = f"Unrecognized output codec: {image_codec}"
                failed_files.setdefault(str(file_path), failed_message)
                if (image_output_path.exists()):
                    image_output_path.unlink()


async def main():
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    names_lock = asyncio.Lock()
    used_names = set()
    skipped_files = {}
    failed_files = {}
    counter = AsyncCounter()

    try:
        async with asyncio.TaskGroup() as tg:
            for file in files:
                tg.create_task(process_image(file, semaphore, names_lock,
                                             used_names, skipped_files,
                                             failed_files, counter,
                                             total_files))
    except ExceptionGroup as eg:
        print(f"Error when processing: {eg}")

    if skipped_files:
        print(f"\nSkipped files: {len(skipped_files)}")
        print("List:")
        for skipped_file, reason in skipped_files.items():
            print(f"  {skipped_file} - {reason}")
    if failed_files:
        print(f"\nFailed files: {len(failed_files)}")
        print('List:')
        for failed_file, error in failed_files.items():
            print(f"  {failed_file} - {error}")
    if not skipped_files and not failed_files:
        print("\nAll files was processed.")

if __name__ == "__main__":
    asyncio.run(main())