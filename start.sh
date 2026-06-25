#!/bin/bash

echo "🔄 Запуск Xvfb на дисплее :99..."
Xvfb :99 -screen 0 1280x1024x24 -ac &

# Ждем запуска Xvfb
sleep 3

# Проверяем, что Xvfb запущен
if ! pgrep -x "Xvfb" > /dev/null; then
    echo "❌ Xvfb не запустился!"
    exit 1
fi

echo "✅ Xvfb запущен на :99"

# Устанавливаем переменную для Chrome
export DISPLAY=:99

echo "🚀 Запуск бота..."
python bot.py