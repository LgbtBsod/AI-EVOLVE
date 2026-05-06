import os
import sys
from pathlib import Path
import datetime
import logging
from typing import List, Tuple, Optional, Dict, Any
import shutil

# Константы
MAX_DISPLAY_PATH_LENGTH = 50
MAX_ERRORS_DISPLAY = 5
DEFAULT_ENCODINGS = ['utf-8', 'cp1251', 'latin-1', 'iso-8859-1']
HIDDEN_DIR_PREFIXES = ['.', '__']

def setup_logging() -> None:
    """Настройка логирования"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('code_to_txt.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

def get_safe_directories() -> List[Tuple[str, str]]:
    """Получить безопасные директории для выбора"""
    directories = []
    
    try:
        # Получаем рабочую директорию (не system32)
        if os.getcwd() == os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'System32'):
            # Если запущено из system32, переходим в Desktop
            desktop_path = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop')
            if os.path.exists(desktop_path):
                os.chdir(desktop_path)
                logging.info(f"Изменена рабочая директория на: {desktop_path}")
        
        current_dir = Path.cwd().resolve()
        
        # Добавляем текущую директорию
        directories.append(("Текущая директория", str(current_dir)))
        
        # Добавляем родительскую директорию
        parent_dir = current_dir.parent
        if parent_dir.exists() and parent_dir != current_dir:
            directories.append(("Родительская директория", str(parent_dir)))
        
        # Добавляем поддиректории текущей папки
        try:
            for item in current_dir.iterdir():
                if item.is_dir() and not any(item.name.startswith(prefix) for prefix in HIDDEN_DIR_PREFIXES):
                    directories.append((item.name, str(item)))
        except PermissionError:
            logging.warning(f"Нет прав доступа к директории: {current_dir}")
        
        # Добавляем стандартные пути
        home_dir = Path.home()
        if home_dir.exists():
            directories.append(("Домашняя папка", str(home_dir)))
        
        desktop_dir = home_dir / "Desktop"
        if desktop_dir.exists():
            directories.append(("Рабочий стол", str(desktop_dir)))
        
        documents_dir = home_dir / "Documents"
        if documents_dir.exists():
            directories.append(("Документы", str(documents_dir)))
            
    except Exception as e:
        logging.error(f"Ошибка при получении списка директорий: {e}")
        print(f"Ошибка при получении списка директорий: {e}")
    
    return directories

def get_available_directories(start_path: str = ".") -> List[Tuple[str, str]]:
    """Получить список доступных директорий для выбора"""
    return get_safe_directories()

def display_directory_menu(directories: List[Tuple[str, str]]) -> None:
    """Отобразить меню выбора директории"""
    print("\n" + "="*60)
    print("ДОСТУПНЫЕ ДИРЕКТОРИИ:")
    print("="*60)
    
    for i, (name, path) in enumerate(directories, 1):
        # Обрезаем длинные пути для лучшего отображения
        display_path = path
        if len(path) > MAX_DISPLAY_PATH_LENGTH:
            display_path = "..." + path[-(MAX_DISPLAY_PATH_LENGTH-3):]
        print(f"{i:2d}. {name:<20} | {display_path}")
    
    print("="*60)
    print("0. Ввести путь вручную")
    print("q. Выход")
    print("="*60)

def validate_directory_path(path: str) -> bool:
    """Проверить валидность пути к директории"""
    try:
        path_obj = Path(path)
        return path_obj.exists() and path_obj.is_dir()
    except (OSError, ValueError):
        return False

def get_user_choice(directories: List[Tuple[str, str]]) -> Optional[str]:
    """Получить выбор пользователя"""
    while True:
        try:
            choice = input("\nВыберите номер директории (или введите 'q' для выхода): ").strip().lower()
            
            if choice == 'q':
                return None
            elif choice == '0':
                manual_path = input("Введите путь к директории вручную: ").strip()
                if not manual_path:
                    print("Путь не может быть пустым. Попробуйте снова.")
                    continue
                
                # Проверяем валидность пути
                if not validate_directory_path(manual_path):
                    print(f"Директория не существует или недоступна: {manual_path}")
                    continue
                
                return manual_path
            
            choice_num = int(choice)
            if 1 <= choice_num <= len(directories):
                return directories[choice_num - 1][1]
            else:
                print(f"Пожалуйста, введите число от 1 до {len(directories)}")
                
        except ValueError:
            print("Пожалуйста, введите корректное число")
        except KeyboardInterrupt:
            print("\n\nПрограмма прервана пользователем.")
            return None

def get_filter_options() -> Tuple[Optional[int], Optional[str], List[str]]:
    """Получить настройки фильтрации от пользователя"""
    print("\n" + "="*60)
    print("НАСТРОЙКИ ФИЛЬТРАЦИИ:")
    print("="*60)
    
    # Спрашиваем, нужна ли фильтрация
    use_filters = input("Использовать фильтрацию файлов? (y/n, Enter - нет): ").strip().lower()
    if use_filters not in ['y', 'yes', 'да', 'д']:
        print("Фильтрация отключена. Будут обработаны все Python файлы.")
        return None, None, []
    
    print("Настройка фильтров:")
    
    # Фильтр по размеру
    size_filter = input("Максимальный размер файла в КБ (Enter - без ограничений): ").strip()
    size_limit = None
    if size_filter:
        try:
            size_limit = int(size_filter) * 1024  # Конвертируем в байты
            if size_limit <= 0:
                print("Размер должен быть положительным числом. Фильтр по размеру отключен.")
                size_limit = None
        except ValueError:
            print("Неверный формат размера. Фильтр по размеру отключен.")
            size_limit = None
    
    # Фильтр по имени
    name_filter = input("Фильтр по имени файла (Enter - все файлы): ").strip()
    if not name_filter:
        name_filter = None
    
    # Фильтр по исключениям
    exclude_filter = input("Исключить файлы с именами (через запятую, Enter - без исключений): ").strip()
    exclude_list = []
    if exclude_filter:
        exclude_list = [name.strip() for name in exclude_filter.split(',') if name.strip()]
    
    return size_limit, name_filter, exclude_list

def should_process_file(file_path: str, file_name: str, size_limit: Optional[int], 
                       name_filter: Optional[str], exclude_list: List[str]) -> bool:
    """Определить, нужно ли обрабатывать файл"""
    # Проверка размера
    if size_limit:
        try:
            file_size = os.path.getsize(file_path)
            if file_size > size_limit:
                return False
        except (OSError, IOError) as e:
            logging.warning(f"Не удалось получить размер файла {file_path}: {e}")
            return False
    
    # Проверка имени файла
    if name_filter and name_filter.lower() not in file_name.lower():
        return False
    
    # Проверка исключений
    for exclude_name in exclude_list:
        if exclude_name.lower() in file_name.lower():
            return False
    
    return True

def count_python_files(directory: str, size_limit: Optional[int] = None, 
                      name_filter: Optional[str] = None, exclude_list: Optional[List[str]] = None) -> int:
    """Подсчитать количество Python файлов в директории с учетом фильтров"""
    count = 0
    exclude_list = exclude_list or []
    
    try:
        for root, dirs, files in os.walk(directory):
            # Пропускаем скрытые директории
            dirs[:] = [d for d in dirs if not any(d.startswith(prefix) for prefix in HIDDEN_DIR_PREFIXES)]
            
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    if should_process_file(file_path, file, size_limit, name_filter, exclude_list):
                        count += 1
    except PermissionError as e:
        logging.error(f"Нет прав доступа к директории {directory}: {e}")
    except Exception as e:
        logging.error(f"Ошибка при подсчете файлов в {directory}: {e}")
    
    return count

def try_read_file(file_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Попытаться прочитать файл с разными кодировками"""
    for encoding in DEFAULT_ENCODINGS:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
                return content, encoding
        except UnicodeDecodeError:
            continue
        except (OSError, IOError) as e:
            logging.warning(f"Ошибка чтения файла {file_path} с кодировкой {encoding}: {e}")
            continue
    
    return None, None

def write_file_header(out_f, file_path: str, relative_path: str, parent_folder: str, 
                     content: str, encoding: str) -> None:
    """Записать заголовок файла в выходной файл"""
    out_f.write(f"# Файл: {os.path.basename(file_path)}\n")
    out_f.write(f"# Путь: {relative_path}\n")
    out_f.write(f"# Папка: {parent_folder}\n")
    out_f.write(f"# Размер: {len(content)} символов\n")
    out_f.write(f"# Кодировка: {encoding}\n")
    out_f.write("-"*60 + "\n")

def write_error_header(out_f, file_path: str, relative_path: str, parent_folder: str) -> None:
    """Записать заголовок ошибки в выходной файл"""
    out_f.write(f"# Файл: {os.path.basename(file_path)}\n")
    out_f.write(f"# Путь: {relative_path}\n")
    out_f.write(f"# Папка: {parent_folder}\n")
    out_f.write(f"# ОШИБКА: Не удалось прочитать файл\n")
    out_f.write(f"# Возможные причины: повреждение файла, несовместимая кодировка\n")
    out_f.write("-"*60 + "\n\n")

def write_output_header(out_f, directory: str, total_files: int, size_limit: Optional[int], 
                       name_filter: Optional[str], exclude_list: List[str]) -> None:
    """Записать заголовок выходного файла"""
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out_f.write(f"# Содержимое Python файлов из директории: {directory}\n")
    out_f.write(f"# Дата создания: {current_time}\n")
    out_f.write(f"# Всего файлов: {total_files}\n")
    
    # Записываем информацию о фильтрах
    if size_limit or name_filter or exclude_list:
        out_f.write(f"# Применены фильтры:\n")
        if size_limit:
            out_f.write(f"# - Максимальный размер: {size_limit // 1024} КБ\n")
        if name_filter:
            out_f.write(f"# - Фильтр по имени: {name_filter}\n")
        if exclude_list:
            out_f.write(f"# - Исключения: {', '.join(exclude_list)}\n")
    
    out_f.write("="*80 + "\n\n")

def write_statistics(out_f, processed_files: int, total_size: int, errors: List[str], 
                    skipped_files: List[str]) -> None:
    """Записать статистику в конец файла"""
    out_f.write(f"\n# СТАТИСТИКА ОБРАБОТКИ\n")
    out_f.write(f"# Обработано файлов: {processed_files}\n")
    out_f.write(f"# Общий размер: {total_size:,} символов\n")
    out_f.write(f"# Ошибок: {len(errors)}\n")
    out_f.write(f"# Пропущено по фильтру: {len(skipped_files)}\n")

def process_py_files(directory: str, output_file: str, size_limit: Optional[int] = None, 
                    name_filter: Optional[str] = None, exclude_list: Optional[List[str]] = None) -> Tuple[bool, int, int, List[str], List[str]]:
    """Обработать Python файлы и сохранить их содержимое с учетом фильтров"""
    processed_files = 0
    total_size = 0
    errors = []
    skipped_files = []
    exclude_list = exclude_list or []
    
    try:
        with open(output_file, 'w', encoding='utf-8') as out_f:
            # Определяем общее количество файлов
            total_files = count_python_files(directory, size_limit, name_filter, exclude_list)
            
            # Записываем заголовок
            write_output_header(out_f, directory, total_files, size_limit, name_filter, exclude_list)
            
            for root, dirs, files in os.walk(directory):
                # Пропускаем скрытые директории
                dirs[:] = [d for d in dirs if not any(d.startswith(prefix) for prefix in HIDDEN_DIR_PREFIXES)]
                
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        
                        # Проверяем фильтры
                        if not should_process_file(file_path, file, size_limit, name_filter, exclude_list):
                            skipped_files.append(f"{os.path.relpath(file_path, directory)} - пропущен по фильтру")
                            continue
                        
                        relative_path = os.path.relpath(file_path, directory)
                        parent_folder = os.path.basename(root)
                        
                        # Пытаемся прочитать файл
                        content, used_encoding = try_read_file(file_path)
                        
                        if content is not None:
                            write_file_header(out_f, file_path, relative_path, parent_folder, content, used_encoding)
                            out_f.write(content)
                            out_f.write("\n\n" + "="*80 + "\n\n")
                            
                            processed_files += 1
                            total_size += len(content)
                        else:
                            write_error_header(out_f, file_path, relative_path, parent_folder)
                            errors.append(f"{relative_path} - не удалось прочитать")
            
            # Записываем статистику
            write_statistics(out_f, processed_files, total_size, errors, skipped_files)
                            
    except (OSError, IOError) as e:
        error_msg = f"Ошибка при создании выходного файла: {e}"
        logging.error(error_msg)
        print(error_msg)
        return False, 0, 0, [], []
    except Exception as e:
        error_msg = f"Неожиданная ошибка при обработке файлов: {e}"
        logging.error(error_msg)
        print(error_msg)
        return False, 0, 0, [], []
    
    return True, processed_files, total_size, errors, skipped_files

def get_output_filename(selected_path: str) -> str:
    """Получить имя выходного файла от пользователя"""
    default_output = f"python_files_{os.path.basename(selected_path)}.txt"
    output_filename = input(f"Имя выходного файла (по умолчанию: {default_output}): ").strip()
    
    if not output_filename:
        output_filename = default_output
    
    # Добавляем расширение .txt если его нет
    if not output_filename.endswith('.txt'):
        output_filename += '.txt'
    
    return output_filename

def display_processing_results(success: bool, processed: int, output_filename: str, 
                              total_size: int, errors: List[str], skipped_files: List[str]) -> None:
    """Отобразить результаты обработки"""
    if success:
        print(f"\n✅ Готово! Обработано файлов: {processed}")
        print(f"📁 Выходной файл: {output_filename}")
        print(f"📊 Общий размер: {total_size:,} символов")
        
        # Показываем размер файла
        if os.path.exists(output_filename):
            file_size = os.path.getsize(output_filename)
            print(f"💾 Размер файла: {file_size:,} байт")
        
        # Показываем ошибки если есть
        if errors:
            print(f"⚠️  Ошибок при обработке: {len(errors)}")
            for error in errors[:MAX_ERRORS_DISPLAY]:
                print(f"   - {error}")
            if len(errors) > MAX_ERRORS_DISPLAY:
                print(f"   ... и еще {len(errors) - MAX_ERRORS_DISPLAY} ошибок")
        
        # Показываем пропущенные файлы если есть
        if skipped_files:
            print(f"⏭️  Пропущено по фильтру: {len(skipped_files)}")
            for skipped in skipped_files[:MAX_ERRORS_DISPLAY]:
                print(f"   - {skipped}")
            if len(skipped_files) > MAX_ERRORS_DISPLAY:
                print(f"   ... и еще {len(skipped_files) - MAX_ERRORS_DISPLAY} файлов")
    else:
        print("❌ Произошла ошибка при обработке файлов.")

def process_single_directory() -> bool:
    """Обработать одну директорию. Возвращает True если нужно продолжить"""
    try:
        # Получаем список доступных директорий
        directories = get_available_directories()
        
        if not directories:
            print("Не удалось получить список директорий.")
            return False
        
        # Отображаем меню
        display_directory_menu(directories)
        
        # Получаем выбор пользователя
        selected_path = get_user_choice(directories)
        
        if selected_path is None:
            print("Программа завершена.")
            return False
        
        # Проверяем существование директории
        if not validate_directory_path(selected_path):
            print(f"Директория не существует или недоступна: {selected_path}")
            return True
        
        # Получаем настройки фильтрации
        size_limit, name_filter, exclude_list = get_filter_options()
        
        # Подсчитываем Python файлы с учетом фильтров
        file_count = count_python_files(selected_path, size_limit, name_filter, exclude_list)
        
        if file_count == 0:
            print(f"В директории {selected_path} не найдено Python файлов, соответствующих фильтрам.")
            return True
        
        print(f"\nНайдено Python файлов (с учетом фильтров): {file_count}")
        
        # Запрашиваем имя выходного файла
        output_filename = get_output_filename(selected_path)
        
        print(f"\nОбработка файлов из: {selected_path}")
        print(f"Выходной файл: {output_filename}")
        if size_limit or name_filter or exclude_list:
            print("Применены фильтры")
        print("Обработка...")
        
        # Обрабатываем файлы
        success, processed, total_size, errors, skipped_files = process_py_files(
            selected_path, output_filename, size_limit, name_filter, exclude_list
        )
        
        # Отображаем результаты
        display_processing_results(success, processed, output_filename, total_size, errors, skipped_files)
        
        # Спрашиваем о продолжении
        continue_choice = input("\nОбработать другую директорию? (y/n): ").strip().lower()
        return continue_choice in ['y', 'yes', 'да', 'д']
        
    except KeyboardInterrupt:
        print("\n\nПрограмма прервана пользователем.")
        return False
    except Exception as e:
        error_msg = f"Произошла неожиданная ошибка: {e}"
        logging.error(error_msg)
        print(f"\n{error_msg}")
        return True

def main() -> None:
    """Основная функция программы"""
    # Настраиваем логирование
    setup_logging()
    
    print("="*60)
    print("ПРОГРАММА ДЛЯ КОНВЕРТАЦИИ PYTHON ФАЙЛОВ В ТЕКСТ")
    print("="*60)
    
    while process_single_directory():
        pass
    
    print("Программа завершена.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nПрограмма завершена.")
    except Exception as e:
        error_msg = f"Критическая ошибка: {e}"
        logging.critical(error_msg)
        print(f"\n{error_msg}")
        input("Нажмите Enter для выхода...")