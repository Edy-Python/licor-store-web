import mysql.connector
from config import DB_CONFIG

print("Conectando a la base de datos en Railway...")
try:
    conexion = mysql.connector.connect(**DB_CONFIG)
    cursor = conexion.cursor()

    print("Creando tabla 'productos'...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id_producto INT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(255) NOT NULL,
        presentacion VARCHAR(100),
        stock INT DEFAULT 0,
        precio DECIMAL(10,2) DEFAULT 0.00,
        precio_uni_pen DECIMAL(10,2) DEFAULT 0.00,
        precio_uni_usd DECIMAL(10,2) DEFAULT 0.00,
        precio_six_pen DECIMAL(10,2) DEFAULT 0.00,
        precio_six_usd DECIMAL(10,2) DEFAULT 0.00,
        precio_caja_pen DECIMAL(10,2) DEFAULT 0.00,
        precio_caja_usd DECIMAL(10,2) DEFAULT 0.00,
        precio_plancha_pen DECIMAL(10,2) DEFAULT 0.00,
        precio_plancha_usd DECIMAL(10,2) DEFAULT 0.00
    )
    """)

    print("Creando tabla 'ventas'...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ventas (
        id_venta INT AUTO_INCREMENT PRIMARY KEY,
        codigo_ticket VARCHAR(20) UNIQUE NOT NULL,
        fecha_emision DATE,
        hora_emision TIME,
        vendedor VARCHAR(100),
        cliente_nombre VARCHAR(255),
        cliente_dni VARCHAR(20),
        cliente_direccion VARCHAR(255),
        total_pen DECIMAL(10,2) DEFAULT 0.00,
        total_usd DECIMAL(10,2) DEFAULT 0.00,
        observaciones TEXT
    )
    """)

    print("Creando tabla 'detalles_venta'...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS detalles_venta (
        id_detalle INT AUTO_INCREMENT PRIMARY KEY,
        id_venta INT,
        id_producto INT,
        tipo_empaque VARCHAR(50),
        cantidad INT,
        precio_unitario DECIMAL(10,2),
        subtotal_pen DECIMAL(10,2),
        subtotal_usd DECIMAL(10,2),
        FOREIGN KEY (id_venta) REFERENCES ventas(id_venta) ON DELETE CASCADE,
        FOREIGN KEY (id_producto) REFERENCES productos(id_producto) ON DELETE RESTRICT
    )
    """)

    conexion.commit()
    print("✅ ¡Todas las tablas se crearon correctamente en Railway!")

except Exception as e:
    print(f"❌ Ocurrió un error: {e}")
finally:
    if 'conexion' in locals() and conexion.is_connected():
        cursor.close()
        conexion.close()