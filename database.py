import os
import mysql.connector
import mysql.connector.pooling
from contextlib import contextmanager
from config import DB_CONFIG

try:
    pool_size = int(os.getenv("DB_POOL_SIZE", 10))
    db_pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="licor_store_pool",
        pool_size=pool_size,
        pool_reset_session=True,
        **DB_CONFIG
    )
    print("[INFO] Pool de conexiones MySQL inicializado correctamente.")
except Exception as ex_pool:
    print(f"[AVISO] No se pudo crear el pool ({ex_pool}). Se utilizarán conexiones directas.")
    db_pool = None

def conectar_db():
    if db_pool:
        try:
            return db_pool.get_connection()
        except Exception:
            return mysql.connector.connect(**DB_CONFIG)
    return mysql.connector.connect(**DB_CONFIG)

@contextmanager
def obtener_cursor(commit=False):
    conn = conectar_db()
    cursor = conn.cursor(buffered=True)
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception:
        if commit:
            try:
                conn.rollback()
            except Exception as ex_rollback:
                print(f"Error en rollback: {ex_rollback}")
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

def inicializar_tablas():
    """
    Inicializa todas las tablas del sistema POS garantizando integridad referencial,
    índices de rendimiento y sembrado inicial de datos para nuevos despliegues.
    """
    try:
        with obtener_cursor(commit=True) as cursor:
            # 1. TABLA: CONFIGURACION (Datos del Negocio)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS configuracion (
                    id INT PRIMARY KEY DEFAULT 1,
                    nombre_negocio VARCHAR(200) NOT NULL DEFAULT '',
                    ruc VARCHAR(20) DEFAULT '',
                    direccion VARCHAR(255) DEFAULT '',
                    referencia VARCHAR(255) DEFAULT '',
                    telefono VARCHAR(50) DEFAULT '',
                    mensaje_ticket TEXT,
                    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            try:
                cursor.execute("ALTER TABLE configuracion ADD COLUMN referencia VARCHAR(255) DEFAULT ''")
            except Exception:
                pass
            # Sembrado inicial de configuración si no existe fila 1
            cursor.execute("""
                INSERT INTO configuracion (id, nombre_negocio, ruc, direccion, referencia, telefono, mensaje_ticket)
                VALUES (1, '', '20000000001', 'Av. Principal 123', '', '999999999', '¡Gracias por su preferencia!')
                ON DUPLICATE KEY UPDATE id=id;
            """)

            # 2. TABLA: USUARIOS (Control de Acceso y Roles)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nombre VARCHAR(100) NOT NULL,
                    email VARCHAR(150) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    rol VARCHAR(50) NOT NULL DEFAULT 'vendedor',
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # Sembrado de usuario administrador inicial si la tabla está vacía
            cursor.execute("SELECT COUNT(*) FROM usuarios")
            if cursor.fetchone()[0] == 0:
                import hashlib
                admin_pass_hash = hashlib.sha256("admin".encode()).hexdigest()
                cursor.execute("""
                    INSERT INTO usuarios (nombre, email, password_hash, rol)
                    VALUES ('Administrador', 'admin@admin.com', %s, 'admin')
                """, (admin_pass_hash,))
                print("[INFO] Usuario admin por defecto creado (admin@admin.com / admin)")

            # 3. TABLA: PRODUCTOS (Catálogo, Precios Multi-Escala y Stock)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS productos (
                    id_producto INT AUTO_INCREMENT PRIMARY KEY,
                    nombre VARCHAR(255) NOT NULL,
                    presentacion VARCHAR(100) DEFAULT 'UNIDAD',
                    categoria VARCHAR(100) DEFAULT 'LICOR',
                    grupo_surtido VARCHAR(100) DEFAULT '',
                    stock INT NOT NULL DEFAULT 0,
                    codigo_barras VARCHAR(100) DEFAULT '',
                    costo_uni_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    costo_uni_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    costo_pack4_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    costo_pack4_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    costo_six_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    costo_six_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    costo_caja_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    costo_caja_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    costo_pack15_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    costo_pack15_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    costo_plancha_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    costo_plancha_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_uni_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_uni_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_pack4_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_pack4_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_six_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_six_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_caja_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_caja_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_pack15_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_pack15_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_plancha_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_plancha_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_prod_nombre (nombre),
                    INDEX idx_prod_codigo (codigo_barras),
                    INDEX idx_prod_categoria (categoria)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            try:
                cursor.execute("ALTER TABLE productos ADD COLUMN codigo_barras VARCHAR(100) DEFAULT ''")
            except Exception:
                pass

            # 4. TABLA: VENTAS (Cabecera de Transacciones y Finanzas)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ventas (
                    id_venta INT AUTO_INCREMENT PRIMARY KEY,
                    codigo_ticket VARCHAR(50) NOT NULL,
                    fecha_emision DATE NOT NULL,
                    hora_emision TIME NOT NULL,
                    vendedor VARCHAR(100) DEFAULT 'Admin',
                    cliente_nombre VARCHAR(150) DEFAULT 'VARIOS',
                    cliente_dni VARCHAR(20) DEFAULT '',
                    cliente_direccion VARCHAR(255) DEFAULT 'Tacna',
                    total_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    total_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    observaciones TEXT,
                    condicion_pago VARCHAR(50) DEFAULT 'Al Contado',
                    metodo_pago VARCHAR(50) DEFAULT 'Efectivo',
                    monto_efectivo DECIMAL(10,2) DEFAULT 0.00,
                    monto_yape DECIMAL(10,2) DEFAULT 0.00,
                    monto_plin DECIMAL(10,2) DEFAULT 0.00,
                    monto_tarjeta DECIMAL(10,2) DEFAULT 0.00,
                    monto_transferencia DECIMAL(10,2) DEFAULT 0.00,
                    monto_dolares DECIMAL(10,2) DEFAULT 0.00,
                    vuelto DECIMAL(10,2) DEFAULT 0.00,
                    utilidad_pen DECIMAL(10,2) DEFAULT 0.00,
                    utilidad_usd DECIMAL(10,2) DEFAULT 0.00,
                    estado VARCHAR(50) DEFAULT 'Completada',
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_ventas_fecha (fecha_emision),
                    INDEX idx_ventas_ticket (codigo_ticket),
                    INDEX idx_ventas_estado (estado)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            try:
                cursor.execute("ALTER TABLE ventas ADD COLUMN monto_transferencia DECIMAL(10,2) DEFAULT 0.00")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE ventas ADD COLUMN monto_dolares DECIMAL(10,2) DEFAULT 0.00")
            except Exception:
                pass

            # 5. TABLA: DETALLES_VENTA (Ítems Vendidos con Llaves Foráneas)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS detalles_venta (
                    id_detalle INT AUTO_INCREMENT PRIMARY KEY,
                    id_venta INT NOT NULL,
                    id_producto INT NOT NULL,
                    tipo_empaque VARCHAR(50) DEFAULT 'Unidad',
                    cantidad INT NOT NULL DEFAULT 1,
                    precio_unitario DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    subtotal_pen DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    subtotal_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    costo_unitario_pen DECIMAL(10,2) DEFAULT 0.00,
                    costo_unitario_usd DECIMAL(10,2) DEFAULT 0.00,
                    FOREIGN KEY (id_venta) REFERENCES ventas(id_venta) ON DELETE CASCADE,
                    FOREIGN KEY (id_producto) REFERENCES productos(id_producto) ON DELETE RESTRICT,
                    INDEX idx_det_venta (id_venta),
                    INDEX idx_det_producto (id_producto)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 6. TABLA: GASTOS (Egresos de Caja y Operativos)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gastos (
                    id_gasto INT AUTO_INCREMENT PRIMARY KEY,
                    fecha DATE NOT NULL,
                    hora TIME NOT NULL,
                    concepto VARCHAR(255) NOT NULL,
                    monto DECIMAL(10,2) NOT NULL,
                    categoria VARCHAR(100) DEFAULT 'General',
                    usuario VARCHAR(100) DEFAULT 'Admin',
                    comprobante VARCHAR(100) DEFAULT '',
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_gastos_fecha (fecha)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 7. TABLA: PAGOS_CREDITO (Abonos a Ventas al Crédito)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pagos_credito (
                    id_pago INT AUTO_INCREMENT PRIMARY KEY,
                    id_venta INT NOT NULL,
                    fecha DATE NOT NULL,
                    hora TIME NOT NULL,
                    monto DECIMAL(10,2) NOT NULL,
                    metodo_pago VARCHAR(50) DEFAULT 'Efectivo',
                    usuario VARCHAR(100) DEFAULT 'Admin',
                    observaciones VARCHAR(255) DEFAULT '',
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (id_venta) REFERENCES ventas(id_venta) ON DELETE CASCADE,
                    INDEX idx_pagos_venta (id_venta),
                    INDEX idx_pagos_fecha (fecha)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 8. TABLA: CIERRES_CAJA (Arqueos y Cuadres Diarios)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cierres_caja (
                    id_cierre INT AUTO_INCREMENT PRIMARY KEY,
                    fecha DATE NOT NULL,
                    hora TIME NOT NULL,
                    usuario VARCHAR(100) NOT NULL,
                    monto_apertura DECIMAL(10,2) DEFAULT 0.00,
                    total_ventas_efectivo DECIMAL(10,2) DEFAULT 0.00,
                    total_ventas_yape DECIMAL(10,2) DEFAULT 0.00,
                    total_ventas_transferencia DECIMAL(10,2) DEFAULT 0.00,
                    total_ventas_tarjeta DECIMAL(10,2) DEFAULT 0.00,
                    total_ventas_dolares DECIMAL(10,2) DEFAULT 0.00,
                    total_abonos_cobrados DECIMAL(10,2) DEFAULT 0.00,
                    total_gastos DECIMAL(10,2) DEFAULT 0.00,
                    efectivo_esperado DECIMAL(10,2) DEFAULT 0.00,
                    efectivo_real_conteo DECIMAL(10,2) DEFAULT 0.00,
                    diferencia DECIMAL(10,2) DEFAULT 0.00,
                    estado_cuadre VARCHAR(50) DEFAULT 'Exacto',
                    observaciones TEXT,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_cierres_fecha (fecha)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 9. TABLA: HISTORIAL_INGRESOS (Kardex Físico de Mercadería)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historial_ingresos (
                    id_ingreso INT AUTO_INCREMENT PRIMARY KEY,
                    id_producto INT NOT NULL,
                    cantidad INT NOT NULL,
                    destino VARCHAR(150) DEFAULT 'Inventario',
                    comentarios TEXT,
                    fecha_ingreso DATETIME NOT NULL,
                    FOREIGN KEY (id_producto) REFERENCES productos(id_producto) ON DELETE RESTRICT,
                    INDEX idx_hist_producto (id_producto),
                    INDEX idx_hist_fecha (fecha_ingreso)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 10. TABLA: INGRESOS_CABECERA (Lotes y Documentos de Compra/Recepción)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ingresos_cabecera (
                    id_ingreso INT AUTO_INCREMENT PRIMARY KEY,
                    fecha DATE NOT NULL,
                    hora TIME NOT NULL,
                    usuario VARCHAR(100) DEFAULT 'Admin',
                    comentarios TEXT,
                    total_articulos INT NOT NULL DEFAULT 0,
                    costo_total DECIMAL(12,2) NOT NULL DEFAULT 0.00,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_ing_fecha (fecha)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            try:
                cursor.execute("ALTER TABLE ingresos_cabecera ADD COLUMN total_articulos INT NOT NULL DEFAULT 0")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE ingresos_cabecera ADD COLUMN costo_total DECIMAL(12,2) NOT NULL DEFAULT 0.00")
            except Exception:
                pass

            # 11. TABLA: INGRESOS_DETALLE (Detalle Transaccional de Recepción)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ingresos_detalle (
                    id_detalle INT AUTO_INCREMENT PRIMARY KEY,
                    id_ingreso INT NOT NULL,
                    id_producto INT NOT NULL,
                    cantidad INT NOT NULL,
                    costo_unitario DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    precio_actualizado DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    subtotal_costo DECIMAL(12,2) NOT NULL DEFAULT 0.00,
                    detalles_precios TEXT,
                    FOREIGN KEY (id_ingreso) REFERENCES ingresos_cabecera(id_ingreso) ON DELETE CASCADE,
                    FOREIGN KEY (id_producto) REFERENCES productos(id_producto) ON DELETE RESTRICT,
                    INDEX idx_ing_det_ingreso (id_ingreso),
                    INDEX idx_ing_det_producto (id_producto)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            try:
                cursor.execute("ALTER TABLE ingresos_detalle ADD COLUMN subtotal_costo DECIMAL(12,2) NOT NULL DEFAULT 0.00")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE ingresos_detalle ADD COLUMN detalles_precios TEXT")
            except Exception:
                pass

            print("[INFO] Esquema de Base de Datos verificado e inicializado correctamente.")
    except Exception as ex:
        print(f"[ERROR CRÍTICO] Fallo al inicializar tablas en MySQL: {ex}")