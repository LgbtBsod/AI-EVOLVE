#!/usr/bin/env python3
"""
Демонстрация умного управления резервными копиями и файлами целостности
"""

from fix_python_files import (
    backup_manager,
    show_backup_status,
    manual_cleanup,
    smart_backup_management,
    force_cleanup_all_backups,
    cleanup_old_backups_by_age
)

def main():
    print("🧠 Демонстрация умного управления резервными копиями")
    print("=" * 60)
    
    # 1. Показываем текущий статус
    print("\n1️⃣ Текущий статус резервных копий:")
    show_backup_status()
    
    # 2. Настраиваем умное управление
    print("\n2️⃣ Настройка умного управления:")
    backup_dir = smart_backup_management()
    print(f"   📁 Директория бэкапов: {backup_dir}")
    
    # 3. Показываем обновленный статус
    print("\n3️⃣ Обновленный статус:")
    show_backup_status()
    
    # 4. Демонстрируем ручную очистку
    print("\n4️⃣ Демонстрация ручной очистки:")
    print("   (Это безопасная операция - удаляются только старые файлы)")
    
    response = input("   Продолжить с очисткой? (y/N): ").strip().lower()
    if response == 'y':
        manual_cleanup()
    else:
        print("   Очистка пропущена")
    
    # 5. Показываем статус после очистки
    print("\n5️⃣ Статус после очистки:")
    show_backup_status()
    
    # 6. Демонстрируем очистку по возрасту
    print("\n6️⃣ Очистка файлов старше 7 дней:")
    response = input("   Продолжить? (y/N): ").strip().lower()
    if response == 'y':
        cleanup_old_backups_by_age(7)
    else:
        print("   Очистка пропущена")
    
    # 7. Финальный статус
    print("\n7️⃣ Финальный статус:")
    show_backup_status()
    
    print("\n" + "=" * 60)
    print("✅ Демонстрация завершена!")
    print("💡 Основные команды:")
    print("   - show_backup_status() - показать статус бэкапов")
    print("   - manual_cleanup() - ручная очистка")
    print("   - smart_backup_management() - настройка умного управления")
    print("   - cleanup_old_backups_by_age(7) - очистка старых файлов")
    print("   - force_cleanup_all_backups() - принудительная очистка всех")
    print("=" * 60)
    
    # 8. Показываем конфигурацию
    print("\n8️⃣ Текущая конфигурация:")
    print(f"   📊 Максимум бэкапов на файл: {backup_manager.max_backups_per_file}")
    print(f"   📅 Максимальный возраст файлов: {backup_manager.max_backup_age_days} дней")
    print(f"   📁 Директория бэкапов: {backup_manager.backup_dir}")
    print(f"   📋 Директория целостности: {backup_manager.integrity_dir}")
    
    # 9. Предлагаем изменить конфигурацию
    print("\n9️⃣ Настройка конфигурации:")
    try:
        new_max = int(input("   Новый максимум бэкапов на файл (текущий: {}): ".format(
            backup_manager.max_backups_per_file)) or backup_manager.max_backups_per_file)
        new_age = int(input("   Новый максимальный возраст в днях (текущий: {}): ".format(
            backup_manager.max_backup_age_days)) or backup_manager.max_backup_age_days)
        
        if new_max != backup_manager.max_backups_per_file or new_age != backup_manager.max_backup_age_days:
            backup_manager.max_backups_per_file = new_max
            backup_manager.max_backup_age_days = new_age
            backup_manager.save_config()
            print("   ✅ Конфигурация обновлена и сохранена!")
        else:
            print("   ➖ Конфигурация не изменена")
    except ValueError:
        print("   ❌ Некорректные значения, конфигурация не изменена")
    
    print("\n" + "=" * 60)
    print("🎉 Демонстрация полностью завершена!")
    print("💡 Теперь у вас есть умная система управления бэкапами!")
    print("=" * 60)

if __name__ == '__main__':
    main()
