# crypto.py
import requests
import threading

def register_crypto(bot):
    """Регистрирует обработчик команды /crypto"""
    
    @bot.message_handler(commands=['crypto'])
    def crypto_command(message):
        status_msg = bot.reply_to(message, "💰 Узнаю курсы криптовалют...")
        
        def do_crypto():
            try:
                # BTC
                r1 = requests.get("https://api.binance.com/api/v3/ticker/price", 
                                  params={"symbol": "BTCUSDT"}, timeout=10)
                # ETH
                r2 = requests.get("https://api.binance.com/api/v3/ticker/price", 
                                  params={"symbol": "ETHUSDT"}, timeout=10)
                
                if r1.status_code != 200 or r2.status_code != 200:
                    bot.edit_message_text("❌ Ошибка Binance API", 
                                          chat_id=message.chat.id, 
                                          message_id=status_msg.message_id)
                    return
                
                btc_usd = float(r1.json().get('price', 0))
                eth_usd = float(r2.json().get('price', 0))
                
                # RUB
                r3 = requests.get("https://api.binance.com/api/v3/ticker/price", 
                                  params={"symbol": "USDRUB"}, timeout=10)
                usd_rub = float(r3.json().get('price', 95)) if r3.status_code == 200 else 95
                
                btc_rub = round(btc_usd * usd_rub, 2)
                eth_rub = round(eth_usd * usd_rub, 2)
                
                result = (
                    "🟡 BITCOIN (BTC):\n"
                    f"  • USD: ${btc_usd:,.2f}\n"
                    f"  • EUR: €{btc_usd * 0.92:,.2f}\n"
                    f"  • RUB: {btc_rub:,.2f} ₽\n\n"
                    "🔷 ETHEREUM (ETH):\n"
                    f"  • USD: ${eth_usd:,.2f}\n"
                    f"  • EUR: €{eth_usd * 0.92:,.2f}\n"
                    f"  • RUB: {eth_rub:,.2f} ₽"
                )
                
                bot.edit_message_text(result, 
                                      chat_id=message.chat.id, 
                                      message_id=status_msg.message_id)
                
            except Exception as e:
                bot.edit_message_text(f"❌ Ошибка: {str(e)[:100]}", 
                                      chat_id=message.chat.id, 
                                      message_id=status_msg.message_id)
        
        threading.Thread(target=do_crypto, daemon=True).start()