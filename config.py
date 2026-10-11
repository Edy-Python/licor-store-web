import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

APP_TIMEZONE = os.getenv("APP_TIMEZONE", "America/Lima")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "autorack.proxy.rlwy.net"),
    "user": os.getenv("DB_USER", "root"), 
    "password": os.getenv("DB_PASSWORD", "LWSwvsNlJSgYvSIHUakxautShyLgNJie"), 
    "database": os.getenv("DB_NAME", "railway"), 
    "port": int(os.getenv("DB_PORT", 15565))
}

USUARIOS = {
    "admin@likio.com": {
        "rol": "admin",
        "password_hash": "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92" 
    },
    "vendedor@likio.com": {
        "rol": "vendedor",
        "password_hash": "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92"
    }
}   