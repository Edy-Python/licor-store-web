import mysql.connector
from config import DB_CONFIG

try:
    print("Conectando a la base de datos...")
    conexion = mysql.connector.connect(**DB_CONFIG)
    cursor = conexion.cursor()

    # Comando para agregar la columna 'estado' a tu tabla en la nube
    cursor.execute("ALTER TABLE ventas ADD COLUMN estado VARCHAR(20) DEFAULT 'Completada';")
    conexion.commit()

    print("✅ ¡Éxito! La columna 'estado' se agregó correctamente a la tabla de ventas.")

except mysql.connector.Error as err:
    if err.errno == 1060:
        print("✅ La columna 'estado' ya existe. ¡Todo está listo para continuar!")
    else:
        print(f"❌ Error de base de datos: {err}")
finally:
    if 'conexion' in locals() and conexion.is_connected():
        cursor.close()
        conexion.close()