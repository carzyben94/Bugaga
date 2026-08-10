# ============================================================
# КУКИ ДЛЯ X.COM (TWITTER)
# ============================================================

COOKIES = [
    {
        "domain": ".x.com",
        "name": "__cuid",
        "value": "55d2d7c5-4888-430a-b024-dd785da46ef4",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified",
        "session": True
    },
    {
        "domain": ".x.com",
        "name": "lang",
        "value": "ru",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified",
        "session": True
    },
    {
        "domain": ".x.com",
        "name": "dnt",
        "value": "1",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified",
        "session": True
    },
    {
        "domain": ".x.com",
        "name": "guest_id",
        "value": "v1%3A178267838599411411",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified",
        "session": True
    },
    {
        "domain": ".x.com",
        "name": "guest_id_marketing",
        "value": "v1%3A178267838599411411",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified",
        "session": True
    },
    {
        "domain": ".x.com",
        "name": "guest_id_ads",
        "value": "v1%3A178267838599411411",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified",
        "session": True
    },
    {
        "domain": ".x.com",
        "name": "personalization_id",
        "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\"",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified",
        "session": True
    },
    {
        "domain": ".x.com",
        "name": "twid",
        "value": "u%3D2067347503503052800",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified",
        "session": True
    },
    {
        "domain": ".x.com",
        "name": "auth_token",
        "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified",
        "session": True
    },
    {
        "domain": ".x.com",
        "name": "ct0",
        "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified",
        "session": True
    },
    {
        "domain": ".x.com",
        "name": "__cf_bm",
        "value": "9YX04RS0xZFBBYvxRkKst23cAU7kJoVapgS2sLSMbSk-1786386173.5554872-1.0.1.1-y1xsH2BFbSOdTQLG0h8CoZ_AsL1v.81lOka84MA_HmqcfpbtaQ2e6ok8TRyg9xqmNGBjtxBSrf9wo6vJ4iJFWcjGVj7n9oXCiQSPXVPw_2SPMcbMcUWzbacWV5JcCeyR",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified",
        "session": True
    },
]

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def get_cookies_for_domain(domain: str) -> list:
    """Возвращает куки для конкретного домена"""
    return [c for c in COOKIES if domain in c.get("domain", "")]

def get_cookies_dict() -> dict:
    """Возвращает словарь {name: value} для всех кук"""
    return {c["name"]: c["value"] for c in COOKIES}