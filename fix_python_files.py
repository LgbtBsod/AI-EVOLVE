import os
import re
import ast
import tokenize
import io
from collections import defaultdict
from typing import List, Tuple
import shutil
import tempfile

def fix_corrupted_files(content):
    """Исправляет сильно поврежденные файлы с критическими ошибками."""
    # Удаляем невидимые символы и мусор
    content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content)
    
    # Исправляем разорванные строки
    content = re.sub(r'\\\s*\n\s*', ' ', content)
    
    # Удаляем лишние пробелы в начале строк
    content = re.sub(r'^\s+', '', content, flags=re.MULTILINE)
    
    # Исправляем разорванные комментарии
    content = re.sub(r'#\s*\n\s*', '# ', content)
    
    # Удаляем пустые строки в начале файла
    content = re.sub(r'^\n+', '', content)
    
    # Исправляем разорванные строки с кавычками
    content = re.sub(r'["\']\s*\n\s*["\']', '""', content)
    
    return content

def fix_broken_imports(content):
    """Исправляет поврежденные импорты и создает недостающие."""
    lines = content.splitlines()
    fixed_lines = []
    
    # Собираем все импорты
    imports = []
    other_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(('import ', 'from ')) and 'import' in stripped:
            imports.append(line)
        else:
            other_lines.append(line)
    
    # Исправляем поврежденные импорты
    fixed_imports = []
    for imp in imports:
        # Убираем лишние пробелы
        imp = re.sub(r'\s+', ' ', imp.strip())
        
        # Исправляем разорванные импорты
        if imp.count('import') > 1:
            # Разбиваем на отдельные импорты
            parts = imp.split('import')
            for i, part in enumerate(parts[1:], 1):
                if part.strip():
                    fixed_imports.append(f"import{part.strip()}")
        else:
            fixed_imports.append(imp)
    
    # Добавляем базовые импорты если их нет
    basic_imports = [
        'import os',
        'import sys',
        'import re',
        'import time',
        'import logging',
        'from typing import *',
        'from dataclasses import dataclass, field',
        'from enum import Enum',
        'from pathlib import Path'
    ]
    
    existing_imports = set()
    for imp in fixed_imports:
        for basic in basic_imports:
            if basic.split()[1] in imp:
                existing_imports.add(basic.split()[1])
    
    for basic in basic_imports:
        if basic.split()[1] not in existing_imports:
            fixed_imports.append(basic)
    
    # Сортируем импорты
    fixed_imports.sort()
    
    # Собираем результат
    fixed_lines.extend(fixed_imports)
    fixed_lines.append('')  # Пустая строка после импортов
    fixed_lines.extend(other_lines)
    
    return '\n'.join(fixed_lines)

def fix_broken_classes_and_functions(content):
    """Исправляет поврежденные классы и функции."""
    lines = content.splitlines()
    fixed_lines = []
    i = 0
    n = len(lines)
    
    while i < n:
        line = lines[i]
        stripped = line.strip()
        
        # Проверяем начало класса или функции
        if re.match(r'^(class|def)\s+\w+', stripped):
            indent = len(line) - len(line.lstrip())
            fixed_lines.append(line)
            i += 1
            
            # Собираем содержимое
            content_lines = []
            while i < n:
                next_line = lines[i]
                next_indent = len(next_line) - len(next_line.lstrip())
                
                # Если встретили строку с тем же или меньшим отступом и она не пустая
                if next_indent <= indent and next_line.strip() != '':
                    # Проверяем, не является ли это новым классом/функцией
                    if re.match(r'^(class|def)\s+\w+', next_line.strip()):
                        break
                    # Проверяем, не является ли это декоратором
                    if next_line.strip().startswith('@'):
                        break
                
                content_lines.append(next_line)
                i += 1
            
            # Проверяем, есть ли содержимое
            non_empty = [l for l in content_lines if l.strip() and not l.strip().startswith('#')]
            if not non_empty:
                fixed_lines.append(' ' * (indent + 4) + 'pass')
            else:
                fixed_lines.extend(content_lines)
        else:
            fixed_lines.append(line)
            i += 1
    
    return '\n'.join(fixed_lines)

def fix_broken_dataclasses(content):
    """Исправляет поврежденные dataclass определения."""
    # Исправляем разорванные dataclass
    content = re.sub(r'@dataclass\s*\n\s*class', '@dataclass\nclass', content)
    
    # Исправляем разорванные field()
    content = re.sub(r'field\s*\(\s*\n\s*\)', 'field()', content)
    
    # Исправляем разорванные типы
    content = re.sub(r'(\w+)\s*:\s*\n\s*(\w+)', r'\1: \2', content)
    
    # Исправляем разорванные значения по умолчанию
    content = re.sub(r'=\s*\n\s*([^,\n]+)', r'= \1', content)
    
    return content

def fix_broken_enums(content):
    """Исправляет поврежденные enum определения."""
    # Исправляем разорванные enum
    content = re.sub(r'class\s+(\w+)\s*\(\s*\n\s*Enum\s*\)', r'class \1(Enum)', content)
    
    # Исправляем разорванные значения enum
    content = re.sub(r'(\w+)\s*=\s*\n\s*([^,\n]+)', r'\1 = \2', content)
    
    return content

def fix_broken_strings(content):
    """Исправляет разорванные строки."""
    # Исправляем разорванные многострочные строки
    content = re.sub(r'"""\s*\n\s*([^"]*)\s*\n\s*"""', r'"""\1"""', content)
    content = re.sub(r"'''\s*\n\s*([^']*)\s*\n\s*'''", r"'''\1'''", content)
    
    # Исправляем разорванные обычные строки
    content = re.sub(r'(["\'])\s*\n\s*([^"\']*)\s*\n\s*\1', r'\1\2\1', content)
    
    return content

def fix_broken_brackets(content):
    """Исправляет поврежденные скобки и структуры."""
    lines = content.splitlines()
    fixed_lines = []
    
    for line in lines:
        # Исправляем разорванные скобки
        line = re.sub(r'\(\s*\n\s*', '(', line)
        line = re.sub(r'\s*\n\s*\)', ')', line)
        line = re.sub(r'\[\s*\n\s*', '[', line)
        line = re.sub(r'\s*\n\s*\]', ']', line)
        line = re.sub(r'{\s*\n\s*', '{', line)
        line = re.sub(r'\s*\n\s*}', '}', line)
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def create_backup_with_timestamp(filepath):
    """Создает резервную копию файла с временной меткой."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Используем директорию .backups для резервных копий
    backup_dir = ".backups"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    # Создаем имя файла с относительным путем
    relative_path = os.path.relpath(filepath, '.')
    safe_filename = relative_path.replace('/', '_').replace('\\', '_')
    backup_filename = f"{safe_filename}.backup_{timestamp}"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    try:
        shutil.copy2(filepath, backup_path)
        return backup_path
    except Exception as e:
        print(f"    ❌ Ошибка создания резервной копии: {e}")
        return None

def emergency_repair(content):
    """Экстренный ремонт сильно поврежденного файла."""
    print("    🚨 Применяю экстренный ремонт...")
    
    # Применяем все исправления в правильном порядке
    content = fix_corrupted_files(content)
    content = fix_broken_strings(content)
    content = fix_broken_brackets(content)
    content = fix_broken_dataclasses(content)
    content = fix_broken_enums(content)
    content = fix_broken_imports(content)
    content = fix_broken_classes_and_functions(content)
    
    # Если файл все еще невалиден, применяем агрессивные исправления
    if not validate_python_syntax(content):
        print("    🔥 Применяю агрессивные исправления...")
        content = aggressive_repair(content)
    
    return content

def aggressive_repair(content):
    """Агрессивный ремонт для критически поврежденных файлов."""
    print("    💥 Агрессивный ремонт...")
    
    # Удаляем все проблемные символы
    content = re.sub(r'[^\x20-\x7E\n\t]', '', content)
    
    # Исправляем разорванные строки более агрессивно
    lines = content.splitlines()
    fixed_lines = []
    
    for line in lines:
        # Убираем лишние пробелы в начале и конце
        line = line.strip()
        
        # Исправляем очевидные ошибки
        line = re.sub(r'[^\x20-\x7E]', '', line)  # Только печатные символы
        
        # Добавляем исправленную строку
        if line:
            fixed_lines.append(line)
    
    # Собираем обратно
    content = '\n'.join(fixed_lines)
    
    # Добавляем базовую структуру если файл пустой
    if not content.strip():
        content = '''# Восстановленный файл
# Этот файл был критически поврежден и восстановлен автоматически

def main():
    """Основная функция"""
    pass

if __name__ == "__main__":
    main()
'''
    
    return content

def apply_preventive_fixes(content):
    """Применяет профилактические исправления для предотвращения проблем в будущем."""
    print("    🛡️ Применяю профилактические исправления...")
    
    # Добавляем защитные импорты
    if 'from typing import *' not in content:
        content = 'from typing import *\n' + content
    
    # Добавляем базовые импорты если их нет
    basic_imports = [
        'import os',
        'import sys',
        'import logging',
        'from pathlib import Path'
    ]
    
    for imp in basic_imports:
        if imp not in content:
            content = imp + '\n' + content
    
    # Добавляем пустую строку после импортов
    content = re.sub(r'(import .*)\n(?!\n)', r'\1\n\n', content)
    
    # Нормализуем окончания строк
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    
    # Убираем лишние пустые строки в конце файла
    content = content.rstrip() + '\n'
    
    return content

def create_file_integrity_check(filepath):
    """Создает файл для проверки целостности в будущем."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Создаем хеш содержимого
        import hashlib
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        
        # Создаем файл проверки
        check_file = filepath + '.integrity'
        with open(check_file, 'w', encoding='utf-8') as f:
            f.write(f"# Файл проверки целостности для {filepath}\n")
            f.write(f"# Создан: {__import__('datetime').datetime.now()}\n")
            f.write(f"# MD5 хеш: {content_hash}\n")
            f.write(f"# Размер: {len(content)} символов\n")
        
        return True
    except Exception as e:
        print(f"    ⚠️ Не удалось создать файл проверки целостности: {e}")
        return False

def cleanup_backup_files():
    """Удаляет резервные копии после успешной проверки проекта."""
    print("🧹 Очистка резервных копий...")
    
    backup_files = []
    integrity_files = []
    
    # Ищем все файлы бэкапа и проверки целостности
    for root, _, files in os.walk('.'):
        for file in files:
            filepath = os.path.join(root, file)
            if file.endswith('.backup_'):
                backup_files.append(filepath)
            elif file.endswith('.integrity'):
                integrity_files.append(filepath)
    
    print(f"  📁 Найдено резервных копий: {len(backup_files)}")
    print(f"  📋 Найдено файлов проверки целостности: {len(integrity_files)}")
    
    if not backup_files:
        print("  ✅ Резервные копии не найдены")
        return
    
    # Проверяем целостность всех Python файлов
    python_files = []
    for root, _, files in os.walk('.'):
        for file in files:
            if file.endswith('.py') and not file.startswith('.'):
                filepath = os.path.join(root, file)
                python_files.append(filepath)
    
    print(f"  🔍 Проверяю целостность {len(python_files)} Python файлов...")
    
    healthy_files = 0
    problematic_files = []
    
    for filepath in python_files:
        try:
            # Проверяем синтаксис
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Пытаемся скомпилировать
            ast.parse(content)
            healthy_files += 1
            
        except Exception as e:
            problematic_files.append((filepath, str(e)))
    
    print(f"  ✅ Здоровых файлов: {healthy_files}")
    print(f"  ❌ Проблемных файлов: {len(problematic_files)}")
    
    # Если все файлы здоровы, удаляем резервные копии
    if len(problematic_files) == 0:
        print("  🎉 Проект полностью здоров! Удаляю резервные копии...")
        
        deleted_backups = 0
        for backup_file in backup_files:
            try:
                os.remove(backup_file)
                deleted_backups += 1
            except Exception as e:
                print(f"    ⚠️ Не удалось удалить {backup_file}: {e}")
        
        print(f"  ✅ Удалено резервных копий: {deleted_backups}")
        
        # Также удаляем файлы проверки целостности
        deleted_integrity = 0
        for integrity_file in integrity_files:
            try:
                os.remove(integrity_file)
                deleted_integrity += 1
            except Exception as e:
                print(f"    ⚠️ Не удалось удалить {integrity_file}: {e}")
        
        print(f"  ✅ Удалено файлов проверки целостности: {deleted_integrity}")
        
    else:
        print("  ⚠️ Проект имеет проблемы, резервные копии сохранены")
        print("  📋 Список проблемных файлов:")
        for filepath, error in problematic_files[:5]:  # Показываем первые 5
            print(f"    - {filepath}: {error}")
        if len(problematic_files) > 5:
            print(f"    ... и еще {len(problematic_files) - 5} файлов")

def smart_backup_management():
    """Умное управление резервными копиями с автоматической очисткой."""
    print("🧠 Умное управление резервными копиями...")
    
    # Создаем директорию для резервных копий если её нет
    backup_dir = ".backups"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        print(f"  📁 Создана директория для резервных копий: {backup_dir}")
    
    # Перемещаем существующие резервные копии в специальную директорию
    moved_backups = 0
    for root, _, files in os.walk('.'):
        for file in files:
            if file.endswith('.backup_') and root != backup_dir:
                old_path = os.path.join(root, file)
                new_path = os.path.join(backup_dir, file)
                try:
                    shutil.move(old_path, new_path)
                    moved_backups += 1
                except Exception as e:
                    print(f"    ⚠️ Не удалось переместить {old_path}: {e}")
    
    if moved_backups > 0:
        print(f"  📦 Перемещено резервных копий в {backup_dir}: {moved_backups}")
    
    return backup_dir

def fix_indentation(content):
    """Заменяет табы на 4 пробела и нормализует отступы."""
    lines = content.splitlines()
    fixed_lines = []
    
    for line in lines:
        fixed_line = line.replace('\t', '    ')
        stripped = fixed_line.lstrip()
        if stripped:
            indent = len(fixed_line) - len(stripped)
            if indent % 4 != 0:
                new_indent = (indent // 4) * 4
                fixed_line = ' ' * new_indent + stripped
        fixed_lines.append(fixed_line)
    
    return '\n'.join(fixed_lines)

def fix_try_except(content):
    """Исправляет голые except и пустые блоки."""
    lines = content.splitlines()
    fixed_lines = []
    i = 0
    n = len(lines)
    
    while i < n:
        line = lines[i]
        stripped = line.strip()
        
        if stripped.startswith('try:'):
            # Найдем блок try
            try_indent = len(line) - len(line.lstrip())
            fixed_lines.append(line)
            i += 1
            
            # Собираем весь блок try
            try_block = []
            while i < n:
                next_line = lines[i]
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_indent <= try_indent and next_line.strip() != '':
                    break
                try_block.append(next_line)
                i += 1
            
            # Обрабатываем блок except
            if i < n and lines[i].strip().startswith('except'):
                except_line = lines[i]
                except_stripped = except_line.strip()
                except_indent = len(except_line) - len(except_line.lstrip())
                
                if except_stripped == 'except:':
                    fixed_lines.append(' ' * except_indent + 'except Exception:')
                else:
                    fixed_lines.append(except_line)
                i += 1
                
                # Собираем блок except
                except_block = []
                while i < n:
                    next_line = lines[i]
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_indent <= except_indent and next_line.strip() != '':
                        break
                    except_block.append(next_line)
                    i += 1
                
                # Проверяем, пуст ли блок except
                non_empty = [l for l in except_block if l.strip() and not l.strip().startswith('#')]
                if not non_empty:
                    fixed_lines.append(' ' * (except_indent + 4) + 'pass')
                else:
                    fixed_lines.extend(except_block)
            else:
                fixed_lines.extend(try_block)
        else:
            fixed_lines.append(line)
            i += 1
    
    return '\n'.join(fixed_lines)

def fix_empty_blocks(content):
    """Удаляет пустые блоки и добавляет pass где необходимо."""
    lines = content.splitlines()
    fixed_lines = []
    i = 0
    n = len(lines)
    
    while i < n:
        line = lines[i]
        stripped = line.strip()
        
        # Обработка блоков, требующих содержимого
        block_keywords = ['if', 'elif', 'else:', 'for', 'while', 'with', 'def', 'class']
        if any(stripped.startswith(keyword) for keyword in block_keywords):
            indent = len(line) - len(line.lstrip())
            fixed_lines.append(line)
            i += 1
            
            # Собираем содержимое блока
            block_content = []
            while i < n:
                next_line = lines[i]
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_indent <= indent and next_line.strip() != '':
                    break
                block_content.append(next_line)
                i += 1
            
            # Проверяем, пуст ли блок
            non_empty = [l for l in block_content if l.strip() and not l.strip().startswith('#')]
            if not non_empty:
                fixed_lines.append(' ' * (indent + 4) + 'pass')
            else:
                fixed_lines.extend(block_content)
        else:
            fixed_lines.append(line)
            i += 1
    
    return '\n'.join(fixed_lines)

def fix_redundant_else(content):
    """Удаляет лишние блоки else в try-except."""
    lines = content.splitlines()
    fixed_lines = []
    i = 0
    n = len(lines)
    
    while i < n:
        line = lines[i]
        stripped = line.strip()
        
        if stripped == 'else:':
            indent = len(line) - len(line.lstrip())
            # Проверяем предыдущие строки на наличие except
            has_except = False
            for j in range(i-1, max(i-10, -1), -1):
                prev_line = lines[j]
                prev_indent = len(prev_line) - len(prev_line.lstrip())
                if prev_indent < indent and 'except' in prev_line:
                    has_except = True
                    break
            
            if has_except:
                # Собираем содержимое блока else
                j = i + 1
                block_content = []
                while j < n:
                    next_line = lines[j]
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_indent <= indent and next_line.strip() != '':
                        break
                    block_content.append(next_line)
                    j += 1
                
                # Проверяем, пуст ли блок else
                non_empty = [l for l in block_content if l.strip() and not l.strip().startswith('#')]
                if not non_empty:
                    i = j  # Пропускаем блок else
                    continue
                else:
                    fixed_lines.append(line)
                    fixed_lines.extend(block_content)
                    i = j
                    continue
            else:
                fixed_lines.append(line)
                i += 1
        else:
            fixed_lines.append(line)
            i += 1
    
    return '\n'.join(fixed_lines)

def fix_imports(content):
    """Сортирует импорты и группирует по типам."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return content

    imports = defaultdict(list)
    import_nodes = []
    last_import_line = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if hasattr(node, 'lineno') and node.lineno > last_import_line:
                import_nodes.append(node)
                last_import_line = node.lineno

    for node in import_nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports['standard'].append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            for alias in node.names:
                imports['third_party'].append(f"from {module} import {alias.name}")

    sorted_imports = []
    for category in ['standard', 'third_party']:
        if imports[category]:
            sorted_imports.extend(sorted(set(imports[category])))
            sorted_imports.append('')

    if not import_nodes:
        return content

    lines = content.splitlines()
    start_line = min(node.lineno for node in import_nodes) - 1
    end_line = max(node.end_lineno for node in import_nodes if hasattr(node, 'end_lineno')) - 1

    new_content = (
        '\n'.join(lines[:start_line]) + '\n' +
        '\n'.join(sorted_imports) +
        '\n'.join(lines[end_line + 1:])
    )
    
    return new_content

def fix_syntax_errors(content):
    """Исправляет распространенные синтаксические ошибки."""
    # Исправляем опечатки в ключевых словах
    replacements = {
        r'imp or t': 'import',
        r'logg in g': 'logging',
        r' in sert': 'insert',
        r' in g': 'ing',
        r' in ': 'in ',
        r'f or mat': 'format',
        r'f or ': 'for ',
        r' and ': 'and ',
        r' is ': 'is ',
        r'pr in t': 'print',
        r'==': '=',
        r'= =': '==',
        r': =': ':=',
        r'=:': '=',
        r' % ': '%',
        r' %': '%',
        r'% ': '%',
    }
    
    for pattern, replacement in replacements.items():
        content = re.sub(pattern, replacement, content)
    
    # Добавление двоеточий после управляющих конструкций
    content = re.sub(r'(if|elif|else|for|while|with|def|class)\s*(\([^)]*\))?\s*$(?=\s*[^#\s])', r'\1\2:', content, flags=re.MULTILINE)
    
    # Удаление лишних запятых в вызовах функций
    content = re.sub(r',(\s*[\]\}])', r'\1', content)
    
    return content

def validate_python_syntax(content):
    """Проверяет, является ли содержимое валидным Python-кодом."""
    try:
        ast.parse(content)
        return True
    except SyntaxError as e:
        print(f"    Синтаксическая ошибка: {e}")
        return False
    except Exception as e:
        print(f"    Неожиданная ошибка при проверке синтаксиса: {e}")
        return False

def create_backup(filepath):
    """Создает резервную копию файла."""
    backup_path = filepath + '.bak'
    try:
        with open(filepath, 'r', encoding='utf-8') as src:
            with open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(src.read())
        return True
    except Exception:
        return False

def process_file(filepath):
    """Обрабатывает один Python-файл."""
    print(f"Обрабатываю файл: {filepath}")
    
    # Проверяем, не является ли файл самим скриптом
    if os.path.abspath(filepath) == os.path.abspath(__file__):
        print(f"Пропуск самого себя: {filepath}")
        return
        
    # Создаем резервную копию с временной меткой
    backup_path = create_backup_with_timestamp(filepath)
    if not backup_path:
        print(f"  ❌ Не удалось создать резервную копию: {filepath}")
        return
        
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  ❌ Ошибка чтения файла {filepath}: {e}")
        return

    original_content = content
    print(f"  📄 Размер файла: {len(content)} символов")

    # Проверяем исходный синтаксис
    original_valid = validate_python_syntax(content)
    print(f"  🔍 Исходный синтаксис: {'✅ валиден' if original_valid else '❌ НЕ ВАЛИДЕН'}")
    
    # Если файл сильно поврежден, применяем экстренный ремонт
    if not original_valid:
        print("  🚨 Файл сильно поврежден, применяю экстренный ремонт...")
        content = emergency_repair(content)
        
        # Проверяем результат экстренного ремонта
        emergency_valid = validate_python_syntax(content)
        if emergency_valid:
            print("  ✅ Экстренный ремонт успешен!")
        else:
            print("  ⚠️ Экстренный ремонт не помог, применяю стандартные исправления...")
    
    # Последовательное применение стандартных исправлений
    print("  🔧 Применяю стандартные исправления...")
    content = fix_indentation(content)
    content = fix_syntax_errors(content)
    content = fix_try_except(content)
    content = fix_empty_blocks(content)
    content = fix_redundant_else(content)
    content = fix_imports(content)
    
    # Применяем профилактические исправления
    content = apply_preventive_fixes(content)

    # Проверяем итоговый синтаксис
    final_valid = validate_python_syntax(content)
    print(f"  🔍 Итоговый синтаксис: {'✅ валиден' if final_valid else '❌ НЕ ВАЛИДЕН'}")
    
    if not final_valid and original_valid:
        print(f"  ⚠️ ВНИМАНИЕ: Исправления сломали синтаксис: {filepath}. Восстанавливаем из резервной копии.")
        # Восстанавливаем из резервной копии
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_content = f.read()
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(backup_content)
            print(f"  ✅ Файл восстановлен из резервной копии")
        except Exception as e:
            print(f"  ❌ Ошибка восстановления из резервной копии: {filepath}: {e}")
        return

    # Проверяем, действительно ли файл исправлен
    if content != original_content:
        # Проверяем синтаксис исправленного содержимого
        if final_valid:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"  ✅ Исправлен: {filepath}")
            except Exception as e:
                print(f"  ❌ Ошибка записи в файл {filepath}: {e}")
        else:
            print(f"  ⚠️ Файл изменен, но синтаксис невалиден: {filepath}")
            print(f"  🔄 Восстанавливаю из резервной копии...")
            try:
                with open(backup_path, 'r', encoding='utf-8') as f:
                    backup_content = f.read()
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(backup_content)
                print(f"  ✅ Файл восстановлен из резервной копии")
            except Exception as e:
                print(f"  ❌ Ошибка восстановления: {e}")
    else:
        print(f"  ➖ Без изменений: {filepath}")
        
    # Сохраняем резервную копию для безопасности
    print(f"  💾 Резервная копия сохранена: {backup_path}")
    
    # Создаем файл проверки целостности только для валидных файлов
    if final_valid:
        create_file_integrity_check(filepath)

def main():
    """Основная функция для обхода директорий."""
    current_dir = os.getcwd()
    print(f"Начинаю обработку Python-файлов в директории: {current_dir}")
    
    # Настраиваем умное управление резервными копиями
    backup_dir = smart_backup_management()
    
    python_files = []
    for root, _, files in os.walk(current_dir):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                python_files.append(filepath)
    
    print(f"Найдено Python-файлов: {len(python_files)}")
    
    for i, filepath in enumerate(python_files, 1):
        print(f"\n[{i}/{len(python_files)}] ", end="")
        process_file(filepath)
    
    print(f"\nОбработка завершена. Обработано файлов: {len(python_files)}")
    
    # После обработки всех файлов проверяем здоровье проекта
    print("\n" + "=" * 50)
    print("🔍 Проверка здоровья проекта...")
    
    # Автоматическая очистка резервных копий если проект здоров
    cleanup_backup_files()

def setup_file_monitoring():
    """Настраивает мониторинг файлов для предотвращения повреждений."""
    print("🔍 Настройка мониторинга файлов...")
    
    # Создаем файл с инструкциями по мониторингу
    monitor_file = "file_monitoring_guide.md"
    with open(monitor_file, 'w', encoding='utf-8') as f:
        f.write("""# Руководство по мониторингу файлов

## Автоматическая защита от повреждений

### 1. Регулярные проверки
- Запускайте `python fix_python_files.py` после каждого сеанса редактирования
- Проверяйте файлы `.integrity` для выявления изменений

### 2. Предотвращение проблем
- Всегда используйте резервные копии перед редактированием
- Проверяйте синтаксис после внесения изменений
- Используйте `python -m py_compile <файл>` для проверки

### 3. Восстановление
- При повреждении используйте файлы в директории `.backups/`
- Запускайте экстренный ремонт для критических повреждений

### 4. Мониторинг в реальном времени
- Следите за размером файлов
- Проверяйте хеши в файлах `.integrity`
- Обращайте внимание на предупреждения Python

### 5. Умное управление резервными копиями
- Резервные копии автоматически сохраняются в `.backups/`
- При здоровом состоянии проекта бэкапы автоматически удаляются
- Ручная очистка: `python -c "from fix_python_files import cleanup_backup_files; cleanup_backup_files()"`
""")
    
    print(f"✅ Создан файл руководства: {monitor_file}")

def manual_cleanup():
    """Функция для ручной очистки резервных копий."""
    print("🧹 Ручная очистка резервных копий...")
    cleanup_backup_files()

def show_backup_status():
    """Показывает статус резервных копий."""
    print("📊 Статус резервных копий...")
    
    backup_dir = ".backups"
    if not os.path.exists(backup_dir):
        print("  📁 Директория резервных копий не найдена")
        return
    
    backup_files = []
    for file in os.listdir(backup_dir):
        if file.endswith('.backup_'):
            backup_files.append(file)
    
    if not backup_files:
        print("  ✅ Резервные копии не найдены")
        return
    
    print(f"  📁 Найдено резервных копий: {len(backup_files)}")
    print("  📋 Список резервных копий:")
    
    # Группируем по исходным файлам
    file_groups = {}
    for backup_file in backup_files:
        # Извлекаем имя исходного файла
        parts = backup_file.split('.backup_')
        if len(parts) >= 2:
            original_file = parts[0].replace('_', '/').replace('_', '\\')
            timestamp = parts[1]
            if original_file not in file_groups:
                file_groups[original_file] = []
            file_groups[original_file].append(timestamp)
    
    for original_file, timestamps in file_groups.items():
        print(f"    📄 {original_file}: {len(timestamps)} версий")
        for timestamp in sorted(timestamps)[-3:]:  # Показываем последние 3
            print(f"      - {timestamp}")
        if len(timestamps) > 3:
            print(f"      ... и еще {len(timestamps) - 3} версий")
    
    print(f"\n  💡 Для очистки используйте: cleanup_backup_files()")

def force_cleanup_all_backups():
    """Принудительно удаляет ВСЕ резервные копии в проекте."""
    print("🧹 ПРИНУДИТЕЛЬНАЯ ОЧИСТКА ВСЕХ РЕЗЕРВНЫХ КОПИЙ...")
    print("⚠️  ВНИМАНИЕ: Эта операция удалит ВСЕ резервные копии!")
    
    # Ищем все файлы бэкапа в проекте
    all_backup_files = []
    all_integrity_files = []
    
    for root, _, files in os.walk('.'):
        for file in files:
            filepath = os.path.join(root, file)
            if file.endswith('.backup_') or file.endswith('.bak'):
                all_backup_files.append(filepath)
            elif file.endswith('.integrity'):
                all_integrity_files.append(filepath)
    
    print(f"  📁 Найдено резервных копий: {len(all_backup_files)}")
    print(f"  📋 Найдено файлов проверки целостности: {len(all_integrity_files)}")
    
    if not all_backup_files and not all_integrity_files:
        print("  ✅ Резервные копии не найдены")
        return
    
    # Показываем что будет удалено
    print("\n  📋 Файлы для удаления:")
    for backup_file in all_backup_files[:10]:  # Показываем первые 10
        print(f"    - {backup_file}")
    if len(all_backup_files) > 10:
        print(f"    ... и еще {len(all_backup_files) - 10} файлов")
    
    # Запрашиваем подтверждение
    response = input("\n  ❓ Продолжить удаление ВСЕХ резервных копий? (yes/NO): ").strip().lower()
    if response != 'yes':
        print("  ❌ Операция отменена пользователем")
        return
    
    # Удаляем все резервные копии
    deleted_backups = 0
    deleted_integrity = 0
    
    print("\n  🗑️ Удаляю резервные копии...")
    for backup_file in all_backup_files:
        try:
            os.remove(backup_file)
            deleted_backups += 1
            print(f"    ✅ Удален: {backup_file}")
        except Exception as e:
            print(f"    ❌ Ошибка удаления {backup_file}: {e}")
    
    print("\n  🗑️ Удаляю файлы проверки целостности...")
    for integrity_file in all_integrity_files:
        try:
            os.remove(integrity_file)
            deleted_integrity += 1
            print(f"    ✅ Удален: {integrity_file}")
        except Exception as e:
            print(f"    ❌ Ошибка удаления {integrity_file}: {e}")
    
    # Удаляем пустые директории .backups
    backup_dirs = ['.backups']
    for backup_dir in backup_dirs:
        if os.path.exists(backup_dir):
            try:
                os.rmdir(backup_dir)
                print(f"    ✅ Удалена пустая директория: {backup_dir}")
            except Exception:
                pass  # Директория не пустая
    
    print(f"\n  🎉 Очистка завершена!")
    print(f"  ✅ Удалено резервных копий: {deleted_backups}")
    print(f"  ✅ Удалено файлов проверки целостности: {deleted_integrity}")
    print(f"  💡 Теперь проект чист от старых резервных копий!")

def cleanup_old_backups_by_age(days_old=7):
    """Удаляет резервные копии старше указанного количества дней."""
    print(f"🧹 Очистка резервных копий старше {days_old} дней...")
    
    from datetime import datetime, timedelta
    cutoff_date = datetime.now() - timedelta(days=days_old)
    
    all_backup_files = []
    for root, _, files in os.walk('.'):
        for file in files:
            if file.endswith('.backup_') or file.endswith('.bak'):
                filepath = os.path.join(root, file)
                try:
                    file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if file_time < cutoff_date:
                        all_backup_files.append((filepath, file_time))
                except Exception:
                    pass
    
    if not all_backup_files:
        print("  ✅ Старые резервные копии не найдены")
        return
    
    print(f"  📁 Найдено старых резервных копий: {len(all_backup_files)}")
    
    # Сортируем по дате
    all_backup_files.sort(key=lambda x: x[1])
    
    # Показываем что будет удалено
    print("  📋 Старые файлы для удаления:")
    for backup_file, file_time in all_backup_files[:10]:
        age_days = (datetime.now() - file_time).days
        print(f"    - {backup_file} (возраст: {age_days} дней)")
    
    if len(all_backup_files) > 10:
        print(f"    ... и еще {len(all_backup_files) - 10} файлов")
    
    # Запрашиваем подтверждение
    response = input(f"\n  ❓ Удалить резервные копии старше {days_old} дней? (y/N): ").strip().lower()
    if response != 'y':
        print("  ❌ Операция отменена пользователем")
        return
    
    # Удаляем старые резервные копии
    deleted_count = 0
    for backup_file, file_time in all_backup_files:
        try:
            os.remove(backup_file)
            deleted_count += 1
            age_days = (datetime.now() - file_time).days
            print(f"    ✅ Удален: {backup_file} (возраст: {age_days} дней)")
        except Exception as e:
            print(f"    ❌ Ошибка удаления {backup_file}: {e}")
    
    print(f"\n  🎉 Очистка завершена!")
    print(f"  ✅ Удалено старых резервных копий: {deleted_count}")

if __name__ == '__main__':
    print("🚀 Запуск улучшенной утилиты исправления Python файлов")
    print("=" * 60)
    
    # Настраиваем мониторинг
    setup_file_monitoring()
    
    # Запускаем основную обработку
    main()
    
    print("\n" + "=" * 60)
    print("🎉 Обработка завершена!")
    
    # Показываем финальный статус резервных копий
    show_backup_status()
    
    print("\n💡 Для предотвращения проблем в будущем:")
    print("   - Регулярно запускайте эту утилиту")
    print("   - Резервные копии автоматически управляются")
    print("   - При здоровом проекте бэкапы удаляются")
    print("   - Ручная очистка: manual_cleanup()")
    
    # Предлагаем очистку старых резервных копий
    print("\n🧹 Очистка старых резервных копий:")
    print("   - force_cleanup_all_backups() - удалить ВСЕ бэкапы")
    print("   - cleanup_old_backups_by_age(7) - удалить бэкапы старше 7 дней")
    print("   - show_backup_status() - показать статус бэкапов")
    
    print("=" * 60)