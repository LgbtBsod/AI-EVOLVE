#!/bin/bash
echo "📦 Установка зависимостей..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
if [ $? -eq 0 ]; then
    echo "✅ Зависимости установлены успешно!"
    echo "Теперь можно запустить ./start_game.sh"
else
    echo "❌ Ошибка установки зависимостей"
    echo "Проверьте подключение к интернету"
fi
read -p "Нажмите Enter для выхода..."
