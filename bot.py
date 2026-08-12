# test_websocket.py - проверка через WebSocket + CDP
import asyncio
import websockets
import json
import httpx

CDP_URL = "https://9d683906-74b6-44a1-a138-c33b957fb907.cdp.browser-use.com"

async def test_cdp_websocket():
    print(f"🔗 Подключение к CDP: {CDP_URL}")
    
    try:
        # 1. Получаем WebSocket URL
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{CDP_URL}/json/version")
            data = resp.json()
            ws_url = data.get("webSocketDebuggerUrl")
            
            if not ws_url:
                print("❌ WebSocket URL не найден")
                return False
            
            # Конвертируем http -> ws
            if ws_url.startswith("http://"):
                ws_url = ws_url.replace("http://", "ws://")
            elif ws_url.startswith("https://"):
                ws_url = ws_url.replace("https://", "wss://")
            
            print(f"🔌 WebSocket: {ws_url}")
        
        # 2. Подключаемся
        ws = await websockets.connect(ws_url)
        print("✅ WebSocket подключен")
        
        # 3. Отправляем простую команду
        msg_id = 1
        await ws.send(json.dumps({
            "id": msg_id,
            "method": "Browser.getVersion",
            "params": {}
        }))
        
        # 4. Ждём ответ
        response = await ws.recv()
        data = json.loads(response)
        
        if data.get("id") == msg_id:
            result = data.get("result", {})
            print(f"✅ Браузер: {result.get('product', 'unknown')}")
            print(f"   User-Agent: {result.get('userAgent', 'unknown')[:50]}...")
            print("✅ Подключение работает!")
            await ws.close()
            return True
        else:
            print("❌ Неправильный ответ")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_cdp_websocket())