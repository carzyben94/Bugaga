import os
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return 'Бот работает!'

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    # Здесь будет логика вашего бота
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
