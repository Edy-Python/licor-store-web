import os
from dotenv import load_dotenv

# Carga los datos de tu archivo secreto .env
load_dotenv()

# La configuración que tu programa está buscando
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASS'),
    'port': 3306
}

# Los usuarios que tu programa está buscando
USUARIOS = {
    "Cristian": {
        "password_hash": "03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4", 
        "rol": "admin"
    },
    "Yoselyn": {
        "password_hash": "9af15b336e6a9619928537df30b2e6a2376569fcf9d7e773eccede65606529a0", 
        "rol": "vendedor"
    }
}