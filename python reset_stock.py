import mysql.connector

def resetear_stock_temporal():
    try:
        # 1. Configura tus datos de conexión (los mismos de tu .env o variables)
        conexion = mysql.connector.connect(
            host="autorack.proxy.rlwy.net",
            user="root",
            password="LWSwvsNlJSgYvSIHUakxautShyLgNJie",
            database="railway",
            port=15565
        )
        
        cursor = conexion.cursor()

        # 2. Ejecutar la actualización (Cambia 'productos' y 'stock' si tus columnas se llaman diferente)
        # ESTE COMANDO SOLO ACTUALIZA EL NÚMERO A 0, NO BORRA NADA MÁS.
        sql = "UPDATE productos SET stock = 0"
        
        cursor.execute(sql)
        conexion.commit() # Confirmar los cambios
        
        print(f"✅ ¡Éxito! Se actualizó el stock a 0 en {cursor.rowcount} productos.")

    except mysql.connector.Error as error:
        print(f"❌ Error al conectar o actualizar MySQL: {error}")
        
    finally:
        # 3. Cerrar conexiones de forma segura
        if conexion.is_connected():
            cursor.close()
            conexion.close()
            print("🔒 Conexión a MySQL cerrada correctamente.")

if __name__ == "__main__":
    resetear_stock_temporal()