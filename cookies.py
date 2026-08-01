# cookies.py - Абсолютно чистая версия, дубликатов НЕТ

COOKIES = [
    # --- chat.qwen.ai (только уникальные имена) ---
    {"domain": ".chat.qwen.ai", "name": "acw_tc", "value": "0a03e58c17854132788371257e493d0bf6508ae037f98bf6881a6e0b9bf076"},
    {"domain": ".chat.qwen.ai", "name": "x-ap", "value": "eu-central-1"},
    {"domain": ".chat.qwen.ai", "name": "sca", "value": "a7ce4259"},
    {"domain": ".chat.qwen.ai", "name": "cna", "value": "oCzyIocOjQECAbKFlPmTst6p"},
    {"domain": ".chat.qwen.ai", "name": "qwen-theme", "value": "light"},
    {"domain": ".chat.qwen.ai", "name": "qwen-locale", "value": "ru-RU"},
    {"domain": ".chat.qwen.ai", "name": "xlly_s", "value": "1"},
    {"domain": ".chat.qwen.ai", "name": "_nb_ioWEgULi", "value": ""},
    {"domain": ".chat.qwen.ai", "name": "token", "value": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6ImJlNWQwNGIzLTY0MDQtNGRiZC1iMTBhLWFmMGU4OWZjMzlhNCIsImxhc3RfcGFzc3dvcmRfY2hhbmdlIjoxNzg1NDEzMzkxLCJleHAiOjE3ODgwMDU0MjV9.VMUns9QzpJdRNC7QH3JhtF9ge_CuIXa4oWDW9Zb4eSA"},
    {"domain": ".chat.qwen.ai", "name": "cnaui", "value": "be5d04b3-6404-4dbd-b10a-af0e89fc39a4"},
    {"domain": ".chat.qwen.ai", "name": "aui", "value": "be5d04b3-6404-4dbd-b10a-af0e89fc39a4"},
    {"domain": ".chat.qwen.ai", "name": "atpsida", "value": "19a194cbe9de439f3c8d1a55_1785413426_6"},
    {"domain": ".chat.qwen.ai", "name": "ssxmod_itna", "value": "1-mqUxBD0DRDcAqqeKYIx0QG73iOG2UDm2DBP01k7Dux4jKid3DUDQTlmxBBnxqD=TuSE74DkinTyQ1DBk4oDRxAtHDm4iawC1qht_ei00gmI3YQ7RAs3FzI2RswoKzo4SXxRUBZcRHHvL4wDDTDmKDUPPDBxDYre2T1DD8ehmxwDiTrDDkeS4D5g0_H40iLxiiW1gY3nubjt4H2byYuinQdiiieG9QqG0DDTGHYhKHPwojLIlNe=_vDl9uDCIIkjYDoO752Q_pqOy8w2dx37eqeOGOSAqNVeWgmyQqDTogtQ4o37OFAhWjwQD\/pQeYD"},
    {"domain": ".chat.qwen.ai", "name": "ssxmod_itna2", "value": "1-mqUxBD0DRDcAqqeKYIx0QG73iOG2UDm2DBP01k7Dux4jKid3DUDQTlmxBBnxqD=TuSE74DkinTyjrD88e_rwWGGYbeDFOIho7y3p3D\/9IaCHANNLT5XsxaimGkvRvmKhD"},
    {"domain": ".chat.qwen.ai", "name": "tfstk", "value": "gR7iih0P1_HG_rkUrx8_YSK-P-j05FTXqt3vHEp4YpJCWtE6HMYVaTxv0lsOKf_hEq3TCl1qoEL4e8U8y1G6lEyRfhMsFdOfTKPpbrrNjWY4e8UpNxeECE5vWP-VT6JBiCo2gtzELpOM_EJw0voeapJ2ut-ZLvR6GKkqudJUtI9e3E8V36PHMpJ2uEWVTBDmCdIFAwy8CVeeSg7V-CxMU1ziuqbnyhvP_p04WwAghL5wKquvFip75_X0I4ONoCbkjMwj51THVOxGoR4yWeJ1ICtQomTV4qoE4NztlLUhGmiXbBOHegSMFwjuK1bbtWmPUhRBT5F3tmiXbBOHeWVnqt-wOBPO."},
    {"domain": ".chat.qwen.ai", "name": "isg", "value": "BLe3U08PkeVqshVpxzob2N4jTakBfIvejF3bOAlkzgbtuNT6EU1RLpWKnUZDfmNW"}
]

# --- Вспомогательные функции ---
COOKIES_UNIQUE = COOKIES

def get_cookies_for_domain(domain: str) -> list:
    """Возвращает куки для конкретного домена (без дубликатов)"""
    return [c for c in COOKIES_UNIQUE if domain in c.get("domain", "")]