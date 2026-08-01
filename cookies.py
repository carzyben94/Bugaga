# cookies.py - ПОЛНОСТЬЮ ОЧИЩЕН ОТ ДУБЛИКАТОВ

COOKIES = [
    # === X.com ===
    {"domain": ".x.com", "name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"},
    {"domain": ".x.com", "name": "lang", "value": "ru"},
    {"domain": ".x.com", "name": "dnt", "value": "1"},
    {"domain": ".x.com", "name": "guest_id", "value": "v1%3A178267838599411411"},
    {"domain": ".x.com", "name": "guest_id_marketing", "value": "v1%3A178267838599411411"},
    {"domain": ".x.com", "name": "guest_id_ads", "value": "v1%3A178267838599411411"},
    {"domain": ".x.com", "name": "personalization_id", "value": '"v1_DKrxLZAC902dMFdd1QrVYg=="'},
    {"domain": ".x.com", "name": "twid", "value": "u%3D2067347503503052800"},
    {"domain": ".x.com", "name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936"},
    {"domain": ".x.com", "name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb"},
    {"domain": ".x.com", "name": "__cf_bm", "value": "rgpecDD.nJZW.PDvUwZ7PnWS.JOBSsUHl1uwuBvlvm0-1784475398.7921503-1.0.1.1-Jh7pm287WlmOXhd1JOwAVbsFYWkIh._GtcIsZAf_n.vP8Os7kJAOjJ.Jg2Rw9cOwixM4iLu0WsOC2uyC6lJfG_cb4Sl1H6fr5jYvSYUr6rNJ.w_I8aFoDCu12CVOpnev"},

    # === chat.z.ai ===
    {"domain": ".chat.z.ai", "name": "cdn_sec_tc", "value": "2ff6319617852874661382491e2022a3810e56e1c8bc489c8c4978fac9"},
    {"domain": ".chat.z.ai", "name": "_gcl_au", "value": "1.1.1857168779.1785287466"},
    {"domain": ".chat.z.ai", "name": "_ga", "value": "GA1.1.1016160882.1785287466"},
    {"domain": ".chat.z.ai", "name": "_c_WBKFRo", "value": "A8vjfrQNoknQJjsZrwLZGxLrKiTznLhU1lwFORBD"},
    {"domain": ".chat.z.ai", "name": "token", "value": "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjdjNGM2OWEwLWI5M2ItNDVmNS05ZDllLTk1NThiMGMwMmM4YyIsImVtYWlsIjoia3VmYzQxOTBAZ21haWwuY29tIn0.1iN6DbuWvbyGU3pj7dGi2iggs9OpMjgxtXK1TdsM89R366-yqTzzr9LWDi4U12NcJHnDJRsm1p3xVJHotif9Zg"},

    # === chat.qwen.ai ===
    {"domain": ".chat.qwen.ai", "name": "acw_tc", "value": "0a03e58c17854132788371257e493d0bf6508ae037f98bf6881a6e0b9bf076"},
    {"domain": ".chat.qwen.ai", "name": "x-ap", "value": "eu-central-1"},
    {"domain": ".chat.qwen.ai", "name": "sca", "value": "a7ce4259"},
    {"domain": ".chat.qwen.ai", "name": "cna", "value": "oCzyIocOjQECAbKFlPmTst6p"},
    {"domain": ".chat.qwen.ai", "name": "qwen-theme", "value": "light"},
    {"domain": ".chat.qwen.ai", "name": "qwen-locale", "value": "ru-RU"},
    {"domain": ".chat.qwen.ai", "name": "xlly_s", "value": "1"},
    {"domain": ".chat.qwen.ai", "name": "_c_WBKFRo", "value": "9x0wmbJ5TK9vyb7WUUOP1txc6zIT1FM1q4S6pFBG"},
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

# Функции для совместимости
COOKIES_UNIQUE = COOKIES

def get_cookies_for_domain(domain: str) -> list:
    """Возвращает куки для конкретного домена"""
    return [c for c in COOKIES_UNIQUE if domain in c.get("domain", "")]