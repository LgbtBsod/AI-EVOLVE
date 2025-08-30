import os
import re
import ast
import tokenize
import io
from collections import defaultdict
from typing import List, Tuple
import shutil
import tempfile
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
import time

class SmartBackupManager:
    """Умный менеджер резервных копий и файлов целостности."""
    
    def __init__(self, project_root="."):
        self.project_root = Path(project_root)
        self.backup_dir = self.project_root / ".backups"
        self.integrity_dir = self.project_root / ".integrity"
        self.config_file = self.project_root / ".backup_config.json"
        self.max_backups_per_file = 3
        self.max_backup_age_days = 7
        self.setup_directories()
        self.load_config()
    
    def setup_directories(self):
        """Создает необходимые директории."""
        self.backup_dir.mkdir(exist_ok=True)
        self.integrity_dir.mkdir(exist_ok=True)
        
        # Создаем .gitignore для этих директорий
        gitignore_file = self.project_root / ".gitignore"
        gitignore_content = """# Автоматически созданные файлы
.backups/
.integrity/
*.backup_*
*.integrity
*.bak
"""
        
        try:
            if not gitignore_file.exists():
                with open(gitignore_file, 'w', encoding='utf-8') as f:
                    f.write(gitignore_content)
            else:
                # Проверяем, есть ли уже наши записи
                try:
                    with open(gitignore_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if ".backups/" not in content:
                        with open(gitignore_file, 'a', encoding='utf-8') as f:
                            f.write('\n' + gitignore_content)
                except UnicodeDecodeError:
                    # Если файл в другой кодировке, создаем новый
                    with open(gitignore_file, 'w', encoding='utf-8') as f:
                        f.write(gitignore_content)
        except Exception as e:
            print(f"    ⚠️ Не удалось обновить .gitignore: {e}")
    
    def load_config(self):
        """Загружает конфигурацию бэкапов."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.max_backups_per_file = config.get('max_backups_per_file', 3)
                    self.max_backup_age_days = config.get('max_backup_age_days', 7)
            except:
                pass
    
    def save_config(self):
        """Сохраняет конфигурацию бэкапов."""
        config = {
            'max_backups_per_file': self.max_backups_per_file,
            'max_backup_age_days': self.max_backup_age_days,
            'last_updated': datetime.now().isoformat()
        }
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def create_smart_backup(self, filepath, content):
        """Создает умную резервную копию с автоматической очисткой."""
        filepath = Path(filepath)
        
        try:
            # Пытаемся получить относительный путь
            relative_path = filepath.relative_to(self.project_root)
        except ValueError:
            # Если не удается получить относительный путь, используем имя файла
            relative_path = filepath.name
        
        # Создаем безопасное имя файла
        safe_name = str(relative_path).replace('/', '_').replace('\\', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{safe_name}.backup_{timestamp}"
        backup_path = self.backup_dir / backup_name
        
        # Создаем бэкап
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Очищаем старые бэкапы для этого файла
            self.cleanup_old_backups_for_file(safe_name)
            
            return str(backup_path)
        except Exception as e:
            print(f"    ❌ Ошибка создания бэкапа: {e}")
            return None
    
    def cleanup_old_backups_for_file(self, file_prefix):
        """Очищает старые бэкапы для конкретного файла."""
        backups = []
        for backup_file in self.backup_dir.glob(f"{file_prefix}.backup_*"):
            try:
                mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
                backups.append((backup_file, mtime))
            except:
                continue
        
        # Сортируем по времени создания (новые в конце)
        backups.sort(key=lambda x: x[1])
        
        # Удаляем лишние, оставляя только последние max_backups_per_file
        if len(backups) > self.max_backups_per_file:
            for backup_file, _ in backups[:-self.max_backups_per_file]:
                try:
                    backup_file.unlink()
                except:
                    pass
    
    def create_integrity_file(self, filepath, content):
        """Создает оптимизированный файл целостности."""
        filepath = Path(filepath)
        
        try:
            # Пытаемся получить относительный путь
            relative_path = filepath.relative_to(self.project_root)
        except ValueError:
            # Если не удается получить относительный путь, используем имя файла
            relative_path = filepath.name
        
        # Создаем безопасное имя
        safe_name = str(relative_path).replace('/', '_').replace('\\', '_')
        integrity_name = f"{safe_name}.integrity"
        integrity_path = self.integrity_dir / integrity_name
        
        # Создаем хеш и метаданные
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        metadata = {
            'file_path': str(relative_path),
            'md5_hash': content_hash,
            'size_bytes': len(content.encode('utf-8')),
            'last_modified': datetime.now().isoformat(),
            'backup_count': len(list(self.backup_dir.glob(f"{safe_name}.backup_*")))
        }
        
        try:
            with open(integrity_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            return str(integrity_path)
        except Exception as e:
            print(f"    ⚠️ Не удалось создать файл целостности: {e}")
            return None
    
    def cleanup_old_files(self):
        """Очищает старые файлы бэкапов и целостности."""
        cutoff_date = datetime.now() - timedelta(days=self.max_backup_age_days)
        
        # Очищаем старые бэкапы
        old_backups = []
        for backup_file in self.backup_dir.glob("*.backup_*"):
            try:
                mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
                if mtime < cutoff_date:
                    old_backups.append(backup_file)
            except:
                continue
        
        if old_backups:
            print(f"  🧹 Найдено старых бэкапов: {len(old_backups)}")
            for backup_file in old_backups:
                try:
                    backup_file.unlink()
                except:
                    pass
        
        # Очищаем старые файлы целостности
        old_integrity = []
        for integrity_file in self.integrity_dir.glob("*.integrity"):
            try:
                mtime = datetime.fromtimestamp(integrity_file.stat().st_mtime)
                if mtime < cutoff_date:
                    old_integrity.append(integrity_file)
            except:
                continue
        
        if old_integrity:
            print(f"  🧹 Найдено старых файлов целостности: {len(old_integrity)}")
            for integrity_file in old_integrity:
                try:
                    integrity_file.unlink()
                except:
                    pass
    
    def get_backup_status(self):
        """Показывает статус бэкапов."""
        backup_count = len(list(self.backup_dir.glob("*.backup_*")))
        integrity_count = len(list(self.integrity_dir.glob("*.integrity")))
        
        print(f"📊 Статус резервных копий:")
        print(f"  📁 Бэкапы: {backup_count}")
        print(f"  📋 Файлы целостности: {integrity_count}")
        
        if backup_count > 0:
            print(f"  💡 Для очистки: backup_manager.cleanup_old_files()")
        
        return backup_count, integrity_count
    
    def force_cleanup_all(self):
        """Принудительно удаляет все бэкапы и файлы целостности."""
        print("🧹 ПРИНУДИТЕЛЬНАЯ ОЧИСТКА ВСЕХ ФАЙЛОВ...")
        
        backup_count = len(list(self.backup_dir.glob("*.backup_*")))
        integrity_count = len(list(self.integrity_dir.glob("*.integrity")))
        
        if backup_count == 0 and integrity_count == 0:
            print("  ✅ Файлы для очистки не найдены")
            return
        
        print(f"  📁 Бэкапов для удаления: {backup_count}")
        print(f"  📋 Файлов целостности для удаления: {integrity_count}")
        
        response = input("  ❓ Продолжить удаление? (yes/NO): ").strip().lower()
        if response != 'yes':
            print("  ❌ Операция отменена")
            return
        
        # Удаляем все файлы
        deleted_backups = 0
        deleted_integrity = 0
        
        for backup_file in self.backup_dir.glob("*.backup_*"):
            try:
                backup_file.unlink()
                deleted_backups += 1
            except:
                pass
        
        for integrity_file in self.integrity_dir.glob("*.integrity"):
            try:
                integrity_file.unlink()
                deleted_integrity += 1
            except:
                pass
        
        print(f"  ✅ Удалено бэкапов: {deleted_backups}")
        print(f"  ✅ Удалено файлов целостности: {deleted_integrity}")
        
        # Удаляем пустые директории
        try:
            if not any(self.backup_dir.iterdir()):
                self.backup_dir.rmdir()
                print("  ✅ Удалена пустая директория .backups")
        except:
            pass
        
        try:
            if not any(self.integrity_dir.iterdir()):
                self.integrity_dir.rmdir()
                print("  ✅ Удалена пустая директория .integrity")
        except:
            pass

# Глобальный экземпляр менеджера
backup_manager = SmartBackupManager()

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
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return backup_manager.create_smart_backup(filepath, content)
    except Exception as e:
        print(f"    ❌ Ошибка создания резервной копии: {e}")
        return None

def emergency_repair(content):
    """Экстренный ремонт для самых критических случаев."""
    print("    🚨 Применяю экстренный ремонт...")
    
    # Полностью переписываем файл с базовой структурой
    lines = content.splitlines()
    fixed_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Пытаемся восстановить определения функций и классов
        if stripped.startswith('def '):
            # Извлекаем имя функции
            match = re.match(r'def\s+(\w+)', stripped)
            if match:
                func_name = match.group(1)
                fixed_lines.append(f'def {func_name}():')
                fixed_lines.append('    pass')
                continue
        
        elif stripped.startswith('class '):
            # Извлекаем имя класса
            match = re.match(r'class\s+(\w+)', stripped)
            if match:
                class_name = match.group(1)
                fixed_lines.append(f'class {class_name}:')
                fixed_lines.append('    pass')
                continue
        
        elif stripped.startswith(('if ', 'elif ', 'for ', 'while ', 'try:', 'with ')):
            # Восстанавливаем управляющие конструкции
            if not stripped.endswith(':'):
                fixed_lines.append(stripped + ':')
            else:
                fixed_lines.append(stripped)
            fixed_lines.append('    pass')
            continue
        
        elif stripped.startswith('import ') or stripped.startswith('from '):
            # Сохраняем импорты
            fixed_lines.append(stripped)
            continue
        
        elif stripped.startswith('#'):
            # Сохраняем комментарии
            fixed_lines.append(stripped)
            continue
        
        # Пропускаем проблемные строки
    
    # Если ничего не получилось, создаем базовую структуру
    if not fixed_lines:
        fixed_lines = [
            '# Восстановленный файл',
            '# Этот файл был критически поврежден',
            '',
            'def main():',
            '    """Основная функция"""',
            '    pass',
            '',
            'if __name__ == "__main__":',
            '    main()'
        ]
    
    return '\n'.join(fixed_lines)

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

def analyze_file_damage(content):
    """Анализирует степень повреждения файла и возвращает детальный отчет."""
    damage_report = {
        'total_lines': len(content.splitlines()),
        'empty_lines': 0,
        'comment_lines': 0,
        'code_lines': 0,
        'syntax_errors': [],
        'encoding_issues': False,
        'damage_score': 0,  # 0-100, где 100 - полностью поврежден
        'recommendations': []
    }
    
    lines = content.splitlines()
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        if not stripped:
            damage_report['empty_lines'] += 1
        elif stripped.startswith('#'):
            damage_report['comment_lines'] += 1
        else:
            damage_report['code_lines'] += 1
            
        # Проверяем на очевидные проблемы
        if any(char in line for char in ['\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07']):
            damage_report['encoding_issues'] = True
            damage_report['syntax_errors'].append(f"Строка {i}: Невидимые символы")
            
        # Проверяем на разорванные конструкции
        if stripped and not stripped.endswith(':') and stripped.endswith('('):
            damage_report['syntax_errors'].append(f"Строка {i}: Незакрытая скобка")
            
        if stripped and stripped.startswith(')') and not stripped.startswith('('):
            damage_report['syntax_errors'].append(f"Строка {i}: Лишняя закрывающая скобка")
    
    # Вычисляем оценку повреждения
    if damage_report['total_lines'] == 0:
        damage_report['damage_score'] = 100
    else:
        # Базовый счетчик
        damage_score = 0
        
        # Штраф за пустые строки (если их много)
        if damage_report['empty_lines'] > damage_report['total_lines'] * 0.8:
            damage_score += 20
            
        # Штраф за проблемы с кодировкой
        if damage_report['encoding_issues']:
            damage_score += 30
            
        # Штраф за синтаксические ошибки
        damage_score += min(len(damage_report['syntax_errors']) * 10, 40)
        
        # Штраф за очень короткие файлы
        if damage_report['total_lines'] < 5:
            damage_score += 20
            
        damage_report['damage_score'] = min(damage_score, 100)
    
    # Формируем рекомендации
    if damage_report['damage_score'] > 80:
        damage_report['recommendations'].append("Критическое повреждение - требуется экстренный ремонт")
    elif damage_report['damage_score'] > 50:
        damage_report['recommendations'].append("Сильное повреждение - требуется агрессивный ремонт")
    elif damage_report['damage_score'] > 20:
        damage_report['recommendations'].append("Умеренное повреждение - стандартные исправления")
    else:
        damage_report['recommendations'].append("Минимальные повреждения - легкие исправления")
    
    if damage_report['encoding_issues']:
        damage_report['recommendations'].append("Обнаружены проблемы с кодировкой - требуется очистка символов")
    
    if len(damage_report['syntax_errors']) > 5:
        damage_report['recommendations'].append("Много синтаксических ошибок - требуется пошаговое исправление")
    
    return damage_report

def smart_repair_strategy(content, damage_report):
    """Выбирает оптимальную стратегию исправления на основе анализа повреждений."""
    print(f"    📊 Анализ повреждений: {damage_report['damage_score']}/100")
    print(f"    📋 Рекомендации: {', '.join(damage_report['recommendations'])}")
    
    # Проверяем, есть ли синтаксические ошибки
    has_syntax_errors = len(damage_report['syntax_errors']) > 0
    
    if has_syntax_errors or damage_report['damage_score'] > 30:
        print("    🚨 Применяю улучшенное пошаговое восстановление...")
        return enhanced_step_by_step_recovery(content)
    elif has_syntax_errors or damage_report['damage_score'] > 20:
        print("    🚨 Применяю улучшенный экстренный ремонт...")
        return enhanced_emergency_repair(content)
    elif damage_report['damage_score'] > 10:
        print("    🔥 Применяю агрессивный ремонт...")
        return aggressive_repair(content)
    else:
        print("    🛡️ Применяю профилактические исправления...")
        return apply_preventive_fixes(content)

def apply_standard_fixes(content):
    """Применяет стандартные исправления в оптимальном порядке."""
    print("    🔧 Стандартные исправления...")
    
    # Применяем исправления в порядке от простых к сложным
    content = fix_indentation(content)
    content = fix_syntax_errors(content)
    content = fix_try_except(content)
    content = fix_empty_blocks(content)
    content = fix_redundant_else(content)
    content = fix_imports(content)
    
    # Обновляем статистику
    update_repair_statistics('standard', True)
    
    return content

def fix_critical_syntax_errors(content):
    """Исправляет критические синтаксические ошибки с улучшенной логикой."""
    print("    🔥 Исправляю критические синтаксические ошибки...")
    
    # Исправляем незакрытые скобки в определениях функций/классов
    lines = content.splitlines()
    fixed_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Исправляем определения функций и классов
        if re.match(r'^(def|class)\s+\w+\s*\([^)]*$', stripped):
            # Добавляем закрывающую скобку и двоеточие
            line = line.rstrip() + '):'
        elif re.match(r'^(def|class)\s+\w+\s*$', stripped):
            # Определение без скобок, добавляем скобки и двоеточие
            line = line.rstrip() + '():'
        elif re.match(r'^(if|elif|else|for|while|with|try|except|finally)\s*\([^)]*$', stripped):
            # Добавляем закрывающую скобку и двоеточие
            line = line.rstrip() + '):'
        elif re.match(r'^(if|elif|else|for|while|with|try|except|finally)\s*[^:]*$', stripped):
            # Добавляем двоеточие если его нет, но только для правильных конструкций
            if not stripped.endswith(':'):
                # Проверяем, есть ли уже скобки
                if '(' in stripped and ')' in stripped:
                    # Есть скобки, просто добавляем двоеточие
                    line = line.rstrip() + ':'
                elif '(' in stripped and ')' not in stripped:
                    # Есть открывающая скобка, но нет закрывающей
                    line = line.rstrip() + '):'
                else:
                    # Нет скобок, просто добавляем двоеточие
                    line = line.rstrip() + ':'
        
        fixed_lines.append(line)
    
    content = '\n'.join(fixed_lines)
    
    # Исправляем незакрытые многострочные строки
    content = re.sub(r'"""([^"]*?)(?=\n|$)', r'"""\1"""', content)
    content = re.sub(r"'''([^']*?)(?=\n|$)", r"'''\1'''", content)
    
    # Исправляем очевидные опечатки
    replacements = {
        'imp or t': 'import',
        'f or ': 'for ',
        'if ': 'if ',
        'def ': 'def ',
        'class ': 'class ',
        'try:': 'try:',
        'except:': 'except:',
        'finally:': 'finally:',
        'with ': 'with ',
        'while ': 'while ',
        'elif ': 'elif ',
        'else:': 'else:'
    }
    
    for wrong, correct in replacements.items():
        content = content.replace(wrong, correct)
    
    # Дополнительные исправления для критических случаев
    # Исправляем незакрытые скобки в конце строк
    content = re.sub(r'\(([^)]*?)(?=\n|$)', r'(\1)', content)
    
    # Исправляем незакрытые квадратные скобки
    content = re.sub(r'\[([^\]]*?)(?=\n|$)', r'[\1]', content)
    
    # Исправляем незакрытые фигурные скобки
    content = re.sub(r'\{([^}]*?)(?=\n|$)', r'{\1}', content)
    
    return content

def advanced_string_fix(content):
    """Продвинутое исправление незакрытых строк и кавычек."""
    print("    🔤 Исправляю сложные проблемы со строками...")
    
    lines = content.splitlines()
    fixed_lines = []
    in_multiline_string = False
    string_delimiter = None
    string_start_line = 0
    
    for i, line in enumerate(lines):
        # Проверяем начало многострочной строки
        if '"""' in line or "'''" in line:
            if not in_multiline_string:
                # Начинается новая многострочная строка
                if '"""' in line:
                    string_delimiter = '"""'
                else:
                    string_delimiter = "'''"
                in_multiline_string = True
                string_start_line = i
            else:
                # Заканчивается многострочная строка
                if string_delimiter in line:
                    in_multiline_string = False
                    string_delimiter = None
        
        # Если мы в многострочной строке, проверяем на незакрытые
        if in_multiline_string:
            # Ищем конец строки
            if string_delimiter in line:
                in_multiline_string = False
                string_delimiter = None
            else:
                # Если строка не заканчивается, добавляем закрывающий разделитель
                if i == len(lines) - 1:  # Последняя строка
                    line = line + string_delimiter
                    in_multiline_string = False
                    string_delimiter = None
        
        # Исправляем одинарные кавычки
        line = re.sub(r'(?<!\\)"(?![^"]*")', '"""', line)  # Заменяем одиночные на тройные
        line = re.sub(r"(?<!\\)'(?![^']*')", "'''", line)
        
        fixed_lines.append(line)
    
    # Если файл заканчивается незакрытой строкой, закрываем её
    if in_multiline_string:
        fixed_lines[-1] = fixed_lines[-1] + string_delimiter
    
    # Дополнительная проверка на незавершенные многострочные строки
    content = '\n'.join(fixed_lines)
    
    # Ищем незавершенные многострочные строки и исправляем их
    # Паттерн: """текст без закрывающих """
    content = re.sub(r'"""([^"]*?)(?=\n|$)', r'"""\1"""', content)
    content = re.sub(r"'''([^']*?)(?=\n|$)", r"'''\1'''", content)
    
    # Ищем строки, которые начинаются с кавычек, но не заканчиваются
    lines = content.splitlines()
    fixed_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Если строка начинается с кавычки, но не заканчивается ею
        if (stripped.startswith('"') and not stripped.endswith('"')) or \
           (stripped.startswith("'") and not stripped.endswith("'")):
            # Добавляем закрывающую кавычку
            if stripped.startswith('"'):
                line = line + '"'
            else:
                line = line + "'"
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def smart_bracket_fix(content):
    """Умное исправление несоответствия скобок."""
    print("    🔗 Исправляю несоответствие скобок...")
    
    lines = content.splitlines()
    fixed_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Подсчитываем скобки в строке
        open_parens = stripped.count('(')
        close_parens = stripped.count(')')
        open_brackets = stripped.count('[')
        close_brackets = stripped.count(']')
        open_braces = stripped.count('{')
        close_braces = stripped.count('}')
        
        # Если есть незакрытые скобки, пытаемся исправить
        if open_parens > close_parens:
            # Добавляем недостающие закрывающие скобки
            missing = open_parens - close_parens
            line = line.rstrip() + ')' * missing
        
        if open_brackets > close_brackets:
            # Добавляем недостающие закрывающие скобки
            missing = open_brackets - close_brackets
            line = line.rstrip() + ']' * missing
        
        if open_braces > close_braces:
            # Добавляем недостающие закрывающие скобки
            missing = open_braces - close_braces
            line = line.rstrip() + '}' * missing
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def context_aware_fix(content):
    """Контекстно-осознанное исправление на основе анализа структуры."""
    print("    🧠 Применяю контекстно-осознанные исправления...")
    
    lines = content.splitlines()
    fixed_lines = []
    indent_level = 0
    expected_indent = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Определяем текущий уровень отступа
        current_indent = len(line) - len(line.lstrip())
        
        # Анализируем контекст строки
        if stripped.startswith(('def ', 'class ', 'if ', 'elif ', 'else:', 'for ', 'while ', 'try:', 'except', 'finally:', 'with ')):
            # Это начало блока
            if not stripped.endswith(':'):
                line = line.rstrip() + ':'
            expected_indent = current_indent + 4
        elif stripped.startswith(('return', 'break', 'continue', 'pass', 'raise')):
            # Это операторы, которые должны быть на правильном уровне отступа
            if current_indent != expected_indent:
                line = ' ' * expected_indent + stripped
        elif stripped and not stripped.startswith('#'):
            # Обычная строка кода
            if current_indent > expected_indent + 8:
                # Слишком большой отступ, исправляем
                line = ' ' * (expected_indent + 4) + stripped
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def step_by_step_recovery(content):
    """Пошаговое восстановление структуры файла."""
    print("    🔄 Пошаговое восстановление структуры...")
    
    # Шаг 1: Очистка от невидимых символов
    print("    🔧 Шаг 1: Очистка от невидимых символов...")
    content = re.sub(r'[^\x20-\x7E\n\t]', '', content)
    
    # Шаг 2: Исправление строк
    print("    🔧 Шаг 2: Исправление строк...")
    content = advanced_string_fix(content)
    
    # Шаг 3: Исправление незавершенных строк
    print("    🔧 Шаг 3: Исправление незавершенных строк...")
    content = fix_unterminated_strings(content)
    
    # Шаг 3.5: Агрессивное исправление многострочных строк
    print("    🔧 Шаг 3.5: Агрессивное исправление многострочных строк...")
    content = fix_multiline_strings_aggressive(content)
    
    # Шаг 4: Исправление скобок
    print("    🔧 Шаг 4: Исправление скобок...")
    content = smart_bracket_fix(content)
    
    # Шаг 5: Исправление двоеточий
    print("    🔧 Шаг 5: Исправление двоеточий...")
    content = fix_missing_colons(content)
    
    # Шаг 6: Исправление вызовов функций
    print("    🔧 Шаг 6: Исправление вызовов функций...")
    content = fix_broken_function_calls(content)
    
    # Шаг 7: Исправление импортов
    print("    🔧 Шаг 7: Исправление импортов...")
    content = fix_broken_import_statements(content)
    
    # Шаг 8: Исправление сложных отступов
    print("    🔧 Шаг 8: Исправление сложных отступов...")
    content = fix_complex_indentation_issues(content)
    
    # Шаг 9: Контекстные исправления
    print("    🔧 Шаг 9: Контекстные исправления...")
    content = context_aware_fix(content)
    
    # Шаг 9.5: Исправление определений функций и классов
    print("    🔧 Шаг 9.5: Исправление определений функций и классов...")
    content = fix_function_and_class_definitions(content)
    
    # Шаг 9.6: Добавление тел к пустым блокам
    print("    🔧 Шаг 9.6: Добавление тел к пустым блокам...")
    content = fix_empty_blocks(content)
    
    # Шаг 10: Критические исправления
    print("    🔧 Шаг 10: Критические исправления...")
    content = fix_critical_syntax_errors(content)
    
    # Шаг 11: Финальная очистка
    print("    🔧 Шаг 11: Финальная очистка...")
    content = final_cleanup_and_validation(content)
    
    # Шаг 12: Простая валидация (без рекурсивных вызовов)
    print("    🔧 Шаг 12: Простая валидация...")
    if not validate_python_syntax(content):
        print("    ⚠️ Синтаксис все еще невалиден, применяю дополнительные исправления...")
        # Применяем дополнительные исправления без рекурсии
        content = fix_missing_colons(content)
        content = fix_unterminated_strings(content)
        content = fix_broken_function_calls(content)
        content = fix_broken_import_statements(content)
        content = fix_multiline_strings_aggressive(content)
        content = smart_bracket_fix(content)
        content = context_aware_fix(content)
    
    return content

def enhanced_emergency_repair(content):
    """Улучшенный экстренный ремонт с реальными исправлениями."""
    print("    🚨 Применяю улучшенный экстренный ремонт...")
    
    # Применяем пошаговое восстановление
    content = step_by_step_recovery(content)
    
    # Если файл все еще невалиден, применяем продвинутые агрессивные исправления
    if not validate_python_syntax(content):
        print("    💥 Применяю продвинутые агрессивные исправления...")
        content = advanced_aggressive_repair(content)
    
    # Обновляем статистику
    update_repair_statistics('emergency', True)
    
    return content

def create_file_integrity_check(filepath):
    """Создает файл для проверки целостности в будущем."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Создаем хеш содержимого
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        
        # Создаем файл проверки через менеджер
        return backup_manager.create_integrity_file(filepath, content)
    except Exception as e:
        print(f"    ⚠️ Не удалось создать файл проверки целостности: {e}")
        return False

def cleanup_backup_files():
    """Удаляет резервные копии после успешной проверки проекта."""
    print("🧹 Очистка резервных копий...")
    
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
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Пытаемся скомпилировать
            ast.parse(content)
            healthy_files += 1
            
        except Exception as e:
            problematic_files.append((filepath, str(e)))
    
    print(f"  ✅ Здоровых файлов: {healthy_files}")
    print(f"  ❌ Проблемных файлов: {len(problematic_files)}")
    
    # Если все файлы здоровы, очищаем старые файлы
    if len(problematic_files) == 0:
        print("  🎉 Проект полностью здоров! Очищаю старые файлы...")
        backup_manager.cleanup_old_files()
    else:
        print("  ⚠️ Проект имеет проблемы, файлы сохранены")
        print("  📋 Список проблемных файлов:")
        for filepath, error in problematic_files[:5]:  # Показываем первые 5
            print(f"    - {filepath}: {error}")
        if len(problematic_files) > 5:
            print(f"    ... и еще {len(problematic_files) - 5} файлов")

def smart_backup_management():
    """Умное управление резервными копиями с автоматической очисткой."""
    print("🧠 Умное управление резервными копиями...")
    
    # Перемещаем существующие резервные копии в специальную директорию
    moved_backups = 0
    for root, _, files in os.walk('.'):
        for file in files:
            if (file.endswith('.backup_') or file.endswith('.bak') or 
                file.endswith('.integrity')) and root not in ['.backups', '.integrity']:
                old_path = os.path.join(root, file)
                if file.endswith('.integrity'):
                    new_path = backup_manager.integrity_dir / file
                else:
                    new_path = backup_manager.backup_dir / file
                try:
                    shutil.move(old_path, new_path)
                    moved_backups += 1
                except Exception as e:
                    print(f"    ⚠️ Не удалось переместить {old_path}: {e}")
    
    if moved_backups > 0:
        print(f"  📦 Перемещено файлов в централизованные директории: {moved_backups}")
    
    # Очищаем старые файлы
    backup_manager.cleanup_old_files()
    
    return str(backup_manager.backup_dir)

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
    """Добавляет тела к пустым функциям, классам и управляющим конструкциям."""
    print("    📝 Добавляю тела к пустым блокам...")
    
    lines = content.splitlines()
    fixed_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Проверяем, является ли это определением функции, класса или управляющей конструкцией
        if (stripped.startswith(('def ', 'class ')) and stripped.endswith(':')) or \
           (stripped.startswith(('if ', 'elif ', 'for ', 'while ', 'with ', 'try:')) and stripped.endswith(':')):
            fixed_lines.append(line)
            
            # Проверяем следующую строку
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                next_stripped = next_line.strip()
                
                # Если следующая строка не имеет отступа или это новое определение
                if (not next_line.startswith(' ') or 
                    next_stripped.startswith(('def ', 'class ', 'if ', 'elif ', 'for ', 'while ', 'with ', 'try:', 'except', 'finally')) or
                    next_stripped.startswith('import') or
                    next_stripped.startswith('from ') or
                    next_stripped == '' or
                    next_stripped == 'else:' or
                    next_stripped == 'except:' or
                    next_stripped == 'finally:'):
                    # Добавляем pass как тело
                    indent = len(line) - len(line.lstrip()) + 4
                    fixed_lines.append(' ' * indent + 'pass')
                else:
                    # Следующая строка уже имеет тело
                    fixed_lines.append(next_line)
                    i += 1
            else:
                # Это последняя строка, добавляем pass
                indent = len(line) - len(line.lstrip()) + 4
                fixed_lines.append(' ' * indent + 'pass')
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
    try:
        # Проверяем, не является ли файл самим скриптом
        if os.path.abspath(filepath) == os.path.abspath(__file__):
            print("    ⏭️ Пропуск самого себя")
            return None
        
        # Создаем директорию для резервных копий
        backup_dir = Path(".backups")
        backup_dir.mkdir(exist_ok=True)
        
        # Создаем имя резервной копии с временной меткой
        filename = Path(filepath).name
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{filename}.backup_{timestamp}"
        
        # Копируем файл
        shutil.copy2(filepath, backup_path)
        print(f"    💾 Резервная копия создана: {backup_path}")
        
        return backup_path
        
    except Exception as e:
        print(f"    ❌ Ошибка создания резервной копии: {e}")
        return None

def process_file(filepath):
    """Обрабатывает один Python файл."""
    try:
        print(f"[{filepath}]")
        
        # Читаем файл с исправлением кодировки
        content = read_file_with_encoding_fix(filepath)
        if not content:
            print("  ❌ Не удалось прочитать файл")
            return
        
        # Проверяем размер файла
        file_size = len(content)
        print(f"  📄 Размер файла: {file_size} символов")
        
        # Проверяем исходный синтаксис
        original_syntax_valid = validate_python_syntax(content)
        print(f"  🔍 Исходный синтаксис: {'✅ валиден' if original_syntax_valid else '❌ НЕ ВАЛИДЕН'}")
        
        if original_syntax_valid:
            # Файл уже валиден, применяем стандартные исправления
            print("  🔧 Применяю стандартные исправления...")
            content = apply_standard_fixes(content)
            content = fix_empty_blocks(content)
            content = apply_preventive_fixes(content)
            
            # Проверяем итоговый синтаксис
            final_syntax_valid = validate_python_syntax(content)
            print(f"  🔍 Итоговый синтаксис: {'✅ валиден' if final_syntax_valid else '❌ НЕ ВАЛИДЕН'}")
            
            if final_syntax_valid:
                # Сохраняем исправленный файл
                save_file(filepath, content)
                print("  ✅ Файл успешно исправлен и сохранен")
            else:
                print("  ⚠️ ВНИМАНИЕ: Исправления сломали синтаксис:", filepath)
                print("  🔄 Восстанавливаем из резервной копии...")
                restore_from_backup(filepath)
        else:
            # Файл невалиден, анализируем повреждения
            print("  🔍 Анализирую повреждения файла...")
            damage_report = analyze_file_damage(content)
            
            # Применяем стратегию исправления
            print("  🚨 Применяю улучшенное пошаговое восстановление...")
            content = smart_repair_strategy(content, damage_report)
            
            # Проверяем итоговый синтаксис
            final_syntax_valid = validate_python_syntax(content)
            print(f"  🔍 Итоговый синтаксис: {'✅ валиден' if final_syntax_valid else '❌ НЕ ВАЛИДЕН'}")
            
            if final_syntax_valid:
                # Сохраняем исправленный файл
                save_file(filepath, content)
                print("  ✅ Файл успешно исправлен и сохранен")
            else:
                # Если стандартные методы не помогли, применяем сверхмощное восстановление
                print("  🚨 Стандартные методы не помогли, применяю сверхмощное восстановление...")
                content = ultimate_file_recovery(content)
                
                # Проверяем результат сверхмощного восстановления
                final_syntax_valid = validate_python_syntax(content)
                print(f"  🔍 Результат сверхмощного восстановления: {'✅ валиден' if final_syntax_valid else '❌ НЕ ВАЛИДЕН'}")
                
                if final_syntax_valid:
                    # Сохраняем восстановленный файл
                    save_file(filepath, content)
                    print("  ✅ Файл успешно восстановлен и сохранен")
                else:
                    print("  ⚠️ Файл изменен, но синтаксис невалиден:", filepath)
                    print("  🔄 Восстанавливаем из резервной копии...")
                    restore_from_backup(filepath)
        
        # Создаем резервную копию
        create_backup(filepath)
        
    except Exception as e:
        print(f"  ❌ Ошибка обработки файла: {e}")
        print(f"  📍 Файл: {filepath}")

def main():
    """Основная функция для обхода директорий."""
    current_dir = os.getcwd()
    print(f"Начинаю обработку Python-файлов в директории: {current_dir}")
    
    # Настраиваем умное управление резервными копиями
    smart_backup_management()
    
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
    
    # Показываем статистику исправлений
    print_repair_statistics()
    
    # Мониторим изменения в файлах
    monitor_file_changes()

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
    backup_manager.cleanup_old_files()

def show_backup_status():
    """Показывает статус резервных копий."""
    backup_manager.get_backup_status()

def force_cleanup_all_backups():
    """Принудительно удаляет ВСЕ резервные копии в проекте."""
    backup_manager.force_cleanup_all()

def cleanup_old_backups_by_age(days_old=7):
    """Удаляет резервные копии старше указанного количества дней."""
    print(f"🧹 Очистка резервных копий старше {days_old} дней...")
    
    cutoff_date = datetime.now() - timedelta(days=days_old)
    
    old_backups = []
    for backup_file in backup_manager.backup_dir.glob("*.backup_*"):
        try:
            mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
            if mtime < cutoff_date:
                old_backups.append((backup_file, mtime))
        except:
            pass
    
    if not old_backups:
        print("  ✅ Старые резервные копии не найдены")
        return
    
    print(f"  📁 Найдено старых резервных копий: {len(old_backups)}")
    
    # Сортируем по дате
    old_backups.sort(key=lambda x: x[1])
    
    # Показываем что будет удалено
    print("  📋 Старые файлы для удаления:")
    for backup_file, file_time in old_backups[:10]:
        age_days = (datetime.now() - file_time).days
        print(f"    - {backup_file.name} (возраст: {age_days} дней)")
    
    if len(old_backups) > 10:
        print(f"    ... и еще {len(old_backups) - 10} файлов")
    
    # Запрашиваем подтверждение
    response = input(f"\n  ❓ Удалить резервные копии старше {days_old} дней? (y/N): ").strip().lower()
    if response != 'y':
        print("  ❌ Операция отменена пользователем")
        return
    
    # Удаляем старые резервные копии
    deleted_count = 0
    for backup_file, file_time in old_backups:
        try:
            backup_file.unlink()
            deleted_count += 1
            age_days = (datetime.now() - file_time).days
            print(f"    ✅ Удален: {backup_file.name} (возраст: {age_days} дней)")
        except Exception as e:
            print(f"    ❌ Ошибка удаления {backup_file.name}: {e}")
    
    print(f"\n  🎉 Очистка завершена!")
    print(f"  ✅ Удалено старых резервных копий: {deleted_count}")

def get_repair_statistics():
    """Возвращает статистику по исправлениям."""
    return {
        'total_files_processed': 0,
        'files_fixed': 0,
        'files_unchanged': 0,
        'files_failed': 0,
        'emergency_repairs': 0,
        'aggressive_repairs': 0,
        'standard_fixes': 0,
        'preventive_fixes': 0,
        'total_repair_time': 0.0
    }

# Глобальная статистика
repair_stats = get_repair_statistics()

def update_repair_statistics(repair_type, success=True):
    """Обновляет статистику исправлений."""
    repair_stats['total_files_processed'] += 1
    
    if success:
        repair_stats['files_fixed'] += 1
    else:
        repair_stats['files_failed'] += 1
    
    if repair_type == 'emergency':
        repair_stats['emergency_repairs'] += 1
    elif repair_type == 'aggressive':
        repair_stats['aggressive_repairs'] += 1
    elif repair_type == 'standard':
        repair_stats['standard_fixes'] += 1
    elif repair_type == 'preventive':
        repair_stats['preventive_fixes'] += 1

def print_repair_statistics():
    """Выводит статистику исправлений."""
    print("\n📊 Статистика исправлений:")
    print(f"  📁 Всего обработано файлов: {repair_stats['total_files_processed']}")
    print(f"  ✅ Успешно исправлено: {repair_stats['files_fixed']}")
    print(f"  ➖ Без изменений: {repair_stats['files_unchanged']}")
    print(f"  ❌ Ошибки исправления: {repair_stats['files_failed']}")
    print(f"  🚨 Экстренных ремонтов: {repair_stats['emergency_repairs']}")
    print(f"  🔥 Агрессивных ремонтов: {repair_stats['aggressive_repairs']}")
    print(f"  🔧 Стандартных исправлений: {repair_stats['standard_fixes']}")
    print(f"  🛡️ Профилактических исправлений: {repair_stats['preventive_fixes']}")
    
    if repair_stats['total_repair_time'] > 0:
        print(f"  ⏱️ Общее время исправлений: {repair_stats['total_repair_time']:.2f} сек")

def enhanced_validate_python_syntax(content):
    """Улучшенная проверка синтаксиса с детальной диагностикой."""
    try:
        # Пытаемся скомпилировать
        ast.parse(content)
        return True, None
    except SyntaxError as e:
        error_info = {
            'type': 'SyntaxError',
            'message': str(e),
            'line': getattr(e, 'lineno', 'unknown'),
            'offset': getattr(e, 'offset', 'unknown'),
            'text': getattr(e, 'text', 'unknown')
        }
        return False, error_info
    except Exception as e:
        error_info = {
            'type': 'Exception',
            'message': str(e),
            'line': 'unknown',
            'offset': 'unknown',
            'text': 'unknown'
        }
        return False, error_info

def suggest_fixes_for_error(error_info):
    """Предлагает исправления на основе ошибки."""
    suggestions = []
    
    if error_info['type'] == 'SyntaxError':
        message = error_info['message'].lower()
        
        if 'unexpected indent' in message:
            suggestions.append("Проверить отступы - возможно, смешаны табы и пробелы")
        elif 'missing colon' in message:
            suggestions.append("Добавить двоеточие после if/for/while/def/class")
        elif 'invalid syntax' in message:
            suggestions.append("Проверить синтаксис - возможно, лишние или недостающие скобки")
        elif 'eol while scanning string literal' in message:
            suggestions.append("Проверить строки - возможно, незакрытые кавычки")
        elif 'unexpected eof' in message:
            suggestions.append("Проверить структуру - возможно, незакрытые блоки")
    
    if not suggestions:
        suggestions.append("Применить экстренный ремонт для критических повреждений")
    
    return suggestions

def create_repair_report(filepath, original_valid, final_valid, damage_report=None, repair_type=None):
    """Создает детальный отчет по исправлению файла."""
    report = {
        'filepath': str(filepath),
        'timestamp': datetime.now().isoformat(),
        'original_valid': original_valid,
        'final_valid': final_valid,
        'repair_type': repair_type,
        'damage_report': damage_report,
        'success': final_valid or (not original_valid and final_valid)
    }
    
    # Сохраняем отчет в директорию .integrity
    report_file = backup_manager.integrity_dir / f"{Path(filepath).stem}_repair_report.json"
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"    ⚠️ Не удалось сохранить отчет: {e}")
    
    return report

def monitor_file_changes():
    """Мониторит изменения в файлах проекта."""
    print("🔍 Мониторинг изменений в файлах...")
    
    # Проверяем файлы целостности
    integrity_files = list(backup_manager.integrity_dir.glob("*.integrity"))
    
    if not integrity_files:
        print("  📋 Файлы целостности не найдены")
        return
    
    print(f"  📋 Найдено файлов целостности: {len(integrity_files)}")
    
    changed_files = []
    unchanged_files = []
    
    for integrity_file in integrity_files:
        try:
            with open(integrity_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            original_file = Path(metadata['file_path'])
            if original_file.exists():
                with open(original_file, 'r', encoding='utf-8') as f:
                    current_content = f.read()
                
                current_hash = hashlib.md5(current_content.encode('utf-8')).hexdigest()
                
                if current_hash == metadata['md5_hash']:
                    unchanged_files.append(original_file)
                else:
                    changed_files.append((original_file, metadata['md5_hash'], current_hash))
            else:
                changed_files.append((original_file, metadata['md5_hash'], 'FILE_NOT_FOUND'))
                
        except Exception as e:
            print(f"    ⚠️ Ошибка проверки {integrity_file}: {e}")
    
    print(f"  ✅ Неизмененных файлов: {len(unchanged_files)}")
    print(f"  🔄 Измененных файлов: {len(changed_files)}")
    
    if changed_files:
        print("  📋 Список измененных файлов:")
        for file_path, old_hash, new_hash in changed_files[:10]:
            print(f"    - {file_path.name}")
        if len(changed_files) > 10:
            print(f"    ... и еще {len(changed_files) - 10} файлов")
    
    return changed_files, unchanged_files

def fix_decimal_literals(content):
    """Исправляет неверные десятичные литералы."""
    print("    🔢 Исправляю неверные десятичные числа...")
    
    # Исправляем неверные десятичные числа
    # Например: 123.456.789 -> 123.456789
    content = re.sub(r'(\d+\.\d+)\.(\d+)', r'\1\2', content)
    
    # Исправляем числа с лишними точками
    content = re.sub(r'(\d+)\.\.(\d+)', r'\1.\2', content)
    
    # Исправляем числа с точкой в конце
    content = re.sub(r'(\d+)\.(?=\s|$)', r'\1', content)
    
    # Исправляем числа с точкой в начале (упрощенная версия)
    lines = content.splitlines()
    fixed_lines = []
    
    for line in lines:
        # Ищем числа, начинающиеся с точки
        if re.search(r'^\s*\.\d+', line):
            line = re.sub(r'^\s*\.(\d+)', r'0.\1', line)
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def fix_corrupted_imports(content):
    """Исправляет поврежденные импорты."""
    print("    📦 Исправляю поврежденные импорты...")
    
    lines = content.splitlines()
    fixed_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Исправляем разорванные импорты
        if stripped.startswith('import ') and not stripped.endswith(';'):
            # Проверяем, есть ли точка в конце
            if stripped.endswith('.'):
                line = line.rstrip('.')
            # Проверяем, есть ли неполный импорт
            elif stripped.endswith('from'):
                line = line.rstrip('from')
            elif stripped.endswith('as'):
                line = line.rstrip('as')
        
        # Исправляем from ... import
        elif stripped.startswith('from ') and 'import' in stripped:
            if not stripped.endswith(';'):
                # Проверяем, есть ли неполный импорт
                if stripped.endswith('import'):
                    line = line + ' *'
                elif stripped.endswith('import '):
                    line = line + '*'
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def restore_class_structure(content):
    """Восстанавливает структуру классов."""
    print("    🏗️ Восстанавливаю структуру классов...")
    
    lines = content.splitlines()
    fixed_lines = []
    in_class = False
    class_indent = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        current_indent = len(line) - len(line.lstrip())
        
        # Определяем начало класса
        if stripped.startswith('class '):
            in_class = True
            class_indent = current_indent
            # Проверяем, есть ли двоеточие
            if not stripped.endswith(':'):
                line = line.rstrip() + ':'
        
        # Если мы в классе, проверяем структуру
        elif in_class and stripped:
            if current_indent <= class_indent:
                # Мы вышли из класса
                in_class = False
            elif stripped.startswith(('def ', 'class ')):
                # Метод или вложенный класс
                if not stripped.endswith(':'):
                    line = line.rstrip() + ':'
                # Проверяем отступ
                if current_indent != class_indent + 4:
                    line = ' ' * (class_indent + 4) + stripped
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def fix_control_flow_structure(content):
    """Исправляет структуру управления потоком."""
    print("    🔀 Исправляю структуру управления потоком...")
    
    lines = content.splitlines()
    fixed_lines = []
    expected_indent = 0
    in_block = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        current_indent = len(line) - len(line.lstrip())
        
        # Определяем начало блока
        if stripped.startswith(('if ', 'elif ', 'else:', 'for ', 'while ', 'try:', 'except', 'finally:', 'with ')):
            in_block = True
            expected_indent = current_indent + 4
            # Проверяем двоеточие
            if not stripped.endswith(':'):
                line = line.rstrip() + ':'
        
        # Если мы в блоке, проверяем отступы
        elif in_block and stripped and not stripped.startswith('#'):
            if current_indent <= expected_indent - 4:
                # Мы вышли из блока
                in_block = False
                expected_indent = current_indent
            elif current_indent != expected_indent:
                # Неправильный отступ, исправляем
                line = ' ' * expected_indent + stripped
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def fix_complex_indentation_issues(content):
    """Исправляет сложные проблемы с отступами."""
    print("    📏 Исправляю сложные проблемы с отступами...")
    
    lines = content.splitlines()
    fixed_lines = []
    indent_stack = [0]  # Стек отступов
    current_block_level = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            fixed_lines.append(line)
            continue
        
        current_indent = len(line) - len(line.lstrip())
        
        # Определяем тип строки и требуемый отступ
        if stripped.startswith(('def ', 'class ')):
            # Функция или класс - новый уровень отступа
            expected_indent = indent_stack[-1]
            if current_indent != expected_indent:
                line = ' ' * expected_indent + stripped
            indent_stack.append(expected_indent + 4)
            current_block_level = expected_indent + 4
        elif stripped.startswith(('if ', 'elif ', 'else:', 'for ', 'while ', 'try:', 'except', 'finally:', 'with ')):
            # Управляющая конструкция
            expected_indent = indent_stack[-1]
            if current_indent != expected_indent:
                line = ' ' * expected_indent + stripped
            indent_stack.append(expected_indent + 4)
            current_block_level = expected_indent + 4
        elif stripped.startswith(('return', 'break', 'continue', 'pass', 'raise')):
            # Операторы должны быть на правильном уровне отступа
            expected_indent = current_block_level
            if current_indent != expected_indent:
                line = ' ' * expected_indent + stripped
        elif stripped.startswith('import ') or stripped.startswith('from '):
            # Импорты должны быть на уровне модуля
            expected_indent = 0
            if current_indent != expected_indent:
                line = ' ' * expected_indent + stripped
        else:
            # Обычная строка кода
            if current_indent > current_block_level + 8:
                # Слишком большой отступ, исправляем
                line = ' ' * (current_block_level + 4) + stripped
            elif current_indent < current_block_level and current_indent > 0:
                # Проверяем, не вышли ли мы из блока
                while indent_stack and current_indent < indent_stack[-1]:
                    indent_stack.pop()
                if indent_stack:
                    expected_indent = indent_stack[-1] + 4
                    line = ' ' * expected_indent + stripped
                    current_block_level = expected_indent
                else:
                    # Мы на уровне модуля
                    line = ' ' * 0 + stripped
                    current_block_level = 0
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def fix_broken_import_statements(content):
    """Исправляет поврежденные импортные операторы."""
    print("    📦 Исправляю поврежденные импортные операторы...")
    
    lines = content.splitlines()
    fixed_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Исправляем разорванные импорты
        if stripped.startswith('import ') and not stripped.endswith(';'):
            # Проверяем на очевидные проблемы
            if stripped.endswith('.'):
                line = line.rstrip('.')
            elif stripped.endswith('from'):
                line = line.rstrip('from')
            elif stripped.endswith('as'):
                line = line.rstrip('as')
            elif stripped.endswith('import'):
                line = line + ' *'
        
        # Исправляем from ... import
        elif stripped.startswith('from ') and 'import' in stripped:
            if not stripped.endswith(';'):
                if stripped.endswith('import'):
                    line = line + ' *'
                elif stripped.endswith('import '):
                    line = line + '*'
        
        # Исправляем очевидные опечатки в импортах
        line = line.replace('imp or t', 'import')
        line = line.replace('f rom', 'from')
        line = line.replace('im port', 'import')
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def advanced_aggressive_repair(content):
    """Продвинутый агрессивный ремонт для критически поврежденных файлов."""
    print("    💥 Применяю продвинутый агрессивный ремонт...")
    
    # Применяем все доступные исправления в правильном порядке
    content = fix_decimal_literals(content)
    content = fix_broken_import_statements(content)
    content = fix_complex_indentation_issues(content)
    content = restore_class_structure(content)
    content = fix_control_flow_structure(content)
    
    # Применяем новые функции исправления
    content = fix_function_and_class_definitions(content)
    content = fix_empty_blocks(content)
    content = fix_critical_syntax_errors(content)
    
    # Если файл все еще невалиден, применяем базовый агрессивный ремонт
    if not validate_python_syntax(content):
        print("    💥 Применяю базовый агрессивный ремонт...")
        content = aggressive_repair(content)
    
    return content

def fix_missing_colons(content):
    """Исправляет отсутствующие двоеточия в критических местах."""
    print("    🔴 Исправляю отсутствующие двоеточия...")
    
    lines = content.splitlines()
    fixed_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Добавляем двоеточия для блоков, которые их требуют
        if stripped.startswith(('def ', 'class ')):
            if not stripped.endswith(':'):
                line = line.rstrip() + ':'
        elif stripped.startswith(('if ', 'elif ', 'else:', 'for ', 'while ', 'try:', 'except', 'finally:', 'with ')):
            if not stripped.endswith(':'):
                line = line.rstrip() + ':'
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def fix_unterminated_strings(content):
    """Исправляет незавершенные строки более агрессивно."""
    print("    📝 Исправляю незавершенные строки...")
    
    lines = content.splitlines()
    fixed_lines = []
    in_string = False
    string_char = None
    
    for line in lines:
        # Проверяем на незавершенные строки
        if '"' in line or "'" in line:
            # Подсчитываем кавычки
            single_quotes = line.count("'")
            double_quotes = line.count('"')
            
            # Если нечетное количество кавычек, добавляем закрывающую
            if single_quotes % 2 == 1:
                if line.endswith("'"):
                    line = line + "'"
                else:
                    line = line + "'"
            
            if double_quotes % 2 == 1:
                if line.endswith('"'):
                    line = line + '"'
                else:
                    line = line + '"'
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def fix_multiline_strings_aggressive(content):
    """Агрессивно исправляет незавершенные многострочные строки."""
    print("    📝 Агрессивно исправляю многострочные строки...")
    
    # Ищем паттерны незавершенных многострочных строк
    # Паттерн 1: """текст без закрывающих """
    content = re.sub(r'"""([^"]*?)(?=\n|$)', r'"""\1"""', content)
    content = re.sub(r"'''([^']*?)(?=\n|$)", r"'''\1'''", content)
    
    # Паттерн 2: """текст\nтекст\nтекст (без закрывающих)
    lines = content.splitlines()
    fixed_lines = []
    in_multiline = False
    multiline_content = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Проверяем начало многострочной строки
        if '"""' in stripped or "'''" in stripped:
            if not in_multiline:
                # Начинается новая многострочная строка
                in_multiline = True
                multiline_content = [line]
                if '"""' in stripped:
                    string_delimiter = '"""'
                else:
                    string_delimiter = "'''"
            else:
                # Заканчивается многострочная строка
                if string_delimiter in stripped:
                    in_multiline = False
                    multiline_content.append(line)
                    fixed_lines.extend(multiline_content)
                    multiline_content = []
                else:
                    # Продолжение многострочной строки
                    multiline_content.append(line)
        elif in_multiline:
            # Мы внутри многострочной строки
            multiline_content.append(line)
        else:
            # Обычная строка
            fixed_lines.append(line)
    
    # Если мы все еще в многострочной строке, закрываем её
    if in_multiline and multiline_content:
        # Добавляем закрывающий разделитель к последней строке
        last_line = multiline_content[-1]
        if string_delimiter == '"""':
            last_line = last_line + '"""'
        else:
            last_line = last_line + "'''"
        multiline_content[-1] = last_line
        fixed_lines.extend(multiline_content)
    
    return '\n'.join(fixed_lines)

def fix_broken_function_calls(content):
    """Исправляет поврежденные вызовы функций."""
    print("    📞 Исправляю поврежденные вызовы функций...")
    
    lines = content.splitlines()
    fixed_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Исправляем незавершенные вызовы функций
        if stripped.endswith('(') and not stripped.startswith('#'):
            # Ищем имя функции
            if 'def ' in stripped or 'class ' in stripped:
                # Это определение, добавляем закрывающую скобку и двоеточие
                line = line.rstrip() + '):'
            else:
                # Это вызов функции, добавляем закрывающую скобку
                line = line.rstrip() + ')'
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def enhanced_step_by_step_recovery(content):
    """Улучшенное пошаговое восстановление с дополнительными проверками."""
    print("    🔄 Применяю улучшенное пошаговое восстановление...")
    
    # Шаг 1: Очистка от невидимых символов
    print("    🔧 Шаг 1: Очистка от невидимых символов...")
    content = re.sub(r'[^\x20-\x7E\n\t]', '', content)
    validate_step_result(content, "Очистка от невидимых символов")
    
    # Шаг 2: Исправление строк
    print("    🔧 Шаг 2: Исправление строк...")
    content = advanced_string_fix(content)
    validate_step_result(content, "Исправление строк")
    
    # Шаг 3: Исправление незавершенных строк
    print("    🔧 Шаг 3: Исправление незавершенных строк...")
    content = fix_unterminated_strings(content)
    validate_step_result(content, "Исправление незавершенных строк")
    
    # Шаг 3.5: Агрессивное исправление многострочных строк
    print("    🔧 Шаг 3.5: Агрессивное исправление многострочных строк...")
    content = fix_multiline_strings_aggressive(content)
    validate_step_result(content, "Агрессивное исправление многострочных строк")
    
    # Шаг 3.6: Умное исправление многострочных строк
    print("    🔧 Шаг 3.6: Умное исправление многострочных строк...")
    content = fix_multiline_strings_smart(content)
    validate_step_result(content, "Умное исправление многострочных строк")
    
    # Шаг 3.7: Исправление отступов в многострочных строках
    print("    🔧 Шаг 3.7: Исправление отступов в многострочных строках...")
    content = fix_multiline_indentation(content)
    validate_step_result(content, "Исправление отступов в многострочных строках")
    
    # Шаг 4: Исправление скобок
    print("    🔧 Шаг 4: Исправление скобок...")
    content = smart_bracket_fix(content)
    validate_step_result(content, "Исправление скобок")
    
    # Шаг 5: Исправление двоеточий
    print("    🔧 Шаг 5: Исправление двоеточий...")
    content = fix_missing_colons(content)
    validate_step_result(content, "Исправление двоеточий")
    
    # Шаг 6: Исправление вызовов функций
    print("    🔧 Шаг 6: Исправление вызовов функций...")
    content = fix_broken_function_calls(content)
    validate_step_result(content, "Исправление вызовов функций")
    
    # Шаг 7: Исправление импортов
    print("    🔧 Шаг 7: Исправление импортов...")
    content = fix_broken_import_statements(content)
    validate_step_result(content, "Исправление импортов")
    
    # Шаг 7.5: Восстановление структуры импортов
    print("    🔧 Шаг 7.5: Восстановление структуры импортов...")
    content = fix_import_structure(content)
    validate_step_result(content, "Восстановление структуры импортов")
    
    # Шаг 8: Исправление сложных отступов
    print("    🔧 Шаг 8: Исправление сложных отступов...")
    content = fix_complex_indentation_issues(content)
    validate_step_result(content, "Исправление сложных отступов")
    
    # Шаг 8.5: Исправление отступов в классах
    print("    🔧 Шаг 8.5: Исправление отступов в классах...")
    content = fix_class_indentation(content)
    validate_step_result(content, "Исправление отступов в классах")
    
    # Шаг 9: Контекстные исправления
    print("    🔧 Шаг 9: Контекстные исправления...")
    content = context_aware_fix(content)
    validate_step_result(content, "Контекстные исправления")
    
    # Шаг 9.5: Исправление определений функций и классов
    print("    🔧 Шаг 9.5: Исправление определений функций и классов...")
    content = fix_function_and_class_definitions(content)
    validate_step_result(content, "Исправление определений функций и классов")
    
    # Шаг 9.6: Добавление тел к пустым блокам
    print("    🔧 Шаг 9.6: Добавление тел к пустым блокам...")
    content = fix_empty_blocks(content)
    validate_step_result(content, "Добавление тел к пустым блокам")
    
    # Шаг 10: Критические исправления
    print("    🔧 Шаг 10: Критические исправления...")
    content = fix_critical_syntax_errors(content)
    validate_step_result(content, "Критические исправления")
    
    # Шаг 11: Финальная очистка
    print("    🔧 Шаг 11: Финальная очистка...")
    content = final_cleanup_and_validation(content)
    validate_step_result(content, "Финальная очистка")
    
    # Шаг 12: Простая валидация (без рекурсивных вызовов)
    print("    🔧 Шаг 12: Простая валидация...")
    if not validate_python_syntax(content):
        print("    ⚠️ Синтаксис все еще невалиден, применяю дополнительные исправления...")
        # Применяем дополнительные исправления без рекурсии
        content = fix_missing_colons(content)
        content = fix_unterminated_strings(content)
        content = fix_broken_function_calls(content)
        content = fix_broken_import_statements(content)
        content = fix_multiline_strings_aggressive(content)
        content = smart_bracket_fix(content)
        content = context_aware_fix(content)
    
    return content

def smart_repair_strategy_v2(content, damage_report):
    """Улучшенная умная стратегия исправления."""
    print(f"    📊 Анализ повреждений: {damage_report['damage_score']}/100")
    print(f"    📋 Рекомендации: {', '.join(damage_report['recommendations'])}")
    
    # Проверяем, есть ли синтаксические ошибки
    has_syntax_errors = len(damage_report['syntax_errors']) > 0
    
    if has_syntax_errors or damage_report['damage_score'] > 30:
        print("    🚨 Применяю улучшенное пошаговое восстановление...")
        return enhanced_step_by_step_recovery(content)
    elif has_syntax_errors or damage_report['damage_score'] > 20:
        print("    🚨 Применяю улучшенный экстренный ремонт...")
        return enhanced_emergency_repair(content)
    elif damage_report['damage_score'] > 10:
        print("    🔥 Применяю агрессивный ремонт...")
        return aggressive_repair(content)
    else:
        print("    🛡️ Применяю профилактические исправления...")
        return apply_preventive_fixes(content)

def ultra_aggressive_repair(content):
    """Ультра-агрессивный ремонт для критически поврежденных файлов."""
    print("    💀 Применяю ультра-агрессивный ремонт...")
    
    # Сначала применяем улучшенное пошаговое восстановление
    print("    🔄 Применяю улучшенное пошаговое восстановление...")
    content = enhanced_step_by_step_recovery(content)
    
    # Если файл все еще невалиден, применяем дополнительные агрессивные исправления
    if not validate_python_syntax(content):
        print("    💥 Применяю дополнительные агрессивные исправления...")
        content = fix_decimal_literals(content)
        content = fix_broken_import_statements(content)
        content = fix_complex_indentation_issues(content)
        content = restore_class_structure(content)
        content = fix_control_flow_structure(content)
        
        # Если файл все еще невалиден, применяем продвинутые агрессивные исправления
        if not validate_python_syntax(content):
            print("    💥 Применяю продвинутые агрессивные исправления...")
            content = advanced_aggressive_repair(content)
            
            # Если файл все еще невалиден, применяем сверхагрессивный ремонт
            if not validate_python_syntax(content):
                print("    💥 Применяю сверхагрессивный ремонт...")
                content = super_aggressive_repair(content)
                
                # Если файл все еще невалиден, применяем полное восстановление
                if not validate_python_syntax(content):
                    print("    🚨 Применяю полное восстановление файла...")
                    content = complete_file_recovery(content)
    
    return content

def final_cleanup_and_validation(content):
    """Финальная очистка и валидация исправленного кода."""
    print("    🧹 Финальная очистка и валидация...")
    
    lines = content.splitlines()
    fixed_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Убираем лишние пробелы в конце строк
        line = line.rstrip()
        
        # Исправляем очевидные проблемы
        if stripped.startswith('def ') and not stripped.endswith(':'):
            if stripped.endswith('()'):
                line = line + ':'
            elif stripped.endswith('('):
                line = line + '):'
            else:
                line = line + ':'
        
        elif stripped.startswith('class ') and not stripped.endswith(':'):
            if stripped.endswith('()'):
                line = line + ':'
            elif stripped.endswith('('):
                line = line + '):'
            else:
                line = line + ':'
        
        elif stripped.startswith(('if ', 'elif ', 'else:', 'for ', 'while ', 'try:', 'except', 'finally:', 'with ')):
            if not stripped.endswith(':'):
                line = line + ':'
        
        # Исправляем лишние отступы
        if stripped and not stripped.startswith('#'):
            current_indent = len(line) - len(line.lstrip())
            if current_indent > 0 and current_indent % 4 != 0:
                # Округляем отступ до ближайшего кратного 4
                new_indent = (current_indent // 4) * 4
                line = ' ' * new_indent + stripped
        
        fixed_lines.append(line)
    
    content = '\n'.join(fixed_lines)
    
    # Убираем пустые строки в конце файла
    content = content.rstrip('\n')
    
    # Добавляем одну пустую строку в конце
    content = content + '\n'
    
    return content

def post_repair_validation(content, recursion_depth=0):
    """Проверяет код после исправления и применяет дополнительные исправления если нужно."""
    print("    🔍 Пост-ремонтная валидация...")
    
    # Защита от рекурсии
    if recursion_depth > 2:
        print("    ⚠️ Достигнута максимальная глубина рекурсии, применяю экстренный ремонт...")
        return emergency_repair(content)
    
    # Проверяем синтаксис
    if validate_python_syntax(content):
        print("    ✅ Синтаксис валиден после исправления")
        return content
    
    print("    ⚠️ Синтаксис все еще невалиден, применяю дополнительные исправления...")
    
    # Применяем дополнительные исправления в правильном порядке
    print("    🔧 Шаг 1: Критические синтаксические исправления...")
    content = fix_critical_syntax_errors(content)
    
    print("    🔧 Шаг 2: Исправление определений функций и классов...")
    content = fix_function_and_class_definitions(content)
    
    print("    🔧 Шаг 3: Сложные проблемы с отступами...")
    content = fix_complex_indentation_issues(content)
    
    print("    🔧 Шаг 4: Финальная очистка...")
    content = final_cleanup_and_validation(content)
    
    # Дополнительная агрессивная проверка
    if not validate_python_syntax(content):
        print("    💥 Синтаксис все еще невалиден, применяю ультра-агрессивный ремонт...")
        content = ultra_aggressive_repair(content)
        
        # Финальная проверка после ультра-агрессивного ремонта
        if not validate_python_syntax(content):
            print("    🚨 Применяю экстренные исправления...")
            # Применяем все доступные исправления еще раз
            content = fix_missing_colons(content)
            content = fix_unterminated_strings(content)
            content = fix_broken_function_calls(content)
            content = fix_broken_import_statements(content)
            content = fix_multiline_strings_aggressive(content)
            content = smart_bracket_fix(content)
            content = context_aware_fix(content)
            
            # Если все еще невалиден, применяем экстренный ремонт
            if not validate_python_syntax(content):
                print("    🚨 Применяю экстренный ремонт как последнюю попытку...")
                content = emergency_repair(content)
    
    # Финальная проверка
    if validate_python_syntax(content):
        print("    ✅ Синтаксис исправлен после всех дополнительных исправлений")
    else:
        print("    ❌ Синтаксис все еще невалиден после всех исправлений")
        print("    📊 Файл требует ручного вмешательства")
    
    return content

def fix_function_and_class_definitions(content):
    """Специально исправляет определения функций и классов с правильными скобками."""
    print("    🏗️ Исправляю определения функций и классов...")
    
    lines = content.splitlines()
    fixed_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Исправляем определения функций
        if stripped.startswith('def '):
            # Убираем лишние пробелы
            clean_def = re.sub(r'def\s+', 'def ', stripped)
            
            # Ищем имя функции
            match = re.match(r'def\s+(\w+)', clean_def)
            if match:
                func_name = match.group(1)
                # Проверяем, есть ли уже скобки
                if '(' in clean_def and ')' in clean_def:
                    # Есть скобки, но может не хватать двоеточия
                    if not clean_def.endswith(':'):
                        clean_def = clean_def + ':'
                elif '(' in clean_def and ')' not in clean_def:
                    # Есть открывающая скобка, но нет закрывающей
                    clean_def = clean_def + '):'
                else:
                    # Нет скобок вообще, добавляем пустые скобки и двоеточие
                    clean_def = f'def {func_name}():'
                
                # Восстанавливаем отступы
                indent = len(line) - len(line.lstrip())
                fixed_lines.append(' ' * indent + clean_def)
            else:
                fixed_lines.append(line)
        
        # Исправляем определения классов
        elif stripped.startswith('class '):
            # Убираем лишние пробелы
            clean_class = re.sub(r'class\s+', 'class ', stripped)
            
            # Ищем имя класса
            match = re.match(r'class\s+(\w+)', clean_class)
            if match:
                class_name = match.group(1)
                # Проверяем, есть ли уже скобки
                if '(' in clean_class and ')' in clean_class:
                    # Есть скобки, но может не хватать двоеточия
                    if not clean_class.endswith(':'):
                        clean_class = clean_class + ':'
                elif '(' in clean_class and ')' not in clean_class:
                    # Есть открывающая скобка, но нет закрывающей
                    clean_class = clean_class + '):'
                else:
                    # Нет скобок вообще, добавляем пустые скобки и двоеточие
                    clean_class = f'class {class_name}():'
                
                # Восстанавливаем отступы
                indent = len(line) - len(line.lstrip())
                fixed_lines.append(' ' * indent + clean_class)
            else:
                fixed_lines.append(line)
        
        # Исправляем управляющие конструкции
        elif stripped.startswith(('if ', 'elif ', 'else:', 'for ', 'while ', 'try:', 'except', 'finally:', 'with ')):
            if not stripped.endswith(':'):
                # Проверяем, есть ли скобки
                if '(' in stripped and ')' not in stripped:
                    # Добавляем закрывающую скобку и двоеточие
                    line = line.rstrip() + '):'
                elif '(' in stripped and ')' in stripped:
                    # Есть скобки, просто добавляем двоеточие
                    line = line.rstrip() + ':'
                else:
                    # Нет скобок, просто добавляем двоеточие
                    line = line.rstrip() + ':'
            fixed_lines.append(line)
        else:
            fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def fix_multiline_strings_smart(content):
    """Умное исправление многострочных строк с анализом контекста."""
    print("    🧠 Умное исправление многострочных строк...")
    
    lines = content.splitlines()
    fixed_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Проверяем на начало многострочной строки
        if '"""' in stripped or "'''" in stripped:
            # Ищем конец многострочной строки
            string_delimiter = '"""' if '"""' in stripped else "'''"
            multiline_content = [line]
            i += 1
            
            # Собираем содержимое многострочной строки
            while i < len(lines):
                next_line = lines[i]
                if string_delimiter in next_line:
                    # Нашли конец строки
                    multiline_content.append(next_line)
                    i += 1
                    break
                else:
                    multiline_content.append(next_line)
                    i += 1
            else:
                # Не нашли конец строки, добавляем его
                last_line = multiline_content[-1]
                if not last_line.endswith(string_delimiter):
                    multiline_content[-1] = last_line + string_delimiter
            
            fixed_lines.extend(multiline_content)
        else:
            fixed_lines.append(line)
            i += 1
    
    return '\n'.join(fixed_lines)

def fix_import_structure(content):
    """Восстанавливает структуру импортов."""
    print("    📦 Восстанавливаю структуру импортов...")
    
    lines = content.splitlines()
    import_lines = []
    other_lines = []
    
    # Разделяем импорты и остальной код
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(('import ', 'from ')) or stripped.startswith('#'):
            import_lines.append(line)
        else:
            other_lines.append(line)
    
    # Сортируем импорты по типам
    standard_imports = []
    third_party_imports = []
    local_imports = []
    comments = []
    
    for line in import_lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            comments.append(line)
        elif stripped.startswith('import ') or stripped.startswith('from '):
            if any(pkg in stripped for pkg in ['os', 'sys', 're', 'json', 'datetime', 'pathlib', 'typing', 'collections']):
                standard_imports.append(line)
            elif any(pkg in stripped for pkg in ['numpy', 'pandas', 'matplotlib', 'requests', 'flask', 'django']):
                third_party_imports.append(line)
            else:
                local_imports.append(line)
    
    # Собираем импорты в правильном порядке
    fixed_imports = []
    
    # Стандартные импорты
    if standard_imports:
        fixed_imports.extend(standard_imports)
        fixed_imports.append('')
    
    # Сторонние библиотеки
    if third_party_imports:
        fixed_imports.extend(third_party_imports)
        fixed_imports.append('')
    
    # Локальные импорты
    if local_imports:
        fixed_imports.extend(local_imports)
        fixed_imports.append('')
    
    # Комментарии
    if comments:
        fixed_imports.extend(comments)
    
    # Объединяем все
    if fixed_imports and other_lines:
        # Убираем пустые строки в начале других строк
        while other_lines and not other_lines[0].strip():
            other_lines.pop(0)
        
        # Добавляем разделитель
        if fixed_imports and not fixed_imports[-1].strip():
            fixed_imports.pop()
        fixed_imports.append('')
    
    return '\n'.join(fixed_imports + other_lines)

def validate_step_result(content, step_name):
    """Проверяет результат каждого шага исправления."""
    print(f"    ✅ Проверяю результат шага: {step_name}")
    
    # Проверяем синтаксис
    try:
        ast.parse(content)
        print(f"    ✅ Шаг '{step_name}' прошел успешно")
        return True
    except SyntaxError as e:
        print(f"    ⚠️ Шаг '{step_name}' имеет синтаксические ошибки: {e}")
        return False
    except Exception as e:
        print(f"    ❌ Шаг '{step_name}' завершился с ошибкой: {e}")
        return False

def fix_class_indentation(content):
    """Исправляет отступы в классах и их методах."""
    print("    🏗️ Исправляю отступы в классах...")
    
    lines = content.splitlines()
    fixed_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Проверяем на определение класса
        if stripped.startswith('class ') and stripped.endswith(':'):
            fixed_lines.append(line)
            class_indent = len(line) - len(line.lstrip())
            i += 1
            
            # Обрабатываем содержимое класса
            while i < len(lines):
                next_line = lines[i]
                next_stripped = next_line.strip()
                
                # Если вышли из класса (меньший отступ)
                if next_stripped and len(next_line) - len(next_line.lstrip()) <= class_indent:
                    if not next_stripped.startswith('class ') and not next_stripped.startswith('def '):
                        break
                
                # Если это метод класса
                if next_stripped.startswith('def ') and next_stripped.endswith(':'):
                    # Правильный отступ для метода
                    correct_indent = class_indent + 4
                    if len(next_line) - len(next_line.lstrip()) != correct_indent:
                        next_line = ' ' * correct_indent + next_stripped
                    fixed_lines.append(next_line)
                    method_indent = correct_indent
                    i += 1
                    
                    # Обрабатываем содержимое метода
                    while i < len(lines):
                        method_line = lines[i]
                        method_stripped = method_line.strip()
                        
                        # Если вышли из метода
                        if method_stripped and len(method_line) - len(method_line.lstrip()) <= method_indent:
                            break
                        
                        # Правильный отступ для содержимого метода
                        if method_stripped:
                            correct_method_indent = method_indent + 4
                            if len(method_line) - len(method_line.lstrip()) != correct_method_indent:
                                method_line = ' ' * correct_method_indent + method_stripped
                        
                        fixed_lines.append(method_line)
                        i += 1
                else:
                    # Обычная строка в классе
                    if next_stripped:
                        correct_indent = class_indent + 4
                        if len(next_line) - len(next_line.lstrip()) != correct_indent:
                            next_line = ' ' * correct_indent + next_stripped
                    
                    fixed_lines.append(next_line)
                    i += 1
        else:
            fixed_lines.append(line)
            i += 1
    
    return '\n'.join(fixed_lines)

def fix_encoding_issues(content):
    """Исправляет проблемы с кодировкой файлов."""
    print("    🔤 Исправляю проблемы с кодировкой...")
    
    # Пробуем разные кодировки
    encodings = ['utf-8', 'cp1252', 'latin-1', 'iso-8859-1']
    
    for encoding in encodings:
        try:
            # Пробуем декодировать как bytes
            if isinstance(content, bytes):
                decoded = content.decode(encoding)
            else:
                # Если это строка, пробуем encode/decode
                encoded = content.encode(encoding, errors='ignore')
                decoded = encoded.decode(encoding)
            
            # Проверяем, что получилось что-то разумное
            if 'def ' in decoded or 'class ' in decoded or 'import ' in decoded:
                print(f"    ✅ Успешно исправлена кодировка: {encoding}")
                return decoded
                
        except Exception as e:
            continue
    
    # Если ничего не получилось, применяем агрессивную очистку
    print("    ⚠️ Не удалось исправить кодировку, применяю агрессивную очистку...")
    
    # Убираем все невидимые символы
    cleaned = ''
    for char in content:
        if char.isprintable() or char in '\n\t':
            cleaned += char
        else:
            cleaned += ' '
    
    return cleaned

def super_aggressive_repair(content):
    """Сверхагрессивный ремонт для критически поврежденных файлов."""
    print("    💥 Применяю сверхагрессивный ремонт...")
    
    # Сначала исправляем кодировку
    content = fix_encoding_issues(content)
    
    # Разбиваем на строки
    lines = content.splitlines()
    fixed_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Пропускаем пустые строки
        if not stripped:
            fixed_lines.append('')
            continue
        
        # Исправляем очевидные проблемы
        fixed_line = stripped
        
        # Исправляем разорванные импорты
        if 'import' in fixed_line and 'from' in fixed_line:
            fixed_line = fixed_line.replace('from', 'import')
        
        # Исправляем разорванные определения функций
        if fixed_line.startswith('def ') and not fixed_line.endswith(':'):
            if '(' in fixed_line and ')' not in fixed_line:
                fixed_line = fixed_line + '):'
            else:
                fixed_line = fixed_line + '():'
        
        # Исправляем разорванные определения классов
        if fixed_line.startswith('class ') and not fixed_line.endswith(':'):
            if '(' in fixed_line and ')' not in fixed_line:
                fixed_line = fixed_line + '):'
            else:
                fixed_line = fixed_line + '():'
        
        # Исправляем управляющие конструкции
        if fixed_line.startswith(('if ', 'elif ', 'for ', 'while ', 'try:', 'with ')):
            if not fixed_line.endswith(':'):
                fixed_line = fixed_line + ':'
        
        # Исправляем очевидные опечатки
        fixed_line = fixed_line.replace('pass', 'pass')
        fixed_line = fixed_line.replace('return', 'return')
        fixed_line = fixed_line.replace('True', 'True')
        fixed_line = fixed_line.replace('False', 'False')
        
        # Убираем лишние пробелы
        fixed_line = ' '.join(fixed_line.split())
        
        fixed_lines.append(fixed_line)
    
    # Собираем обратно
    content = '\n'.join(fixed_lines)
    
    # Добавляем базовую структуру если файл пустой
    if not content.strip():
        content = '''# Восстановленный файл
# Этот файл был критически поврежден

def main():
    """Основная функция"""
    pass

if __name__ == "__main__":
    main()
'''
    
    return content

def fix_multiline_indentation(content):
    """Исправляет отступы в многострочных строках."""
    print("    📐 Исправляю отступы в многострочных строках...")
    
    lines = content.splitlines()
    fixed_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Проверяем на многострочную строку
        if '"""' in stripped or "'''" in stripped:
            string_delimiter = '"""' if '"""' in stripped else "'''"
            multiline_content = [line]
            i += 1
            
            # Собираем содержимое многострочной строки
            while i < len(lines):
                next_line = lines[i]
                if string_delimiter in next_line:
                    # Нашли конец строки
                    multiline_content.append(next_line)
                    i += 1
                    break
                else:
                    # Исправляем отступы внутри многострочной строки
                    if next_line.strip():  # Если строка не пустая
                        # Определяем правильный отступ
                        base_indent = len(line) - len(line.lstrip())
                        content_indent = len(next_line) - len(next_line.lstrip())
                        
                        if content_indent < base_indent:
                            # Добавляем отступ
                            next_line = ' ' * base_indent + next_line.strip()
                        elif content_indent > base_indent + 8:
                            # Уменьшаем отступ
                            next_line = ' ' * (base_indent + 4) + next_line.strip()
                    
                    multiline_content.append(next_line)
                    i += 1
            else:
                # Не нашли конец строки, добавляем его
                last_line = multiline_content[-1]
                if not last_line.endswith(string_delimiter):
                    multiline_content[-1] = last_line + string_delimiter
            
            fixed_lines.extend(multiline_content)
        else:
            fixed_lines.append(line)
            i += 1
    
    return '\n'.join(fixed_lines)

def ultimate_file_recovery(content):
    """Сверхмощное восстановление критически поврежденных файлов."""
    print("    🚨 Применяю сверхмощное восстановление файла...")
    
    # Пробуем прочитать файл как bytes для исправления кодировки
    if isinstance(content, str):
        try:
            # Пробуем разные кодировки
            for encoding in ['utf-8', 'cp1252', 'latin-1', 'iso-8859-1']:
                try:
                    content_bytes = content.encode(encoding, errors='ignore')
                    content = content_bytes.decode(encoding, errors='ignore')
                    break
                except:
                    continue
        except:
            pass
    
    # Разбиваем на строки
    lines = content.splitlines()
    fixed_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Пропускаем пустые строки
        if not stripped:
            fixed_lines.append('')
            continue
        
        # Исправляем очевидные проблемы
        fixed_line = stripped
        
        # Убираем невидимые символы
        fixed_line = ''.join(char for char in fixed_line if char.isprintable() or char in ' \t')
        
        # Исправляем разорванные импорты
        if 'import' in fixed_line and 'from' in fixed_line:
            if fixed_line.count('import') > fixed_line.count('from'):
                fixed_line = fixed_line.replace('from', 'import')
            else:
                fixed_line = fixed_line.replace('import', 'from')
        
        # Исправляем определения функций
        if fixed_line.startswith('def '):
            # Ищем имя функции
            parts = fixed_line.split()
            if len(parts) >= 2:
                func_name = parts[1]
                # Убираем лишние символы из имени
                func_name = ''.join(c for c in func_name if c.isalnum() or c == '_')
                fixed_line = f'def {func_name}():'
        
        # Исправляем определения классов
        elif fixed_line.startswith('class '):
            # Ищем имя класса
            parts = fixed_line.split()
            if len(parts) >= 2:
                class_name = parts[1]
                # Убираем лишние символы из имени
                class_name = ''.join(c for c in class_name if c.isalnum() or c == '_')
                fixed_line = f'class {class_name}:'
        
        # Исправляем управляющие конструкции
        elif fixed_line.startswith(('if ', 'elif ', 'for ', 'while ', 'try:', 'with ')):
            if not fixed_line.endswith(':'):
                fixed_line = fixed_line + ':'
        
        # Исправляем очевидные опечатки
        fixed_line = fixed_line.replace('pass', 'pass')
        fixed_line = fixed_line.replace('return', 'return')
        fixed_line = fixed_line.replace('True', 'True')
        fixed_line = fixed_line.replace('False', 'False')
        
        # Убираем лишние пробелы
        fixed_line = ' '.join(fixed_line.split())
        
        fixed_lines.append(fixed_line)
    
    # Собираем обратно
    content = '\n'.join(fixed_lines)
    
    # Добавляем базовую структуру если файл пустой
    if not content.strip():
        content = '''# Восстановленный файл
# Этот файл был критически поврежден

def main():
    """Основная функция"""
    pass

if __name__ == "__main__":
    main()
'''
    
    return content

def read_file_with_encoding_fix(filepath):
    """Читает файл с автоматическим исправлением проблем кодировки."""
    print(f"    📖 Читаю файл с исправлением кодировки: {filepath}")
    
    # Пробуем разные кодировки
    encodings = ['utf-8', 'cp1252', 'latin-1', 'iso-8859-1']
    
    for encoding in encodings:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                content = f.read()
                print(f"    ✅ Успешно прочитан с кодировкой: {encoding}")
                return content
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"    ⚠️ Ошибка чтения с кодировкой {encoding}: {e}")
            continue
    
    # Если ничего не получилось, читаем как bytes и применяем агрессивную очистку
    print("    ⚠️ Не удалось прочитать с известными кодировками, применяю агрессивную очистку...")
    try:
        with open(filepath, 'rb') as f:
            content_bytes = f.read()
        
        # Пробуем декодировать с игнорированием ошибок
        for encoding in encodings:
            try:
                content = content_bytes.decode(encoding, errors='ignore')
                print(f"    ✅ Успешно декодирован с игнорированием ошибок: {encoding}")
                return content
            except:
                continue
        
        # Если ничего не получилось, возвращаем как строку с заменой невидимых символов
        content = content_bytes.decode('latin-1', errors='ignore')
        print("    ⚠️ Применена агрессивная очистка невидимых символов")
        return content
        
    except Exception as e:
        print(f"    ❌ Критическая ошибка чтения файла: {e}")
        return ""

def save_file(filepath, content):
    """Сохраняет файл с обработкой ошибок."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"    ❌ Ошибка сохранения файла: {e}")
        return False

def restore_from_backup(filepath):
    """Восстанавливает файл из резервной копии."""
    try:
        # Ищем последнюю резервную копию
        backup_dir = Path(".backups")
        if not backup_dir.exists():
            print("    ❌ Директория резервных копий не найдена")
            return False
        
        # Ищем файлы с именем нашего файла
        filename = Path(filepath).name
        backup_files = list(backup_dir.glob(f"{filename}.backup_*"))
        
        if not backup_files:
            print("    ❌ Резервные копии не найдены")
            return False
        
        # Берем самую новую
        latest_backup = max(backup_files, key=lambda x: x.stat().st_mtime)
        
        # Восстанавливаем
        with open(latest_backup, 'r', encoding='utf-8') as f:
            backup_content = f.read()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(backup_content)
        
        print(f"    ✅ Файл восстановлен из резервной копии: {latest_backup}")
        return True
        
    except Exception as e:
        print(f"    ❌ Ошибка восстановления из резервной копии: {e}")
        return False

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