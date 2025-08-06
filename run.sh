#!/bin/bash

cd "$(dirname "$0")"  

if [ ! -d "venv" ]; then
    echo "🔧 Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing requirements..."
pip install -r requirements.txt

mkdir -p logs

echo "Starting userbot..."
exec python3 -u -m bot.main