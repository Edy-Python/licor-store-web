import flet as ft
import datetime
import hashlib
import mysql.connector
import pandas as pd
import os
import uuid
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from num2words import num2words
from fpdf import FPDF

from config import DB_CONFIG, USUARIOS

# Nota: se quitó "from escpos.printer import Usb" porque no se usaba en
# ningún lado (el botón "Imprimir" del ticket es solo un placeholder).
# Si más adelante implementas impresión térmica directa, vuelve a importarlo ahí.


def conectar_db():
    """Abre una nueva conexión a MySQL usando la configuración de config.py."""
    return mysql.connector.connect(**DB_CONFIG)


@contextmanager
def obtener_cursor(commit=False):
    """
    Entrega un cursor de MySQL y garantiza que la conexión y el cursor se
    cierren siempre -incluso si ocurre un error dentro del bloque `with`-,
    evitando conexiones que quedan abiertas cuando algo falla.

    Uso:
        with obtener_cursor() as cursor:
            cursor.execute("SELECT ...")
            datos = cursor.fetchall()

        with obtener_cursor(commit=True) as cursor:
            cursor.execute("INSERT ...")
    """
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception:
        if commit:
            conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def main(page: ft.Page):
    page.title = "Licor Store POS"
    page.theme_mode = ft.ThemeMode.LIGHT 
    page.padding = 0 
    page.bgcolor = "#F4F6F8" 

    def mostrar_mensaje(texto, bgcolor=ft.Colors.BLUE):
        page.snack_bar = ft.SnackBar(
            ft.Text(texto, color=ft.Colors.WHITE),
            bgcolor=bgcolor,
            duration=4000,
        )
        page.snack_bar.open = True
        page.update()

    # --- FUNCIONES LÓGICAS ---
    # (Los controles de la interfaz -input_dni, tabla_carrito, lbl_total_pen,
    # etc.- se definen más abajo, cerca de donde se arma el layout final.
    # Antes había una segunda copia de estos mismos controles aquí arriba
    # que nunca llegaba a mostrarse en pantalla; se eliminó para evitar
    # confusión y duplicación.)
    def actualizar_totales():
        t_pen = sum((Decimal(str(row.cells[6].content.value or "0")) for row in tabla_carrito.rows), Decimal("0.00"))
        t_usd = sum((Decimal(str(row.cells[7].content.value or "0")) for row in tabla_carrito.rows), Decimal("0.00"))
        lbl_total_pen.value = f"S/ {t_pen:.2f}"
        lbl_total_usd.value = f"$ {t_usd:.2f}"
        page.update()

    def eliminar_fila(row):
        tabla_carrito.rows.remove(row)
        actualizar_totales()

    def seleccionar_autocompletado(nombre):
        input_buscar.value = nombre
        lista_resultados.visible = False
        page.update()

    def buscar_dinamico(e):
        busqueda = input_buscar.value.strip()
        lista_resultados.controls.clear()
        
        if len(busqueda) < 2:
            lista_resultados.visible = False
            page.update()
            return
            
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT nombre FROM productos WHERE nombre LIKE %s LIMIT 50", (f"%{busqueda}%",))
                resultados = cursor.fetchall()

            if resultados:
                lista_resultados.visible = True
                for fila in resultados:
                    lista_resultados.controls.append(ft.ListTile(title=ft.Text(fila[0]), on_click=lambda e, n=fila[0]: seleccionar_autocompletado(n)))
            else:
                lista_resultados.visible = False

            page.update()
        except Exception as ex:
            # No mostramos snackbar en cada tecleo (sería molesto), pero al
            # menos queda registrado en consola para poder depurar.
            print(f"Error en búsqueda dinámica: {ex}")

    # (input_buscar se define más abajo, junto a tabla_carrito y los demás
    # controles del carrito; antes había una segunda copia huérfana aquí.)

    def agregar_producto(e):
        busqueda = (input_buscar.value or "").strip()
        if not busqueda:
            return

        cantidad_texto = (input_cantidad.value or "").strip()
        if not cantidad_texto.isdigit() or int(cantidad_texto) <= 0:
            mostrar_mensaje("La cantidad debe ser un número entero mayor que 0", ft.Colors.RED)
            return
        cant_ingresada = int(cantidad_texto)

        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT id_producto, nombre, presentacion,
                           precio_uni_pen, precio_uni_usd, precio_six_pen, precio_six_usd,
                           precio_caja_pen, precio_caja_usd, precio_plancha_pen, precio_plancha_usd
                    FROM productos
                    WHERE id_producto = %s OR nombre = %s
                    LIMIT 1
                """, (busqueda if busqueda.isdigit() else 0, busqueda))
                producto = cursor.fetchone()

            if not producto:
                mostrar_mensaje("Producto no encontrado.", ft.Colors.RED)
                return

            (id_prod, nombre, pres, p_uni_pen, p_uni_usd, p_six_pen, p_six_usd,
             p_caja_pen, p_caja_usd, p_plan_pen, p_plan_usd) = producto
            moneda = dropdown_moneda.value
            empaque = dropdown_empaque.value

            precios = {
                ("Unidad", "PEN"): p_uni_pen, ("Unidad", "USD"): p_uni_usd,
                ("Six-pack", "PEN"): p_six_pen, ("Six-pack", "USD"): p_six_usd,
                ("Caja", "PEN"): p_caja_pen, ("Caja", "USD"): p_caja_usd,
                ("Plancha", "PEN"): p_plan_pen, ("Plancha", "USD"): p_plan_usd,
            }
            precio_final = Decimal(str(precios.get((empaque, moneda), 0) or 0))

            precio_especial = (input_precio_esp.value or "").strip()
            if precio_especial:
                try:
                    precio_final = Decimal(precio_especial)
                except InvalidOperation:
                    mostrar_mensaje("El precio especial no es válido", ft.Colors.RED)
                    return

            if precio_final <= 0:
                mostrar_mensaje(f"No existe un precio válido para {empaque} en {moneda}.", ft.Colors.RED)
                return

            subtotal = precio_final * cant_ingresada
            sub_pen = subtotal if moneda == "PEN" else Decimal("0.00")
            sub_usd = subtotal if moneda == "USD" else Decimal("0.00")

            nueva_fila = ft.DataRow(cells=[
                ft.DataCell(ft.Container(content=ft.Text(str(id_prod).zfill(3)), width=30)),
                ft.DataCell(ft.Container(content=ft.Text(str(nombre)), width=120)),
                ft.DataCell(ft.Text(str(pres))),
                ft.DataCell(ft.Text(empaque)),
                ft.DataCell(ft.Text(str(cant_ingresada))),
                ft.DataCell(ft.Text(f"{precio_final:.2f}")),
                ft.DataCell(ft.Text(f"{sub_pen:.2f}")),
                ft.DataCell(ft.Text(f"{sub_usd:.2f}")),
            ])
            nueva_fila.cells.append(ft.DataCell(ft.IconButton(
                icon=ft.Icons.DELETE,
                icon_color=ft.Colors.RED,
                on_click=lambda e, r=nueva_fila: eliminar_fila(r),
            )))
            tabla_carrito.rows.append(nueva_fila)

            input_buscar.value = ""
            input_cantidad.value = "1"
            input_precio_esp.value = ""
            lista_resultados.visible = False
            actualizar_totales()
        except Exception as ex:
            print(f"Error al agregar al carrito: {ex}")
            mostrar_mensaje("Error al agregar el producto.", ft.Colors.RED)

    def ver_nota_venta(id_venta_reciente, codigo_ticket):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT fecha_emision, hora_emision, vendedor, cliente_nombre, cliente_dni, cliente_direccion, total_pen, total_usd FROM ventas WHERE id_venta = %s", (id_venta_reciente,))
                cabecera = cursor.fetchone()

                cursor.execute("""
                    SELECT d.cantidad, d.tipo_empaque, p.nombre, d.precio_unitario, d.subtotal_pen, d.subtotal_usd 
                    FROM detalles_venta d 
                    JOIN productos p ON d.id_producto = p.id_producto 
                    WHERE d.id_venta = %s
                """, (id_venta_reciente,))
                detalles = cursor.fetchall()

            if not cabecera:
                raise ValueError(f"No se encontró la venta con id {id_venta_reciente}.")

            f_emision, h_emision, vendedor, c_nombre, c_dni, c_dir, t_pen, t_usd = cabecera
            
            # --- LÓGICA DE VALORES POR DEFECTO ---
            nombre_final = c_nombre.strip() if c_nombre and c_nombre.strip() != "" else "VARIOS"
            dni_final = c_dni.strip() if c_dni and c_dni.strip() != "" else "00000000"
            dir_final = c_dir.strip() if c_dir and c_dir.strip() != "" else "Tacna"
            
            # Llenado de celdas con anchos fijos para expandir la tabla
            filas_tabla = []
            for det in detalles:
                filas_tabla.append(
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Container(content=ft.Text(str(det[0]), size=11), width=25)),
                        ft.DataCell(ft.Container(content=ft.Text(str(det[1])[:3].upper(), size=11), width=25)),
                        ft.DataCell(ft.Container(content=ft.Text(str(det[2]), size=11), width=110)),
                        ft.DataCell(ft.Container(content=ft.Text(f"{det[3]:.2f}", size=11), width=35)),
                        ft.DataCell(ft.Container(content=ft.Text(f"{det[4]:.2f}", size=11), width=40)),
                        ft.DataCell(ft.Container(content=ft.Text(f"{det[5]:.2f}", size=11), width=40))
                    ])
                )
            
            borde_linea = ft.BorderSide(1, ft.Colors.BLACK87)

            # Cabeceras sincronizadas con las mismas medidas de las celdas
            tabla_ticket = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Container(content=ft.Text("Cant", size=11, weight=ft.FontWeight.BOLD), width=25)),
                    ft.DataColumn(ft.Container(content=ft.Text("Und", size=11, weight=ft.FontWeight.BOLD), width=25)),
                    ft.DataColumn(ft.Container(content=ft.Text("Desc.", size=11, weight=ft.FontWeight.BOLD), width=110)),
                    ft.DataColumn(ft.Container(content=ft.Text("P.U.", size=11, weight=ft.FontWeight.BOLD), width=35)),
                    ft.DataColumn(ft.Container(content=ft.Text("Sub(S/)", size=11, weight=ft.FontWeight.BOLD), width=40)),
                    ft.DataColumn(ft.Container(content=ft.Text("Sub($)", size=11, weight=ft.FontWeight.BOLD), width=40)),
                ],
                rows=filas_tabla,
                border=ft.border.Border(top=borde_linea, bottom=borde_linea, left=borde_linea, right=borde_linea),
                vertical_lines=borde_linea,
                horizontal_lines=borde_linea,
                column_spacing=10, 
                data_row_max_height=45, 
                heading_row_height=40
            )
            elementos_finales = [ft.Container(content=tabla_ticket, padding=ft.Padding(left=0, top=10, right=0, bottom=10))]
            
            if t_pen > 0:
                entero_pen = int(t_pen)
                centimos_pen = int(round((t_pen - entero_pen) * 100))
                texto_pen = num2words(entero_pen, lang='es').capitalize()
                leyenda_pen = f"Son: {texto_pen} con {centimos_pen:02d}/100 Soles"
                elementos_finales.append(ft.Row([ft.Text("Total a pagar (S/):", weight=ft.FontWeight.BOLD), ft.Text(f"{t_pen:.2f}", weight=ft.FontWeight.BOLD)], alignment=ft.MainAxisAlignment.END))
                elementos_finales.append(ft.Text(leyenda_pen, size=11, italic=True, text_align=ft.TextAlign.RIGHT, width=float('inf')))

            if t_usd > 0:
                entero_usd = int(t_usd)
                centimos_usd = int(round((t_usd - entero_usd) * 100))
                texto_usd = num2words(entero_usd, lang='es').capitalize()
                leyenda_usd = f"Son: {texto_usd} con {centimos_usd:02d}/100 Dólares Americanos"
                elementos_finales.append(ft.Row([ft.Text("Total a pagar ($):", weight=ft.FontWeight.BOLD), ft.Text(f"{t_usd:.2f}", weight=ft.FontWeight.BOLD)], alignment=ft.MainAxisAlignment.END))
                elementos_finales.append(ft.Text(leyenda_usd, size=11, italic=True, text_align=ft.TextAlign.RIGHT, width=float('inf')))

            def cerrar_ticket(e):
                dialogo_ticket.open = False
                page.update()

            dialogo_ticket = ft.AlertDialog(
                content=ft.Container(
                    width=380,
                    content=ft.Column([
                        ft.Text("NOTA DE VENTA", size=18, weight=ft.FontWeight.BOLD),
                        ft.Text(codigo_ticket, size=15, weight=ft.FontWeight.BOLD),
                        ft.Divider(color=ft.Colors.GREY_300),
                        ft.Row([ft.Text(f"F. Emisión: {f_emision}", size=12)], alignment=ft.MainAxisAlignment.START),
                        ft.Row([ft.Text(f"H. Emisión: {h_emision}", size=12)], alignment=ft.MainAxisAlignment.START),
                        ft.Row([ft.Text(f"Vendedor: {str(vendedor).upper()}", size=12)], alignment=ft.MainAxisAlignment.START),
                        ft.Divider(color=ft.Colors.GREY_300),
                        ft.Row([ft.Text(f"Cliente: {nombre_final}", size=12)], alignment=ft.MainAxisAlignment.START),
                        ft.Row([ft.Text(f"DNI: {dni_final}", size=12)], alignment=ft.MainAxisAlignment.START),
                        ft.Row([ft.Text(f"Dirección: {dir_final}", size=12)], alignment=ft.MainAxisAlignment.START),
                        ft.Divider(color=ft.Colors.GREY_300),
                        *elementos_finales
                    ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO)
                ),
                actions=[
                    ft.ElevatedButton("Imprimir", icon=ft.Icons.PRINT, bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE, on_click=lambda e: mostrar_mensaje("La impresión directa aún no está configurada. Usa el PDF para imprimir el ticket.", ft.Colors.BLUE)),
                    ft.ElevatedButton("Cerrar Ticket", bgcolor=ft.Colors.BLACK, color=ft.Colors.WHITE, on_click=cerrar_ticket)
                ]
            )
                
            page.overlay.append(dialogo_ticket)
            dialogo_ticket.open = True
            page.update()

        except Exception as e:
            print(f"Error generando ticket: {e}")
            page.snack_bar = ft.SnackBar(ft.Text("No se pudo generar la nota de venta.", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED)
            page.snack_bar.open = True
            page.update()

    def procesar_venta(e):
        if not tabla_carrito.rows:
            mostrar_mensaje("El carrito está vacío.", ft.Colors.RED)
            return

        conn = conectar_db()
        cursor = None
        try:
            cursor = conn.cursor()
            multiplicadores = {"Unidad": 1, "Six-pack": 6, "Caja": 12, "Plancha": 24}
            items = []
            stock_requerido = {}

            for row in tabla_carrito.rows:
                id_prod = int(row.cells[0].content.content.value)
                empaque = row.cells[3].content.value
                cant = int(row.cells[4].content.value)
                p_unit = Decimal(str(row.cells[5].content.value))
                sub_pen = Decimal(str(row.cells[6].content.value))
                sub_usd = Decimal(str(row.cells[7].content.value))

                if cant <= 0:
                    raise ValueError("Todas las cantidades deben ser mayores que 0.")
                multiplicador = multiplicadores.get(empaque)
                if multiplicador is None:
                    raise ValueError(f"Tipo de empaque no válido: {empaque}")

                consumo = multiplicador * cant
                stock_requerido[id_prod] = stock_requerido.get(id_prod, 0) + consumo
                items.append((id_prod, empaque, cant, p_unit, sub_pen, sub_usd))

            for id_prod, consumo_total in stock_requerido.items():
                cursor.execute(
                    "SELECT nombre, stock FROM productos WHERE id_producto = %s FOR UPDATE",
                    (id_prod,),
                )
                resultado = cursor.fetchone()
                if not resultado:
                    raise ValueError(f"El producto con id {id_prod} ya no existe.")
                nombre_prod, stock_actual = resultado
                if stock_actual < consumo_total:
                    raise ValueError(
                        f"Stock insuficiente de '{nombre_prod}'. Quedan {stock_actual} y solicitas {consumo_total}."
                    )

            fecha_actual = datetime.date.today()
            hora_actual = datetime.datetime.now().time()
            vendedor_actual = (
                page.rol_usuario.upper()
                if hasattr(page, 'rol_usuario') and page.rol_usuario
                else "ADMINISTRADOR"
            )
            obs = (input_observacion.value or "").strip() or "Sin observaciones"
            t_pen = sum((item[4] for item in items), Decimal("0.00"))
            t_usd = sum((item[5] for item in items), Decimal("0.00"))

            ticket_temporal = f"TMP-{uuid.uuid4().hex}"
            cursor.execute("""
                INSERT INTO ventas (
                    codigo_ticket, fecha_emision, hora_emision, vendedor,
                    cliente_nombre, cliente_dni, cliente_direccion,
                    total_pen, total_usd, observaciones
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                ticket_temporal, fecha_actual, hora_actual, vendedor_actual,
                (input_cliente.value or "").strip(),
                (input_dni.value or "").strip(),
                (input_direccion.value or "Tacna").strip(),
                t_pen, t_usd, obs,
            ))
            id_venta = cursor.lastrowid
            codigo_ticket = f"NV-{id_venta:08d}"
            cursor.execute("UPDATE ventas SET codigo_ticket = %s WHERE id_venta = %s", (codigo_ticket, id_venta))

            for id_prod, empaque, cant, p_unit, sub_pen, sub_usd in items:
                cursor.execute("""
                    INSERT INTO detalles_venta (
                        id_venta, id_producto, tipo_empaque, cantidad,
                        precio_unitario, subtotal_pen, subtotal_usd
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (id_venta, id_prod, empaque, cant, p_unit, sub_pen, sub_usd))

            for id_prod, consumo_total in stock_requerido.items():
                cursor.execute(
                    "UPDATE productos SET stock = stock - %s WHERE id_producto = %s",
                    (consumo_total, id_prod),
                )

            conn.commit()
            tabla_carrito.rows.clear()
            input_dni.value = ""
            input_cliente.value = ""
            input_observacion.value = ""
            actualizar_totales()

            def cerrar_alerta_venta(e):
                alerta_venta.open = False
                page.update()

            alerta_venta = ft.AlertDialog(
                title=ft.Text("¡Venta Realizada!", color=ft.Colors.GREEN, weight=ft.FontWeight.BOLD),
                content=ft.Text(f"Ticket generado: {codigo_ticket}\nEl stock se ha descontado correctamente.", size=16),
                actions=[
                    ft.TextButton(
                        "Ver Nota de Venta",
                        on_click=lambda e, id_v=id_venta, cod=codigo_ticket: ver_nota_venta(id_v, cod),
                    ),
                    ft.ElevatedButton(
                        "Aceptar", bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE, on_click=cerrar_alerta_venta
                    ),
                ],
            )
            page.overlay.append(alerta_venta)
            alerta_venta.open = True
            page.update()

        except Exception as ex:
            conn.rollback()
            print(f"Error procesando la venta: {ex}")
            if isinstance(ex, ValueError):
                mostrar_mensaje(str(ex), ft.Colors.RED)
            else:
                mostrar_mensaje("No se pudo procesar la venta. Verifica la conexión con la base de datos.", ft.Colors.RED)
        finally:
            if cursor is not None:
                cursor.close()
            conn.close()

    def cerrar_sesion(e):
        page.rol_usuario = None 
        input_usuario.value = ""
        input_password.value = ""
        
        # Ocultamos el dashboard completo en lugar de las vistas separadas
        vista_dashboard.visible = False 
        vista_login.visible = True
        
        page.update()

    def tiene_permiso():
        if not hasattr(page, 'rol_usuario') or page.rol_usuario != "admin": 
            page.snack_bar = ft.SnackBar(
                ft.Text("Acceso denegado: Solo el administrador puede modificar.", color=ft.Colors.WHITE), 
                bgcolor=ft.Colors.RED
            )
            page.snack_bar.open = True
            page.update()
            return False
        return True

# --- TABLA DE INVENTARIO (ACTUALIZADA) ---
    tabla_inventario = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("#", weight=ft.FontWeight.BOLD)), # Correlativo visual solicitado
            ft.DataColumn(ft.Text("Producto")),
            ft.DataColumn(ft.Text("Pres.")),
            ft.DataColumn(ft.Text("Stock")),
            ft.DataColumn(ft.Text("Uni (S/)")),
            ft.DataColumn(ft.Text("Caja (S/)")),
            ft.DataColumn(ft.Text("Acciones")),
        ],
        rows=[]
    )

    def abrir_edicion(id_prod):
        if not tiene_permiso():
            return
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                SELECT nombre, presentacion, 
                       precio_uni_pen, precio_uni_usd, 
                       precio_six_pen, precio_six_usd, 
                       precio_caja_pen, precio_caja_usd, 
                       precio_plancha_pen, precio_plancha_usd 
                FROM productos WHERE id_producto = %s
            """, (id_prod,))
                datos = cursor.fetchone()

            if not datos: return
            (n, pres, pu_pen, pu_usd, ps_pen, ps_usd, pc_pen, pc_usd, pp_pen, pp_usd) = datos

        except Exception as e:
            print(f"Error consultando producto: {e}")
            page.snack_bar = ft.SnackBar(ft.Text("No se pudo cargar el producto para editar.", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED)
            page.snack_bar.open = True
            page.update()
            return

        # --- CAMPOS POBLADOS CON DATOS EXISTENTES ---
        input_add_stock = ft.TextField(label="Añadir Stock (+)", value="0", col={"sm": 12, "md": 4}, bgcolor=ft.Colors.BLUE_50, prefix_icon=ft.Icons.ADD_BOX)
        input_nom = ft.TextField(label="Nombre del Producto", value=str(n), col={"sm": 12, "md": 4})
        input_pres = ft.TextField(label="Presentación", value=str(pres), col={"sm": 12, "md": 4})
        
        inp_pu_pen = ft.TextField(label="Unidad (S/)", value=f"{pu_pen:.2f}", col={"sm": 6, "md": 4})
        inp_pu_usd = ft.TextField(label="Unidad ($)", value=f"{pu_usd:.2f}", col={"sm": 6, "md": 4})
        inp_ps_pen = ft.TextField(label="Six-pack (S/)", value=f"{ps_pen:.2f}", col={"sm": 6, "md": 4})
        inp_ps_usd = ft.TextField(label="Six-pack ($)", value=f"{ps_usd:.2f}", col={"sm": 6, "md": 4})
        inp_pc_pen = ft.TextField(label="Caja (S/)", value=f"{pc_pen:.2f}", col={"sm": 6, "md": 4})
        inp_pc_usd = ft.TextField(label="Caja ($)", value=f"{pc_usd:.2f}", col={"sm": 6, "md": 4})
        inp_pp_pen = ft.TextField(label="Plancha (S/)", value=f"{pp_pen:.2f}", col={"sm": 6, "md": 4})
        inp_pp_usd = ft.TextField(label="Plancha ($)", value=f"{pp_usd:.2f}", col={"sm": 6, "md": 4})

        def guardar_edicion(e):
            if not tiene_permiso():
                return
            try:
                if not input_nom.value.strip():
                    raise ValueError("El nombre del producto es obligatorio.")

                stock_texto = (input_add_stock.value or "0").strip()
                if not stock_texto.isdigit():
                    raise ValueError("El stock a añadir debe ser un entero mayor o igual a 0.")
                stock_sumar = int(stock_texto)

                def decimal_edicion(campo, nombre_campo):
                    valor = Decimal((campo.value or "0").strip())
                    if valor < 0:
                        raise ValueError(f"{nombre_campo} no puede ser negativo.")
                    return valor

                valores = [
                    decimal_edicion(inp_pu_pen, "Unidad (S/)"),
                    decimal_edicion(inp_pu_usd, "Unidad ($)"),
                    decimal_edicion(inp_ps_pen, "Six-pack (S/)"),
                    decimal_edicion(inp_ps_usd, "Six-pack ($)"),
                    decimal_edicion(inp_pc_pen, "Caja (S/)"),
                    decimal_edicion(inp_pc_usd, "Caja ($)"),
                    decimal_edicion(inp_pp_pen, "Plancha (S/)"),
                    decimal_edicion(inp_pp_usd, "Plancha ($)"),
                ]

                with obtener_cursor(commit=True) as cursor:
                    cursor.execute("""
                        UPDATE productos SET
                            nombre = %s, presentacion = %s, stock = stock + %s,
                            precio_uni_pen = %s, precio_uni_usd = %s,
                            precio_six_pen = %s, precio_six_usd = %s,
                            precio_caja_pen = %s, precio_caja_usd = %s,
                            precio_plancha_pen = %s, precio_plancha_usd = %s
                        WHERE id_producto = %s
                    """, (
                        input_nom.value.strip(), input_pres.value.strip(), stock_sumar, *valores, id_prod
                    ))

                dialogo_editar.open = False
                cargar_datos_inventario()
                mostrar_mensaje("✅ Producto actualizado correctamente", ft.Colors.GREEN)
            except (ValueError, InvalidOperation) as ex:
                mostrar_mensaje(f"❌ {ex}", ft.Colors.RED)
            except Exception as ex:
                print(f"Error al guardar edición: {ex}")
                mostrar_mensaje("❌ Error al guardar los cambios.", ft.Colors.RED)

        dialogo_editar = ft.AlertDialog(
            title=ft.Text("Modificar Producto", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=650, 
                content=ft.Column([
                    ft.ResponsiveRow([input_add_stock, input_nom, input_pres]),
                    ft.Divider(),
                    ft.Text("Precios por Unidad", weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.GREY_700),
                    ft.ResponsiveRow([inp_pu_pen, inp_pu_usd]),
                    ft.Text("Precios por Six-pack", weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.GREY_700),
                    ft.ResponsiveRow([inp_ps_pen, inp_ps_usd]),
                    ft.Text("Precios por Caja", weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.GREY_700),
                    ft.ResponsiveRow([inp_pc_pen, inp_pc_usd]),
                    ft.Text("Precios por Plancha", weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.GREY_700),
                    ft.ResponsiveRow([inp_pp_pen, inp_pp_usd]),
                ], scroll=ft.ScrollMode.AUTO, tight=True)
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: setattr(dialogo_editar, 'open', False) or page.update()),
                ft.ElevatedButton("Guardar Cambios", bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE, on_click=guardar_edicion)
            ]
        )
        page.overlay.append(dialogo_editar)
        dialogo_editar.open = True
        page.update()

    def confirmar_eliminacion(id_prod, nombre_prod):
        if not tiene_permiso(): return
        
        def borrar_bd(e):
            try:
                with obtener_cursor(commit=True) as cursor:
                    cursor.execute("DELETE FROM productos WHERE id_producto = %s", (id_prod,))

                dialogo_borrar.open = False
                cargar_datos_inventario() 
                
                page.snack_bar = ft.SnackBar(ft.Text(f"🗑️ '{nombre_prod}' eliminado", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED)
                page.snack_bar.open = True
                page.update()
            except mysql.connector.Error as err:
                # Capturamos específicamente el error 1451 de llave foránea
                if err.errno == 1451:
                    mensaje = f"❌ Protegido: '{nombre_prod}' tiene ventas registradas y no puede eliminarse."
                else:
                    mensaje = f"Error DB: {err}"
                    
                page.snack_bar = ft.SnackBar(ft.Text(mensaje, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.Colors.RED, duration=5000)
                page.snack_bar.open = True
                dialogo_borrar.open = False
                page.update()

        def cancelar_borrado(e):
            dialogo_borrar.open = False
            page.update()

        dialogo_borrar = ft.AlertDialog(
            title=ft.Text("Confirmar Eliminación", color=ft.Colors.RED, weight=ft.FontWeight.BOLD),
            content=ft.Text(f"¿Estás seguro de eliminar '{nombre_prod}' del inventario de forma permanente?"),
            actions=[
                ft.TextButton("Cancelar", on_click=cancelar_borrado),
                ft.ElevatedButton("Eliminar", bgcolor=ft.Colors.RED, color=ft.Colors.WHITE, on_click=borrar_bd)
            ]
        )
        page.overlay.append(dialogo_borrar)
        dialogo_borrar.open = True
        page.update()

    def cargar_datos_inventario():
        tabla_inventario.rows.clear()
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT id_producto, nombre, presentacion, stock, precio_uni_pen, precio_caja_pen FROM productos ORDER BY id_producto ASC")
                filas = cursor.fetchall()

            correlativo = 1

            for fila in filas:
                id_real = fila[0] 
                nombre_prod = str(fila[1])
                
                # Enlazamos los botones a las funciones reales usando lambda
                btn_editar = ft.IconButton(
                     ft.Icons.EDIT, 
                     icon_color=ft.Colors.BLUE, 
                     tooltip="Editar y Añadir Stock",
                     on_click=lambda e, i=id_real: abrir_edicion(i)
                )
                btn_borrar = ft.IconButton(
                    ft.Icons.DELETE, 
                    icon_color=ft.Colors.RED, 
                    tooltip="Eliminar",
                    on_click=lambda e, i=id_real, n=nombre_prod: confirmar_eliminacion(i, n)
                )
                acciones = ft.Row([btn_editar, btn_borrar])
                
                tabla_inventario.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(correlativo))), 
                    ft.DataCell(ft.Text(nombre_prod)),
                    ft.DataCell(ft.Text(str(fila[2]))),
                    ft.DataCell(ft.Text(str(fila[3]))),
                    ft.DataCell(ft.Text(f"{fila[4]:.2f}")),
                    ft.DataCell(ft.Text(f"{fila[5]:.2f}")),
                    ft.DataCell(acciones),
                ]))
                correlativo += 1

            page.update()
        except Exception as e:
            print(f"Error cargando inventario: {e}")
            page.snack_bar = ft.SnackBar(ft.Text("No se pudo cargar el inventario.", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED)
            page.snack_bar.open = True
            page.update()

    # 3. Esta es la función que ahora llama tu botón azul
    def exportar_excel(e):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT id_producto, nombre, presentacion, stock,
                           precio_uni_pen, precio_uni_usd,
                           precio_six_pen, precio_six_usd,
                           precio_caja_pen, precio_caja_usd,
                           precio_plancha_pen, precio_plancha_usd
                    FROM productos
                    ORDER BY id_producto ASC
                """)
                columnas = [col[0] for col in cursor.description]
                filas = cursor.fetchall()

            df = pd.DataFrame(filas, columns=columnas)
            os.makedirs("assets", exist_ok=True)
            nombre_archivo = "Inventario_LicorStore.xlsx"
            ruta_archivo = os.path.join("assets", nombre_archivo)
            df.to_excel(ruta_archivo, index=False)
            page.launch_url(f"/assets/{nombre_archivo}", web_window_name="_blank")
            mostrar_mensaje("¡Excel generado con éxito! Se abrió en una pestaña nueva.", ft.Colors.GREEN)
        except Exception as ex:
            print(f"Error al exportar: {ex}")
            mostrar_mensaje(f"❌ Error al exportar: {ex}", ft.Colors.RED)

    def cambiar_vista(e):
        # 1. Ocultamos TODAS las pantallas de la interfaz al hacer clic
        seccion_pos.visible = False
        vista_inventario.visible = False
        panel_reportes.visible = False
        
        # 2. Mostramos solo la pantalla correspondiente según el botón del menú
        nombre_boton = e.control.data
        
        if nombre_boton == "Ventas":
            seccion_pos.visible = True
        elif nombre_boton == "Inventario":
            vista_inventario.visible = True
        elif nombre_boton == "Reportes":
            panel_reportes.visible = True
            cargar_ventas_diarias() # Carga la tabla de ventas al instante
            
        page.update()

    def toggle_menu(e):
        menu_lateral.visible = not menu_lateral.visible
        page.update()

    def crear_boton_menu(texto, icono, funcion_click, color_fondo="#F39C12"):
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(icono, color=ft.Colors.BLACK, size=20),
                        bgcolor=color_fondo,
                        border_radius=6,
                        padding=6, # Margen uniforme con entero
                    ),
                    ft.Text(texto, color=ft.Colors.BLACK, weight=ft.FontWeight.BOLD, size=16),
                ],
                spacing=10,
            ),
            bgcolor=color_fondo,
            # SOLUCIÓN: Un solo número entero (10 píxeles a todos los lados)
            padding=10, 
            border_radius=8,
            ink=True,          
            data=texto,        
            on_click=funcion_click,
        )

    # --- CONSTRUCCIÓN DE LA VISTA PRINCIPAL (POS) ---
    menu_lateral = ft.Container(
        width=200, bgcolor="#1A1A1A", padding=20,
        content=ft.Column([
            ft.Text("LICOR STORE", color="#F39C12", weight=ft.FontWeight.BOLD, size=20),
            ft.Divider(color=ft.Colors.WHITE24),
            
            # Tus nuevos botones personalizados
            crear_boton_menu("Ventas", ft.Icons.MONETIZATION_ON, cambiar_vista),
            crear_boton_menu("Inventario", ft.Icons.INVENTORY, cambiar_vista),
            crear_boton_menu("Reportes", ft.Icons.BAR_CHART, cambiar_vista),
            crear_boton_menu("Configuración", ft.Icons.SETTINGS, lambda e: mostrar_mensaje("El módulo de configuración aún no está implementado.", ft.Colors.BLUE)),
            
            ft.Divider(color=ft.Colors.WHITE24),
            # Botón de Cerrar Sesión con el mismo diseño pero en rojo
            crear_boton_menu("Cerrar Sesión", ft.Icons.EXIT_TO_APP, cerrar_sesion, color_fondo="#E74C3C")
        ], spacing=15)
    )

    # --- CONTROLES DE LA APP (NUEVA INTERFAZ RESPONSIVA POS) ---
    input_dni = ft.TextField(label="DNI", hint_text="00000000", col={"sm": 12, "md": 3})
    input_cliente = ft.TextField(label="Cliente", hint_text="Varios", col={"sm": 12, "md": 5})
    input_direccion = ft.TextField(label="Dirección", value="Tacna", col={"sm": 12, "md": 4})
    
    # Nuevos selectores desplegables
    dropdown_empaque = ft.Dropdown(
        label="Empaque",
        options=[ft.dropdown.Option("Unidad"), ft.dropdown.Option("Six-pack"), ft.dropdown.Option("Caja"), ft.dropdown.Option("Plancha")],
        value="Unidad",
        col={"sm": 6, "md": 2}
    )
    
    input_cantidad = ft.TextField(label="Cant.", value="1", keyboard_type=ft.KeyboardType.NUMBER, col={"sm": 3, "md": 1})
    
    input_precio_esp = ft.TextField(label="Precio Esp.", hint_text="Opcional", keyboard_type=ft.KeyboardType.NUMBER, col={"sm": 3, "md": 2})
    
    dropdown_moneda = ft.Dropdown(
        label="Moneda", options=[ft.dropdown.Option("PEN"), ft.dropdown.Option("USD")], value="PEN", col={"sm": 6, "md": 2}
    )
    
    btn_agregar = ft.ElevatedButton("Agregar", style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor="#2FA572"), height=50, on_click=agregar_producto, col={"sm": 12, "md": 2})
    
    # Cuadro de texto para notas internas solicitado por el cliente
    input_observacion = ft.TextField(label="Comentarios de la venta (Solo uso interno)", multiline=True, col={"sm": 12, "md": 12})

    lbl_total_pen = ft.Text("S/ 0.00", size=24, weight=ft.FontWeight.BOLD, color="#A7BA00")
    lbl_total_usd = ft.Text("$ 0.00", size=24, weight=ft.FontWeight.BOLD, color="#0b9007")
    
    # Tabla compacta para el carrito (ID con 3 dígitos de espacio)
    tabla_carrito = ft.DataTable(
        column_spacing=15, 
        columns=[
            ft.DataColumn(ft.Container(ft.Text("ID"), width=30)), 
            ft.DataColumn(ft.Container(ft.Text("Descripción"), width=120)),
            ft.DataColumn(ft.Text("Pres.")),
            ft.DataColumn(ft.Text("Tipo")),
            ft.DataColumn(ft.Text("Cant.")),
            ft.DataColumn(ft.Text("P. Unit")),
            ft.DataColumn(ft.Text("Sub (S/)")),
            ft.DataColumn(ft.Text("Sub ($)")),
            ft.DataColumn(ft.Text("Acción")), 
        ],
        rows=[], expand=True
    )

    lista_resultados = ft.ListView(spacing=2, padding=5, visible=False, height=150)
    input_buscar = ft.TextField(label="Buscar Producto", hint_text="Nombre...", on_change=buscar_dinamico, col={"sm": 12, "md": 3})

    panel_izquierdo = ft.Container(
        expand=True, padding=20, bgcolor=ft.Colors.WHITE, border_radius=10,
        content=ft.Column([
            ft.Text("Registrar venta", size=24, weight=ft.FontWeight.BOLD),
            ft.ResponsiveRow([input_dni, input_cliente, input_direccion]), 
            ft.Divider(color="#EEEEEE"),
            ft.ResponsiveRow([input_buscar, dropdown_empaque, input_cantidad, input_precio_esp, dropdown_moneda, btn_agregar]),
            lista_resultados,
            ft.Container(content=tabla_carrito, expand=True),
            ft.ResponsiveRow([input_observacion])
        ], scroll=ft.ScrollMode.AUTO)
    )

    panel_derecho = ft.Container(
        padding=20, bgcolor=ft.Colors.WHITE, border_radius=10,
        content=ft.Column([
            ft.Text("Detalle de venta", size=20, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Row([ft.Text("Subtotal (S/):"), lbl_total_pen], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([ft.Text("En Dólares ($):"), lbl_total_usd], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(),
            ft.ElevatedButton("Procesar Venta", style=ft.ButtonStyle(bgcolor="#F39C12", color=ft.Colors.WHITE), width=250, height=50, on_click=procesar_venta)
        ], spacing=20)
    )

    # 1. LA CAJA DE VENTAS (contenedor responsivo: apila los paneles en celulares)
    seccion_pos = ft.Container(
        expand=True, padding=20,
        content=ft.ResponsiveRow([
            ft.Column([panel_izquierdo], col={"sm": 12, "md": 8}),
            ft.Column([panel_derecho], col={"sm": 12, "md": 4})
        ]),
        visible=True
    )

    # 2. LÓGICA DEL FORMULARIO DE INVENTARIO (NUEVA ARQUITECTURA RESPONSIVA)
    input_nombre_prod = ft.TextField(label="Nombre del Producto", col={"sm": 12, "md": 8})
    input_presentacion_prod = ft.TextField(label="Presentación", col={"sm": 12, "md": 4})
    input_stock_prod = ft.TextField(label="Stock Inicial", value="0", col={"sm": 12, "md": 4})

    input_precio_uni_pen = ft.TextField(label="Unidad (S/)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_uni_usd = ft.TextField(label="Unidad ($)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_six_pen = ft.TextField(label="Six-pack (S/)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_six_usd = ft.TextField(label="Six-pack ($)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_caja_pen = ft.TextField(label="Caja (S/)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_caja_usd = ft.TextField(label="Caja ($)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_plancha_pen = ft.TextField(label="Plancha (S/)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_plancha_usd = ft.TextField(label="Plancha ($)", value="0.00", col={"sm": 6, "md": 4})

    dialogo_exito = ft.AlertDialog(
        title=ft.Text("¡Operación Exitosa!", color=ft.Colors.GREEN, weight=ft.FontWeight.BOLD),
        content=ft.Text(""), 
        actions=[ft.ElevatedButton("Aceptar", on_click=lambda _: cerrar_dialogo_exito())]
    )

    def cerrar_dialogo_exito():
        dialogo_exito.open = False
        page.update()

    def cerrar_dialogo(e):
        dialogo_producto.open = False
        page.update()

    def guardar_producto_bd(e):
        boton = e.control
        boton.text = "Guardando..."
        boton.disabled = True
        page.update()

        nombre = input_nombre_prod.value.strip()
        presentacion = input_presentacion_prod.value.strip()
        
        if not nombre:
            page.snack_bar = ft.SnackBar(ft.Text("El nombre es obligatorio"), bgcolor=ft.Colors.RED)
            page.snack_bar.open = True
            boton.text = "Guardar"
            boton.disabled = False
            page.update()
            return

        try:
            stock_texto = (input_stock_prod.value or "0").strip()
            if not stock_texto.isdigit():
                raise ValueError("El stock inicial debe ser un entero mayor o igual a 0.")
            stock_ingresado = int(stock_texto)

            def decimal_no_negativo(campo, nombre_campo):
                valor = Decimal((campo.value or "0").strip())
                if valor < 0:
                    raise ValueError(f"{nombre_campo} no puede ser negativo.")
                return valor

            p_uni_pen = decimal_no_negativo(input_precio_uni_pen, "Unidad (S/)")
            p_uni_usd = decimal_no_negativo(input_precio_uni_usd, "Unidad ($)")
            p_six_pen = decimal_no_negativo(input_precio_six_pen, "Six-pack (S/)")
            p_six_usd = decimal_no_negativo(input_precio_six_usd, "Six-pack ($)")
            p_caja_pen = decimal_no_negativo(input_precio_caja_pen, "Caja (S/)")
            p_caja_usd = decimal_no_negativo(input_precio_caja_usd, "Caja ($)")
            p_plan_pen = decimal_no_negativo(input_precio_plancha_pen, "Plancha (S/)")
            p_plan_usd = decimal_no_negativo(input_precio_plancha_usd, "Plancha ($)")

            with obtener_cursor(commit=True) as cursor:
                cursor.execute("SELECT id_producto, stock FROM productos WHERE nombre = %s AND presentacion = %s LIMIT 1", (nombre, presentacion))
                producto_existente = cursor.fetchone()

                if producto_existente:
                    id_prod, stock_actual = producto_existente[0], producto_existente[1]
                    nuevo_stock = stock_actual + stock_ingresado
                    cursor.execute(
                        """UPDATE productos SET stock = %s, 
                           precio_uni_pen = %s, precio_uni_usd = %s, 
                           precio_six_pen = %s, precio_six_usd = %s, 
                           precio_caja_pen = %s, precio_caja_usd = %s, 
                           precio_plancha_pen = %s, precio_plancha_usd = %s 
                           WHERE id_producto = %s""",
                        (nuevo_stock, p_uni_pen, p_uni_usd, p_six_pen, p_six_usd, p_caja_pen, p_caja_usd, p_plan_pen, p_plan_usd, id_prod)
                    )
                    mensaje = f"Se sumaron {stock_ingresado} unidades.\nNuevo stock: {nuevo_stock}"
                else:
                    cursor.execute(
                        """INSERT INTO productos (nombre, presentacion, stock, 
                           precio_uni_pen, precio_uni_usd, precio_six_pen, precio_six_usd, 
                           precio_caja_pen, precio_caja_usd, precio_plancha_pen, precio_plancha_usd) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (nombre, presentacion, stock_ingresado, p_uni_pen, p_uni_usd, p_six_pen, p_six_usd, p_caja_pen, p_caja_usd, p_plan_pen, p_plan_usd)
                    )
                    mensaje = "Producto registrado correctamente en la nueva base de datos."

            dialogo_producto.open = False
            dialogo_exito.content.value = mensaje
            if dialogo_exito not in page.overlay:
                page.overlay.append(dialogo_exito)
            dialogo_exito.open = True
            
            cargar_datos_inventario() 
            
        except Exception as ex:
            print(f"Error guardando: {ex}")
            page.snack_bar = ft.SnackBar(ft.Text("Error al procesar en la BD"), bgcolor=ft.Colors.RED)
            page.snack_bar.open = True
            
        boton.text = "Guardar"
        boton.disabled = False
        page.update()

    dialogo_producto = ft.AlertDialog(
        title=ft.Text("Registrar Nuevo Producto", weight=ft.FontWeight.BOLD),
        content=ft.Container(
            width=650, 
            content=ft.Column(
                [
                    ft.ResponsiveRow([input_nombre_prod, input_presentacion_prod, input_stock_prod]),
                    ft.Divider(),
                    ft.Text("Precios por Unidad", weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.GREY_700),
                    ft.ResponsiveRow([input_precio_uni_pen, input_precio_uni_usd]),
                    ft.Text("Precios por Six-pack", weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.GREY_700),
                    ft.ResponsiveRow([input_precio_six_pen, input_precio_six_usd]),
                    ft.Text("Precios por Caja", weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.GREY_700),
                    ft.ResponsiveRow([input_precio_caja_pen, input_precio_caja_usd]),
                    ft.Text("Precios por Plancha", weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.GREY_700),
                    ft.ResponsiveRow([input_precio_plancha_pen, input_precio_plancha_usd]),
                ],
                scroll=ft.ScrollMode.AUTO, 
                tight=True
            )
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=cerrar_dialogo),
            ft.ElevatedButton("Guardar", bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE, on_click=guardar_producto_bd)
        ]
    )

    def abrir_dialogo_nuevo(e):
        if tiene_permiso():
            input_nombre_prod.value = ""
            input_presentacion_prod.value = ""
            input_stock_prod.value = "0"
            input_precio_uni_pen.value = "0.00"
            input_precio_uni_usd.value = "0.00"
            input_precio_six_pen.value = "0.00"
            input_precio_six_usd.value = "0.00"
            input_precio_caja_pen.value = "0.00"
            input_precio_caja_usd.value = "0.00"
            input_precio_plancha_pen.value = "0.00"
            input_precio_plancha_usd.value = "0.00"
            
            if dialogo_producto not in page.overlay:
                page.overlay.append(dialogo_producto)
            dialogo_producto.open = True
            page.update()

    # 3. VISTA DE INVENTARIO
    vista_inventario = ft.Container(
        expand=True, visible=False, padding=20, bgcolor=ft.Colors.WHITE, border_radius=10,
        content=ft.Column([
            ft.Row([
                ft.Text("Gestión de Inventario", size=24, weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.ElevatedButton("Excel", icon=ft.Icons.DOWNLOAD, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE), on_click=exportar_excel),
                    ft.ElevatedButton("Agregar Producto", icon=ft.Icons.ADD, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE), on_click=abrir_dialogo_nuevo),
                    ft.ElevatedButton("Actualizar Datos", icon=ft.Icons.REFRESH, on_click=lambda _: cargar_datos_inventario())
                ])
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(),
            ft.ListView(controls=[tabla_inventario], expand=True)
        ])
    )

    # 4. ENSAMBLAJE DEL DASHBOARD (MENÚ RETRÁCTIL)
    # (toggle_menu ya se definió más arriba; aquí solo quedaba un duplicado exacto)

    # --- MÓDULO DE REPORTES Y CIERRE DE CAJA ---
    tabla_ventas_diarias = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Ticket", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Hora", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Cliente", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Total (S/)", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Total ($)", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Acciones", weight=ft.FontWeight.BOLD)),
        ],
        rows=[]
    )

    def exportar_ticket_pdf(id_venta, codigo_ticket):
        # 1. Señal visual de inicio de exportación
        page.snack_bar = ft.SnackBar(ft.Text(f"⏳ Generando PDF de {codigo_ticket}...", color=ft.Colors.BLACK, weight=ft.FontWeight.BOLD), bgcolor=ft.Colors.YELLOW)
        page.snack_bar.open = True
        page.update()
        
        try:
            with obtener_cursor() as cursor:
                # Agregamos "vendedor" a la consulta SQL
                cursor.execute("SELECT fecha_emision, hora_emision, vendedor, cliente_nombre, cliente_dni, cliente_direccion, total_pen, total_usd FROM ventas WHERE id_venta = %s", (id_venta,))
                cabecera = cursor.fetchone()

                cursor.execute("SELECT p.nombre, d.cantidad, d.tipo_empaque, d.precio_unitario, d.subtotal_pen, d.subtotal_usd FROM detalles_venta d JOIN productos p ON d.id_producto = p.id_producto WHERE d.id_venta = %s", (id_venta,))
                detalles = cursor.fetchall()

            if not cabecera:
                raise ValueError(f"No se encontró la venta con id {id_venta}.")

            f_emision, h_emision, vendedor, c_nombre, c_dni, c_dir, t_pen, t_usd = cabecera

            # 2. CÁLCULO DEL ALTO DINÁMICO (Corte automático de papel)
            alto_base = 94  # Aumentamos a 94 para darle espacio a la nueva línea del vendedor
            alto_productos = len(detalles) * 5  
            alto_total = alto_base + alto_productos
            
            if t_usd > 0:
                alto_total += 15 

            pdf = FPDF(orientation='P', unit='mm', format=(80, alto_total)) 
            pdf.set_margins(5, 5, 5) 
            pdf.set_auto_page_break(auto=False, margin=0) 
            pdf.add_page()
            
            # --- LOGO CENTRADO ---
            pdf.image("LogoLK.png", x=25, y=5, w=30) 
            pdf.ln(12) 
            
            # --- RECUADRO NOTA DE VENTA ---
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(70, 6, txt=f"NOTA DE VENTA: {codigo_ticket}", border=1, ln=True, align='C')
            
            # --- DATOS DEL CLIENTE Y VENDEDOR ---
            pdf.ln(2)
            pdf.set_font("Arial", size=7)
            pdf.cell(70, 4, txt=f"Fecha: {f_emision}   Hora: {h_emision}", ln=True, align='C')
            
            # Nueva línea para el vendedor, renderizada en mayúsculas
            pdf.cell(70, 4, txt=f"Atendido por: {str(vendedor).upper()}", ln=True, align='L')
            
            pdf.cell(70, 4, txt=f"Cliente: {c_nombre if c_nombre else 'VARIOS'}", ln=True, align='L')
            pdf.cell(70, 4, txt=f"DNI: {c_dni if c_dni else '00000000'}", ln=True, align='L')
            pdf.cell(70, 4, txt=f"Dir: {c_dir[:30] if c_dir else 'Tacna'}", ln=True, align='L')
            
            pdf.ln(3)
            
            # --- CABECERAS TABULARES EN MINIATURA ---
            pdf.set_font("Arial", 'B', 5) 
            pdf.set_fill_color(220, 220, 220) 
            pdf.cell(6, 5, txt="CANT", border=1, align='C', fill=True)
            pdf.cell(9, 5, txt="EMP", border=1, align='C', fill=True)
            pdf.cell(23, 5, txt="DESC", border=1, align='C', fill=True)
            pdf.cell(10, 5, txt="P.UNI", border=1, align='C', fill=True)
            pdf.cell(11, 5, txt="SUB(S/)", border=1, align='C', fill=True)
            pdf.cell(11, 5, txt="SUB($)", border=1, ln=True, align='C', fill=True)
            
            # --- FILAS DE PRODUCTOS ---
            pdf.set_font("Arial", size=5)
            for det in detalles:
                pdf.cell(6, 5, txt=str(det[1]), border=1, align='C')
                pdf.cell(9, 5, txt=str(det[2][:3]).upper(), border=1, align='C') 
                pdf.cell(23, 5, txt=str(det[0][:15]), border=1, align='L')
                pdf.cell(10, 5, txt=f"{det[3]:.1f}", border=1, align='C')
                pdf.cell(11, 5, txt=f"{det[4]:.2f}", border=1, align='R')
                pdf.cell(11, 5, txt=f"{det[5]:.2f}", border=1, ln=True, align='R')
                
            pdf.ln(3)
            
            # --- TOTALES Y CONVERSIÓN A TEXTO ---
            if t_pen > 0:
                pdf.set_font("Arial", 'B', 9)
                pdf.cell(46, 5, txt="TOTAL (S/):", align='R')
                pdf.cell(24, 5, txt=f"{t_pen:.2f}", border=1, ln=True, align='R', fill=True)
                
                entero = int(t_pen)
                centimos = int(round((t_pen - entero) * 100))
                texto_pen = num2words(entero, lang='es').capitalize()
                pdf.set_font("Arial", 'I', 7)
                pdf.multi_cell(70, 4, txt=f"Son: {texto_pen} con {centimos:02d}/100 Soles", align='R')
            
            if t_usd > 0:
                pdf.ln(1)
                pdf.set_font("Arial", 'B', 9)
                pdf.cell(46, 5, txt="TOTAL ($):", align='R')
                pdf.cell(24, 5, txt=f"{t_usd:.2f}", border=1, ln=True, align='R', fill=True)
                
                entero_usd = int(t_usd)
                centimos_usd = int(round((t_usd - entero_usd) * 100))
                texto_usd = num2words(entero_usd, lang='es').capitalize()
                pdf.set_font("Arial", 'I', 7)
                pdf.multi_cell(70, 4, txt=f"Son: {texto_usd} con {centimos_usd:02d}/100 Dolares", align='R')
            
            pdf.ln(5)
            pdf.set_font("Arial", 'B', 7)
            pdf.cell(70, 4, txt="¡Gracias por su compra!", ln=True, align='C')

            # Como la app corre en el navegador (ft.AppView.WEB_BROWSER), el
            # PDF se guarda en la carpeta "assets" del servidor y se abre con
            # launch_url en una pestaña nueva para que el usuario lo vea o
            # descargue; antes se generaba también con os.path.abspath(...)
            # en una ruta del servidor que el usuario no podía ver, y ese
            # segundo bloque corría siempre (incluso si esta parte fallaba),
            # duplicando el PDF y arriesgando un error si "pdf" no existía.
            os.makedirs("assets", exist_ok=True)
            ruta_pdf = os.path.join("assets", f"{codigo_ticket}.pdf")
            pdf.output(ruta_pdf)

            page.launch_url(f"/assets/{codigo_ticket}.pdf", web_window_name="_blank")

            # 3. Señal visual de éxito al finalizar
            page.snack_bar = ft.SnackBar(ft.Text("✅ ¡PDF generado! Se abrió en una pestaña nueva.", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.Colors.GREEN, duration=6000)
            page.snack_bar.open = True
            page.update()

        except Exception as e:
            print(f"Error PDF Térmico: {e}")
            page.snack_bar = ft.SnackBar(ft.Text(f"❌ Error al exportar: {e}", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED)
            page.snack_bar.open = True
            page.update()

    def cargar_ventas_diarias():
        tabla_ventas_diarias.rows.clear()
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT id_venta, codigo_ticket, hora_emision, cliente_nombre, total_pen, total_usd FROM ventas WHERE fecha_emision = CURDATE() ORDER BY id_venta DESC")
                filas = cursor.fetchall()

            for fila in filas:
                id_v, cod, hora, cliente, t_pen, t_usd = fila
                btn_ver = ft.IconButton(ft.Icons.VISIBILITY, icon_color=ft.Colors.BLUE, tooltip="Ver Ticket", on_click=lambda e, i=id_v, c=cod: ver_nota_venta(i, c))
                btn_imprimir = ft.IconButton(ft.Icons.PRINT, icon_color=ft.Colors.GREEN, tooltip="Imprimir", on_click=lambda e: mostrar_mensaje("La impresión directa aún no está configurada. Usa el PDF para imprimir el ticket.", ft.Colors.BLUE))
                btn_pdf = ft.IconButton(ft.Icons.PICTURE_AS_PDF, icon_color=ft.Colors.RED, tooltip="Descargar PDF", on_click=lambda e, i=id_v, c=cod: exportar_ticket_pdf(i, c))
                acciones = ft.Row([btn_ver, btn_imprimir, btn_pdf], spacing=0)
                
                tabla_ventas_diarias.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(cod)),
                    ft.DataCell(ft.Text(str(hora))),
                    ft.DataCell(ft.Text(cliente if cliente else "VARIOS")),
                    ft.DataCell(ft.Text(f"{t_pen:.2f}")),
                    ft.DataCell(ft.Text(f"{t_usd:.2f}")),
                    ft.DataCell(acciones)
                ]))
            page.update()
        except Exception as e:
            print(f"Error cargando ventas: {e}")
            page.snack_bar = ft.SnackBar(ft.Text("No se pudieron cargar las ventas del día.", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED)
            page.snack_bar.open = True
            page.update()

    def cuadrar_caja_diaria(e):
        try:
            with obtener_cursor() as cursor:
                # Sumamos las columnas de totales filtrando solo la fecha de hoy
                cursor.execute("""
                    SELECT SUM(total_pen), SUM(total_usd), COUNT(id_venta) 
                    FROM ventas 
                    WHERE fecha_emision = CURDATE()
                """)
                resultado = cursor.fetchone()
            
            # Asignamos 0 si es que no hay ventas en el día para evitar errores
            total_pen = resultado[0] if resultado[0] else 0.00
            total_usd = resultado[1] if resultado[1] else 0.00
            cantidad_tickets = resultado[2] if resultado[2] else 0
            
            def cerrar_cuadre(e):
                dialogo_cuadre.open = False
                page.update()
            
            # Creamos la ventana emergente con los montos en grande
            dialogo_cuadre = ft.AlertDialog(
                title=ft.Text("Cuadre de Caja Diaria", weight=ft.FontWeight.BOLD, color="#F39C12"),
                content=ft.Column([
                    ft.Text(f"Tickets emitidos hoy: {cantidad_tickets}", size=16),
                    ft.Divider(),
                    ft.Text(f"Total Ingresos (S/): {total_pen:.2f}", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN),
                    ft.Text(f"Total Ingresos ($): {total_usd:.2f}", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
                ], tight=True),
                actions=[ft.ElevatedButton("Aceptar", bgcolor=ft.Colors.BLACK, color=ft.Colors.WHITE, on_click=cerrar_cuadre)]
            )
            
            page.overlay.append(dialogo_cuadre)
            dialogo_cuadre.open = True
            page.update()
            
        except Exception as ex:
            print(f"Error al cuadrar caja: {ex}")
            page.snack_bar = ft.SnackBar(ft.Text("No se pudo calcular el cuadre de caja.", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED)
            page.snack_bar.open = True
            page.update()


    panel_reportes = ft.Container(
        expand=True, visible=False, padding=20, bgcolor=ft.Colors.WHITE, border_radius=10,
        content=ft.Column([
            ft.Text("Cierre de Caja - Historial de Ventas", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(color="#EEEEEE"),
            ft.ResponsiveRow([
                ft.ElevatedButton("Cuadrar Caja Diaria", icon=ft.Icons.CALCULATE, bgcolor="#F39C12", color=ft.Colors.WHITE, on_click=cuadrar_caja_diaria, col={"sm": 12, "md": 3})
            ]),
            # --- Aquí inyectamos el gráfico visual ---
            #ft.Text("Comparativa de Ingresos", size=18, weight=ft.FontWeight.W_600),
            #contenedor_grafico, 
            ft.Divider(color=ft.Colors.TRANSPARENT, height=10),
            # -----------------------------------------
            ft.Container(content=tabla_ventas_diarias, expand=True, padding=ft.Padding(left=0, top=15, right=0, bottom=0))
        ], scroll=ft.ScrollMode.AUTO)
    )

    boton_hamburguesa = ft.IconButton(icon=ft.Icons.MENU, icon_size=30, on_click=toggle_menu)

    area_derecha = ft.Column([
        ft.Row([boton_hamburguesa]),
        seccion_pos,
        vista_inventario,
        panel_reportes # Añadimos el nuevo panel al ensamblaje principal
    ], expand=True)

    vista_dashboard = ft.Row([menu_lateral, area_derecha], expand=True, visible=False)

    # 5. INICIO DE SESIÓN
    input_usuario = ft.TextField(label="Correo electrónico", width=300)
    input_password = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, width=300)

    def iniciar_sesion(e):
        usuario = (input_usuario.value or "").strip()
        password = input_password.value or ""

        # 1. Validación de credenciales contra config.py (hash SHA-256, no texto plano)
        datos_usuario = USUARIOS.get(usuario)
        password_ok = datos_usuario and hashlib.sha256(password.encode()).hexdigest() == datos_usuario["password_hash"]

        if not password_ok:
            page.snack_bar = ft.SnackBar(ft.Text("Credenciales incorrectas", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED)
            page.snack_bar.open = True
            page.update()
            return

        page.rol_usuario = datos_usuario["rol"]
        vista_login.visible = False
        vista_dashboard.visible = True

        if page.rol_usuario == "vendedor":
            # Forzamos la vista de ventas por si se quedó abierta otra pestaña
            seccion_pos.visible = True
            vista_inventario.visible = False
            panel_reportes.visible = False

        # 2. Filtro de seguridad dinámico en el menú lateral
        for boton in menu_lateral.content.controls:
            if hasattr(boton, 'data') and boton.data in ["Inventario", "Reportes"]:
                # Solo serán visibles si el usuario es administrador
                boton.visible = (page.rol_usuario == "admin")

        page.update()

    btn_login = ft.ElevatedButton("Iniciar sesión", style=ft.ButtonStyle(bgcolor="#F39C12", color=ft.Colors.WHITE), width=300, height=50, on_click=iniciar_sesion)

    vista_login = ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.STORE, size=60, color="#F39C12"),
            ft.Text("Bienvenido de vuelta", size=30, weight=ft.FontWeight.BOLD),
            ft.Text("Inicia sesión para continuar", color=ft.Colors.GREY),
            ft.Divider(color=ft.Colors.TRANSPARENT, height=20),
            input_usuario,
            input_password,
            ft.Divider(color=ft.Colors.TRANSPARENT, height=10),
            btn_login
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        alignment=ft.Alignment(0, 0),
        expand=True
    )


    # 6. MONTAJE FINAL EN LA PÁGINA
    page.add(vista_login, vista_dashboard)

# EJECUCIÓN WEB
ft.run(main, view=ft.AppView.WEB_BROWSER, assets_dir="assets")