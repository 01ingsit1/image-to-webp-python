import os
import asyncio
from pathlib import Path
from collections import defaultdict
import shutil

MAX_CONCURRENT_TASKS = 8

def check_dependencies():
    """Проверяет наличие необходимых команд в системе"""
    required_commands = ['ffprobe', 'magick']
    missing = []
    
    for cmd in required_commands:
        if shutil.which(cmd) is None:
            missing.append(cmd)
    
    if missing:
        print(f"Ошибка: следующие команды не найдены в PATH: {', '.join(missing)}")
        print("Убедитесь, что установлены:")
        print("- FFmpeg (для ffprobe)")
        print("- ImageMagick (для magick)")
        return False
    
    return True

def get_input_path():
    """Запрашивает и проверяет входной путь"""
    while True:
        path = input("Введите путь к исходной папке с изображениями: ").strip()
        if os.path.isdir(path):
            return os.path.normpath(path)
        print(f"Ошибка: папка '{path}' не существует. Пожалуйста, введите корректный путь.")

def get_output_path():
    """Запрашивает и проверяет выходной путь"""
    while True:
        path = input("Введите путь к папке для сохранения результатов: ").strip()
        path = os.path.normpath(path)
        
        # Проверяем существование папки
        if not os.path.exists(path):
            try:
                os.makedirs(path)
                return path
            except OSError as e:
                print(f"Ошибка при создании папки: {e}")
                continue
        
        # Проверяем что папка пуста
        if os.listdir(path):
            print(f"Ошибка: папка '{path}' не пуста. Пожалуйста, выберите пустую папку.")
            continue
        
        return path

def get_quality():
    """Запрашивает качество сжатия"""
    default = 89
    while True:
        inp = input(f"Введите качество сжатия (1-100, по умолчанию {default}): ").strip()
        if not inp:
            return default
        
        try:
            quality = int(inp)
            if 1 <= quality <= 100:
                return quality
            print("Ошибка: качество должно быть в диапазоне от 1 до 100.")
        except ValueError:
            print("Ошибка: введите целое число.")

def get_lossless():
    """Запрашивает режим lossless"""
    default = False
    inp = input("Использовать lossless-сжатие? (по умолчанию нет, введите 'true' для включения): ").strip()
    return inp.lower() == 'true'

def get_append_name():
    """Запрашивает режим добавления счетчика к именам"""
    default = True
    inp = input("Добавлять счетчик к именам файлов при дублировании? (по умолчанию да, введите 'false' для отключения): ").strip()
    return inp.lower() != 'false'

def confirm_settings(settings):
    """Выводит настройки и ожидает подтверждения"""
    print("\nНастройки конвертации:")
    print(f"Качество: {settings['quality']}")
    print(f"Lossless: {settings['lossless']}")
    print(f"Append_name: {settings['append_name']}")
    print(f"Input path: {settings['input_dir']}")
    print(f"Output path: {settings['output_dir']}")
    input("\nНажмите Enter чтобы начать конвертацию...")

async def get_image_codec(filepath):
    """Определяет кодек изображения с помощью ffprobe"""
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
    """Генерирует команду ImageMagick с параметрами"""
    base_cmd = [
        'magick',
        'apng:' + input_path if is_apng else input_path,
        '-auto-orient',
        '-coalesce',
        '-strip',
        '-quality', str(quality),
        '-define', 'webp:alpha-compression=1',
        '-define', 'webp:alpha-filtering=2',
        '-define', f'webp:alpha-quality={quality}',
        '-define', 'webp:alpha-filter=true',
        '-define', 'webp:filter-strength=100',
        '-define', 'webp:filter-type=1',
        '-define', f'webp:lossless={"true" if lossless else "false"}',
        '-define', 'webp:method=6',
        '-define', 'webp:partitions=3',
        '-define', 'webp:partition-limit=0',
        '-define', 'webp:pass=10',
        '-define', 'webp:segment=4',
        '-define', 'webp:use-sharp-yuv=true',
        output_path
    ]
    return base_cmd

async def convert_to_webp(input_path, output_path, codec, quality, lossless):
    """Выбирает правильный метод конвертации"""
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
    """Генерирует уникальное имя файла с учетом уже использованных"""
    if counter == 1:
        return base_name
    
    name, ext = os.path.splitext(base_name)
    new_name = f"{name}({counter}){ext}"
    
    # Проверяем, не занято ли уже это имя
    while new_name in used_names:
        counter += 1
        new_name = f"{name}({counter}){ext}"
    
    return new_name

async def process_file(input_path, output_path, semaphore, used_names, quality, lossless, append_name):
    async with semaphore:
        try:
            # Сначала проверяем формат исходного файла
            codec = await get_image_codec(input_path)
            print(f"Обнаружен: {input_path} (формат: {codec})")
            
            # Конвертируем
            result = await convert_to_webp(input_path, output_path, codec, quality, lossless)
            
            # Проверяем что файл создан
            if not os.path.exists(output_path):
                print(f"Ошибка: выходной файл не создан {output_path}")
                return False, None, input_path
            
            # Проверяем формат выходного файла
            output_codec = await get_image_codec(output_path)
            if output_codec != 'webp':
                print(f"Ошибка: выходной файл не является webp (формат: {output_codec})")
                try:
                    os.remove(output_path)  # Удаляем невалидный файл
                except OSError:
                    pass
                return False, None, input_path
            
            print(f"Конвертировано: {input_path} -> {output_path}")
            return True, codec, None
            
        except Exception as e:
            print(f"Ошибка при обработке {input_path}: {str(e)}")
            # Пытаемся удалить выходной файл в случае ошибки
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            return False, None, input_path

async def main():    
    if not check_dependencies():
        return  # Завершаем работу, если зависимости не установлены    
    
    # Получаем параметры от пользователя
    input_dir = get_input_path()
    output_dir = get_output_path()
    quality = get_quality()
    lossless = get_lossless()
    append_name = get_append_name()
    
    # Показываем настройки и ждем подтверждения
    settings = {
        'quality': quality,
        'lossless': lossless,
        'append_name': append_name,
        'input_dir': input_dir,
        'output_dir': output_dir
    }
    confirm_settings(settings)
    
    # Основной код конвертации
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    valid_exts = ('.webp', '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif')
    
    # Собираем файлы в два этапа: сначала webp, потом остальные
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
    
    # Объединяем списки с приоритетом для webp
    all_files = webp_files + other_files
    
    # Словарь для отслеживания использованных имен
    output_names = defaultdict(int)
    used_names = set()
    skipped_files = []
    
    tasks = []
    
    for input_path in all_files:
        rel_path = os.path.relpath(input_path, input_dir)
        base_name = os.path.splitext(os.path.basename(rel_path))[0] + ".webp"
        rel_dir = os.path.dirname(rel_path)
        
        # Полный относительный путь для выходного файла (включая поддиректории)
        full_rel_path = os.path.join(rel_dir, base_name) if rel_dir else base_name
        
        # Определяем выходное имя файла
        if append_name:
            # Увеличиваем счетчик для этого полного относительного пути
            output_names[full_rel_path] += 1
            counter = output_names[full_rel_path]
            
            # Генерируем уникальное имя только если counter > 1
            if counter > 1:
                name, ext = os.path.splitext(base_name)
                output_filename = f"{name}({counter}){ext}"
                output_path = os.path.join(output_dir, rel_dir, output_filename)
            else:
                output_path = os.path.join(output_dir, rel_dir, base_name)
        else:
            output_path = os.path.join(output_dir, full_rel_path)
            
            # Проверяем, не обрабатывали ли мы уже файл с таким именем
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
    
    # Записываем пропущенные файлы (только если append_name = False)
    if not append_name and skipped_files:
        skipped_log_path = os.path.join(input_dir, "skipped_files.log")
        with open(skipped_log_path, 'w', encoding='utf-8') as f:
            f.write("Следующие файлы были пропущены из-за конфликта имен:\n")
            for file in skipped_files:
                f.write(f"{file}\n")
        print(f"\nЗаписаны пропущенные файлы в {skipped_log_path}")
    
    # Записываем файлы с ошибками
    if failed_files:
        error_log_path = os.path.join(input_dir, "failed_files.log")
        with open(error_log_path, 'w', encoding='utf-8') as f:
            f.write("Следующие файлы не удалось обработать из-за ошибок:\n")
            for file in failed_files:
                f.write(f"{file}\n")
        print(f"\nЗаписаны файлы с ошибками в {error_log_path}")
    
    print(f"\nГотово! Успешно обработано {success_count} файлов.")

if __name__ == "__main__":
    asyncio.run(main())