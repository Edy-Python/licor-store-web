import mysql.connector
import pandas as pd

def migrar_inventario_oficial():
    try:
        conexion = mysql.connector.connect(
            host='localhost',
            database='sistema_inventario',
            user='root',
            password='Cr1sth14n', # Coloca tu clave
            port=3306
        )
        cursor = conexion.cursor()
        print("Conectado a MySQL. Leyendo Excel...")
        
        # CAMBIA ESTO por el nombre exacto del nuevo archivo Excel de tu cliente
        ruta_excel = r'D:\Ejercicios Python\Tienda_Crist.py\Database.xlsx'
        df = pd.read_excel(ruta_excel)
        
        # 1. Registrar categorías (Columna B: Categoria)
        categorias = df['Categoria'].dropna().unique()
        dicc_cat = {}
        for cat in categorias:
            cursor.execute("INSERT IGNORE INTO categorias (nombre) VALUES (%s)", (cat,))
            conexion.commit()
            cursor.execute("SELECT id_categoria FROM categorias WHERE nombre = %s", (cat,))
            dicc_cat[cat] = cursor.fetchone()[0]
            
        # 2. Registrar productos con los encabezados exactos de la imagen
        insertados = 0
        for index, row in df.iterrows():
            if pd.isna(row['Producto']) or pd.isna(row['Categoria']): 
                continue
                
            cat_id = dicc_cat[row['Categoria']]
            
            # Se respeta el nombre exacto de la columna "Stok (unidades)"
            valores = (
                cat_id,
                str(row['Producto']),
                str(row['Presentacion']),
                float(row['Precio unitario (S/.)']),
                float(row['Precio caja ($)']),
                float(row['Precio caja (S/.)']),
                int(row['Stok (unidades)'])
            )
            
            sql = """INSERT INTO productos 
                     (id_categoria, nombre, presentacion, precio, precio_caja_usd, precio_caja_pen, stock) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            cursor.execute(sql, valores)
            insertados += 1
            
        conexion.commit()
        print(f"¡Migración exitosa! {insertados} productos oficiales registrados.")
        
    except Exception as e:
        print(f"Error durante la migración: {e}")
    finally:
        if 'conexion' in locals() and conexion.is_connected():
            cursor.close()
            conexion.close()

if __name__ == '__main__':
    migrar_inventario_oficial()