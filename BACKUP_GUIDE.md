# 🧠 Умное управление резервными копиями

## 🎯 Основные преимущества

✅ **Централизованное хранение** - все бэкапы в одной папке `.backups/`  
✅ **Автоматическая очистка** - старые файлы удаляются автоматически  
✅ **Умное ограничение** - максимум 3 бэкапа на файл  
✅ **Файлы целостности** - в отдельной папке `.integrity/`  
✅ **Автоматический .gitignore** - бэкапы не попадают в git  

## 🚀 Быстрый старт

```bash
# Запуск основной утилиты
python fix_python_files.py

# Демонстрация возможностей
python demo_smart_backup.py
```

## 📋 Основные команды

### Просмотр статуса
```python
from fix_python_files import show_backup_status
show_backup_status()
```

### Ручная очистка
```python
from fix_python_files import manual_cleanup
manual_cleanup()  # Удаляет файлы старше 7 дней
```

### Очистка по возрасту
```python
from fix_python_files import cleanup_old_backups_by_age
cleanup_old_backups_by_age(3)  # Удаляет файлы старше 3 дней
```

### Принудительная очистка всех
```python
from fix_python_files import force_cleanup_all_backups
force_cleanup_all_backups()  # Удаляет ВСЕ бэкапы
```

## ⚙️ Настройка

### Изменение конфигурации
```python
from fix_python_files import backup_manager

# Изменить максимальное количество бэкапов на файл
backup_manager.max_backups_per_file = 5

# Изменить максимальный возраст файлов в днях
backup_manager.max_backup_age_days = 14

# Сохранить конфигурацию
backup_manager.save_config()
```

### Просмотр конфигурации
```python
print(f"Максимум бэкапов: {backup_manager.max_backups_per_file}")
print(f"Максимальный возраст: {backup_manager.max_backup_age_days} дней")
print(f"Директория бэкапов: {backup_manager.backup_dir}")
print(f"Директория целостности: {backup_manager.integrity_dir}")
```

## 🔍 Структура файлов

```
AI-EVOLVE/
├── .backups/           # Все резервные копии
│   ├── file1.py.backup_20241201_143022
│   ├── file2.py.backup_20241201_143025
│   └── ...
├── .integrity/         # Файлы проверки целостности
│   ├── file1.py.integrity
│   ├── file2.py.integrity
│   └── ...
├── .backup_config.json # Конфигурация системы
├── .gitignore          # Автоматически обновляется
└── ...
```

## 🧹 Автоматическая очистка

### Когда происходит очистка:
- ✅ При запуске `fix_python_files.py`
- ✅ При вызове `manual_cleanup()`
- ✅ При вызове `cleanup_old_files()`

### Что удаляется:
- 🔴 Бэкапы старше 7 дней (по умолчанию)
- 🔴 Файлы целостности старше 7 дней
- 🔴 Лишние бэкапы (больше 3 на файл)

## 🚨 Восстановление файлов

### Из резервной копии:
```python
import shutil
shutil.copy2('.backups/filename.py.backup_20241201_143022', 'filename.py')
```

### Проверка целостности:
```python
import json
with open('.integrity/filename.py.integrity', 'r') as f:
    metadata = json.load(f)
    print(f"MD5: {metadata['md5_hash']}")
    print(f"Размер: {metadata['size_bytes']} байт")
```

## 💡 Лучшие практики

1. **Регулярно запускайте** `python fix_python_files.py`
2. **Проверяйте статус** через `show_backup_status()`
3. **Очищайте старые файлы** через `manual_cleanup()`
4. **Настраивайте лимиты** под ваши потребности
5. **Используйте .gitignore** для исключения бэкапов из git

## 🔧 Устранение проблем

### Проблема: Много старых бэкапов
```python
# Решение: принудительная очистка
force_cleanup_all_backups()
```

### Проблема: Бэкапы не удаляются
```python
# Решение: проверьте права доступа и запустите
backup_manager.cleanup_old_files()
```

### Проблема: Файлы целостности не создаются
```python
# Решение: проверьте права на запись в .integrity/
backup_manager.integrity_dir.mkdir(exist_ok=True)
```

## 📊 Мониторинг

### Проверка размера директорий:
```python
import os
backup_size = sum(f.stat().st_size for f in backup_manager.backup_dir.rglob('*') if f.is_file())
integrity_size = sum(f.stat().st_size for f in backup_manager.integrity_dir.rglob('*') if f.is_file())

print(f"Размер .backups/: {backup_size / 1024:.1f} KB")
print(f"Размер .integrity/: {integrity_size / 1024:.1f} KB")
```

### Статистика по файлам:
```python
backup_files = list(backup_manager.backup_dir.glob('*.backup_*'))
integrity_files = list(backup_manager.integrity_dir.glob('*.integrity'))

print(f"Всего бэкапов: {len(backup_files)}")
print(f"Всего файлов целостности: {len(integrity_files)}")
```

---

**🎉 Теперь у вас есть умная система управления бэкапами, которая не засоряет проект!**
