"""
Script de prueba y demostración en archivo temporal (SQLite).
Permite verificar y ejecutar el sistema de inventario sin depender de MySQL.
"""
import os
import sqlite3
import re

DB_TEMP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_licor_store.db")

def conectar_temp():
    """Conecta a la base de datos temporal SQLite local."""
    conn = sqlite3.connect(DB_TEMP_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_bd_temporal():
    """Crea la tabla productos con las columnas requeridas si no existe."""
    conn = conectar_temp()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_producto TEXT DEFAULT '',
            orden INTEGER NOT NULL DEFAULT 0,
            nombre TEXT NOT NULL,
            presentacion TEXT DEFAULT 'UNIDAD',
            categoria TEXT DEFAULT 'LICOR',
            grupo_surtido TEXT DEFAULT '',
            stock INTEGER NOT NULL DEFAULT 0,
            codigo_barras TEXT DEFAULT '',
            costo_uni_pen REAL NOT NULL DEFAULT 0.00,
            costo_uni_usd REAL NOT NULL DEFAULT 0.00,
            precio_uni_pen REAL NOT NULL DEFAULT 0.00,
            precio_uni_usd REAL NOT NULL DEFAULT 0.00,
            precio_caja_pen REAL NOT NULL DEFAULT 0.00,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prod_sku ON productos(codigo_producto);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prod_orden ON productos(orden);")
    conn.commit()

    # Si la tabla está vacía, sembramos datos de prueba
    cursor.execute("SELECT COUNT(*) FROM productos")
    if cursor.fetchone()[0] == 0:
        productos_iniciales = [
            ("WHISKY JOHNNIE WALKER RED", "BOTELLA", "LICOR", 50, 45.00, "SKU-RED-01", 1),
            ("WHISKY JOHNNIE WALKER BLACK", "BOTELLA", "LICOR", 40, 85.00, "SKU-BLK-02", 2),
            ("VODKA SMIRNOFF 750ML", "BOTELLA", "LICOR", 35, 32.00, "SKU-SMR-03", 3),
            ("RON CARTAVIO BLACK", "BOTELLA", "LICOR", 60, 22.00, "SKU-CRTB-04", 4),
            ("RON FLOR DE CAÑA 4 AÑOS", "BOTELLA", "LICOR", 25, 38.00, "SKU-FDC-05", 5),
            ("PISCO QUEBRANTA 4 GALLOS", "BOTELLA", "LICOR", 30, 42.00, "SKU-4G-06", 6),
            ("TEQUILA JOSE CUERVO ESPECIAL", "BOTELLA", "LICOR", 20, 55.00, "SKU-JC-07", 7),
            ("CERVEZA CORONA 355ML", "SIXPACK", "CERVEZA", 100, 28.00, "SKU-COR-08", 8),
            ("CERVEZA CUSQUEÑA TRIGO", "SIXPACK", "CERVEZA", 80, 26.00, "SKU-CUSQ-09", 9),
            ("GIN TANQUERAY LONDON DRY", "BOTELLA", "LICOR", 15, 68.00, "SKU-TNQ-10", 10),
        ]
        cursor.executemany("""
            INSERT INTO productos (nombre, presentacion, categoria, stock, precio_uni_pen, codigo_producto, orden)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, productos_iniciales)
        conn.commit()
    conn.close()

# -------------------------------------------------------------------------
# REQUISITO 1: Actualizar únicamente el código de producto (SKU)
# -------------------------------------------------------------------------
def actualizar_codigo_producto_temp(id_producto: int, nuevo_codigo: str):
    conn = conectar_temp()
    try:
        with conn:
            conn.execute("""
                UPDATE productos 
                SET codigo_producto = ? 
                WHERE id_producto = ?
            """, (nuevo_codigo.strip() if nuevo_codigo else "", id_producto))
        return True
    finally:
        conn.close()

# -------------------------------------------------------------------------
# REQUISITO 2: Lógica de reordenamiento de posiciones (Desplazamiento)
# -------------------------------------------------------------------------
def reordenar_producto_temp(id_producto: int, nueva_posicion: int):
    if nueva_posicion < 1:
        raise ValueError("La posición debe ser un número entero mayor o igual a 1.")

    conn = conectar_temp()
    try:
        with conn:  # Context manager gestiona BEGIN TRANSACTION, COMMIT y ROLLBACK
            cursor = conn.cursor()
            cursor.execute("SELECT orden, nombre FROM productos WHERE id_producto = ?", (id_producto,))
            fila = cursor.fetchone()
            if not fila:
                raise ValueError(f"No se encontró el producto con ID {id_producto}")

            pos_actual = fila["orden"]
            nombre_prod = fila["nombre"]

            if pos_actual == nueva_posicion:
                return True

            if nueva_posicion < pos_actual:
                # Movimiento hacia arriba (ej. de 8 a 2):
                # Los ítems entre [nueva_posicion y pos_actual - 1] suman +1
                cursor.execute("""
                    UPDATE productos 
                    SET orden = orden + 1 
                    WHERE orden >= ? AND orden < ? AND id_producto != ?
                """, (nueva_posicion, pos_actual, id_producto))
            else:
                # Movimiento hacia abajo (ej. de 2 a 8):
                # Los ítems entre [pos_actual + 1 y nueva_posicion] restan -1
                cursor.execute("""
                    UPDATE productos 
                    SET orden = orden - 1 
                    WHERE orden > ? AND orden <= ? AND id_producto != ?
                """, (pos_actual, nueva_posicion, id_producto))

            # Asignar la nueva posición final al producto objetivo
            cursor.execute("""
                UPDATE productos 
                SET orden = ? 
                WHERE id_producto = ?
            """, (nueva_posicion, id_producto))

        return True
    finally:
        conn.close()

# -------------------------------------------------------------------------
# REQUISITO 3: Buscador Dinámico con ORDER BY orden ASC
# -------------------------------------------------------------------------
def buscar_productos_temp(texto: str = ""):
    conn = conectar_temp()
    try:
        cursor = conn.cursor()
        if texto:
            termino = f"%{texto.strip()}%"
            cursor.execute("""
                SELECT id_producto, codigo_producto, orden, nombre, presentacion, stock, precio_uni_pen
                FROM productos
                WHERE nombre LIKE ? OR codigo_producto LIKE ? OR codigo_barras LIKE ?
                ORDER BY orden ASC
            """, (termino, termino, termino))
        else:
            cursor.execute("""
                SELECT id_producto, codigo_producto, orden, nombre, presentacion, stock, precio_uni_pen
                FROM productos
                ORDER BY orden ASC
            """)
        return cursor.fetchall()
    finally:
        conn.close()

def imprimir_tabla(titulo="CATÁLOGO ACTUAL"):
    print(f"\n{'='*75}")
    print(f" {titulo}")
    print(f"{'='*75}")
    print(f"{'POS/ORDEN':<10} | {'ID':<4} | {'SKU/CÓDIGO':<15} | {'NOMBRE':<32} | {'PRECIO':<8}")
    print(f"{'-'*75}")
    items = buscar_productos_temp()
    for it in items:
        sku = it['codigo_producto'] or '(Sin SKU)'
        print(f"{it['orden']:<10} | {it['id_producto']:<4} | {sku:<15} | {it['nombre'][:30]:<32} | S/ {it['precio_uni_pen']:<6.2f}")
    print(f"{'='*75}\n")

if __name__ == "__main__":
    print("[1] Inicializando base de datos temporal SQLite...")
    inicializar_bd_temporal()
    imprimir_tabla("ESTADO INICIAL DEL CATÁLOGO")

    # Demostración Requisito 1: Actualizar SKU
    print("[2] Requisito 1: Editando SKU del producto ID 1...")
    actualizar_codigo_producto_temp(1, "SKU-RED-EDICION-2026")
    imprimir_tabla("LUEGO DE ACTUALIZAR SKU DEL PRODUCTO ID 1")

    # Demostración Requisito 2: Mover producto (ej. ID 8 que está en pos 8 hacia la pos 2)
    print("[3] Requisito 2: Moviendo producto ID 8 ('CERVEZA CORONA') de posición 8 a posición 2...")
    reordenar_producto_temp(id_producto=8, nueva_posicion=2)
    imprimir_tabla("LUEGO DE REORDENAR (CORONA PASA A LA POSICIÓN 2)")

    # Demostración Requisito 3: Búsqueda dinámica filtrando por texto y ordenado por 'orden ASC'
    print("[4] Requisito 3: Buscando productos con término 'WHISKY' (respetando orden ASC)...")
    resultados = buscar_productos_temp("WHISKY")
    for r in resultados:
        print(f" -> Pos: {r['orden']} | SKU: {r['codigo_producto']} | {r['nombre']}")
    print("\n[EXITO] Todas las pruebas en archivo temporal completadas exitosamente.")
