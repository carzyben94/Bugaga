import requests
import json

# Встроенные куки прямо в коде
COOKIES = {
    "_ga_B9CY1C9VBC": "GS2.1.s1786752686$o1$g1$t1786752702$j44$l0$h0",
    "_ga": "GA1.1.1821388155.1786752686",
    "NID": "533=m1OjJ80EEpf6XPge09phLqkeY6YFt5ZtQ0r8Lvi9soijvNqXu5aqbc55UXOuuVEMoqc8IEqk1HU15tlMHdTrWhdJ3GOAMFZ2N8jAk3pbw8GhhbrQHB78yzFHIy-QPLe5lpADr7qARdA8Ih5GZTaRB9bG0-tb4yu6vB30_h6-W0yEgZfx97PZHqBKzDl2raZtyMSuK_8",
    "guest_id_marketing": "v1%3A178675259654555167",
    "guest_id_ads": "v1%3A178675259654555167",
    "personalization_id": "\"v1_Rik8XnBCUdSu/NJcDKc1pg==\"",
    "guest_id": "v1%3A178675259654555167",
    "__cf_bm": "lNapyeWDHAGFzi1zEC11UFNALeUsLNOWvTIk4ARDm3E-1786752596.4689136-1.0.1.1-McWNqxm_1lFvpaWX0gsGaJLGY11TqAJU_LXsGgqBtQS8zY3RbZ3HO_Bin2U9shJQ1NPqWnccXHJ7Ijf1x6SxjJ0JI3YdtLoyEImdd55TKFYB8xB96Q17Dyy8yLN0K7ww",
    "gt": "2088417578007839086",
    "__cuid": "42d48fab-94e0-45ea-9597-2c1848c2567a",
    "twid": "u%3D2075158859295997952",
    "auth_token": "5839949e4d83685926213037f9c747f0ae5f0b75",
    "ct0": "d9fe90fead05566aa72c02d54bade153d1e485366da157dea69dd6f60237a478c45f3ad131732aa8af0b4b240a99b712e4bca0005f13dd423a1110704bee8ab4e1ef5513d34b6dd7c2af5e8f987830d7",
    "g_state": "{\"i_l\":1,\"i_ll\":1786752531634,\"i_b\":\"L8IFMpD6ZrVVSrl3gX7LFhlLLW27n9P9rM5W3Dno6Qs\",\"i_e\":{\"enable_itp_optimization\":24},\"i_et\":1786752531634}",
    "lang": "ru",
    "IDE": "AHWqTUluuhD4Jbd4dOmxHHwp_vVpYOHyikeh27DDLve6O8f4aWsNoJ5wsdq9C8-7R1Y"
}

def get_session():
    """Возвращает сессию requests с куками"""
    session = requests.Session()
    session.cookies.update(COOKIES)
    return session

def get_cookies():
    """Возвращает словарь с куками"""
    return COOKIES.copy()

# Пример использования
if __name__ == "__main__":
    session = get_session()
    
    # Проверка доступа к X
    try:
        resp = session.get('https://x.com/home', timeout=10)
        print(f"Статус: {resp.status_code}")
        if resp.status_code == 200:
            print("✅ Доступ к X.com есть!")
    except Exception as e:
        print(f"❌ Ошибка: {e}")