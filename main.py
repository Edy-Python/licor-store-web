import flet as ft
import textwrap
import datetime
import hashlib
import mysql.connector
import pandas as pd
import os
from contextlib import contextmanager
from num2words import num2words
from fpdf import FPDF
from config import DB_CONFIG, USUARIOS

def conectar_db():
    return mysql.connector.connect(**DB_CONFIG)

@contextmanager
def obtener_cursor(commit=False):
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        yield cursor
        if commit:
            conn.commit()
    finally:
        cursor.close()
        conn.close()

def main(page: ft.Page):
    page.rol_usuario = None  
    page.title = "Likio Licores"
    page.fonts = {
        "Inter": "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
    }
    page.theme = ft.Theme(font_family="Inter")
    page.theme_mode = ft.ThemeMode.LIGHT 
    page.padding = 0 
    page.bgcolor = "#F4F6F8"

    # --- ESTILO UNIVERSAL PARA PANELES (EFECTO TARJETA) ---
    estilo_tarjeta = {
        "padding": 25,
        "bgcolor": ft.colors.WHITE,
        "border_radius": 12,
        "shadow": ft.BoxShadow(
            spread_radius=0, 
            blur_radius=15, 
            color=ft.colors.with_opacity(0.08, ft.colors.BLACK), 
            offset=ft.Offset(0, 4)
        ),
        "border": ft.border.all(1, ft.colors.GREY_100)
    }

    accion_guardada = [None] 
    input_pass_seguridad = ft.TextField(label="Contraseña de Administrador", password=True, can_reveal_password=True)
    
    def confirmar_seguridad(e):
        import hashlib
        hash_ingresado = hashlib.sha256(input_pass_seguridad.value.encode()).hexdigest()
        hash_admin = USUARIOS["admin@likio.com"]["password_hash"]
    
        if hash_ingresado == hash_admin:
            page.close(dialogo_seguridad)
            input_pass_seguridad.value = ""
            page.update()
            if accion_guardada[0]:
                accion_guardada[0]() 
        else:
            page.open(ft.SnackBar(ft.Text("❌ Contraseña incorrecta", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
    
    dialogo_seguridad = ft.AlertDialog(
        title=ft.Text("Verificación de Seguridad", weight=ft.FontWeight.BOLD),
        content=ft.Column([
            ft.Text("Ingresa tu contraseña para autorizar:"),
            input_pass_seguridad
        ], tight=True),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: page.close(dialogo_seguridad)),
            ft.ElevatedButton("Verificar", bgcolor=ft.colors.RED, color=ft.colors.WHITE, on_click=confirmar_seguridad)
        ]
    )
    
    def solicitar_password(accion):
        accion_guardada[0] = accion
        input_pass_seguridad.value = ""
        page.open(dialogo_seguridad)

    def actualizar_totales():
        t_pen = sum(float(row.cells[6].content.value) for row in tabla_carrito.rows)
        t_usd = sum(float(row.cells[7].content.value) for row in tabla_carrito.rows)
        lbl_total_pen.value = f"S/ {t_pen:.2f}"
        lbl_total_usd.value = f"$ {t_usd:.2f}"
        page.update()

    def eliminar_fila(fila_a_borrar):
        if fila_a_borrar in tabla_carrito.rows:
            tabla_carrito.rows.remove(fila_a_borrar)
            tabla_carrito.update()
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

            print(f"Error en búsqueda dinámica: {ex}")

    def agregar_producto(e):
        busqueda = input_buscar.value.strip()
        if not busqueda: return
        
        cant_ingresada = int(input_cantidad.value) if input_cantidad.value and input_cantidad.value.isdigit() else 1
        
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT id_producto, nombre, presentacion, 
                           precio_uni_pen, precio_uni_usd, precio_six_pen, precio_six_usd, 
                           precio_caja_pen, precio_caja_usd, precio_plancha_pen, precio_plancha_usd 
                    FROM productos WHERE id_producto = %s OR nombre = %s LIMIT 1
                """, (busqueda if busqueda.isdigit() else 0, busqueda))
                producto = cursor.fetchone()

            if producto:
                (id_prod, nombre, pres, p_uni_pen, p_uni_usd, p_six_pen, p_six_usd, p_caja_pen, p_caja_usd, p_plan_pen, p_plan_usd) = producto
                
                moneda = dropdown_moneda.value
                empaque = dropdown_empaque.value
                
                precio_final = 0.00
                if empaque == "Unidad": precio_final = p_uni_pen if moneda == "PEN" else p_uni_usd
                elif empaque == "Six-pack": precio_final = p_six_pen if moneda == "PEN" else p_six_usd
                elif empaque == "Caja": precio_final = p_caja_pen if moneda == "PEN" else p_caja_usd
                elif empaque == "Plancha": precio_final = p_plan_pen if moneda == "PEN" else p_plan_usd
                
                if input_precio_esp.value:
                    try:
                        precio_final = float(input_precio_esp.value)
                    except ValueError:
                        pass
                
                sub_pen = (precio_final * cant_ingresada) if moneda == "PEN" else 0.00
                sub_usd = (precio_final * cant_ingresada) if moneda == "USD" else 0.00
                
                id_formateado = str(id_prod).zfill(3)
                
                nueva_fila = ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(id_formateado), width=30)),
                    ft.DataCell(ft.Container(content=ft.Text(str(nombre), size=12, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS), width=170)), # <-- Texto multilínea
                    ft.DataCell(ft.Text(str(pres))),
                    ft.DataCell(ft.Text(empaque)),
                    ft.DataCell(ft.Text(str(cant_ingresada))),
                    ft.DataCell(ft.Text(f"{precio_final:.2f}")),
                    ft.DataCell(ft.Text(f"{sub_pen:.2f}")),
                    ft.DataCell(ft.Text(f"{sub_usd:.2f}"))
                ])
                
                def accion_borrar_carrito(e):
                    fila = e.control.data
                    if fila in tabla_carrito.rows:
                        tabla_carrito.rows.remove(fila)
                        tabla_carrito.update()
                        actualizar_totales()

                btn_eliminar = ft.IconButton(
                    icon=ft.icons.DELETE, 
                    icon_color=ft.colors.RED, 
                    data=nueva_fila, 
                    on_click=accion_borrar_carrito
                )
                
                nueva_fila.cells.append(ft.DataCell(btn_eliminar))
                tabla_carrito.rows.append(nueva_fila)
                tabla_carrito.update()
                
                input_buscar.value = ""
                input_cantidad.value = "1"
                input_precio_esp.value = ""
                lista_resultados.visible = False
                actualizar_totales()
            else:
                page.open(ft.SnackBar(ft.Text("Producto no encontrado."), bgcolor=ft.colors.RED))

        except Exception as ex:
            print(f"Error al agregar al carrito: {ex}")
            page.open(ft.SnackBar(ft.Text("Error al agregar el producto.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

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
            nombre_final = c_nombre.strip() if c_nombre and c_nombre.strip() != "" else "VARIOS"
            dni_final = c_dni.strip() if c_dni and c_dni.strip() != "" else "00000000"
            dir_final = c_dir.strip() if c_dir and c_dir.strip() != "" else "Tacna"
            
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
            
            borde_linea = ft.BorderSide(1, ft.colors.BLACK87)

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
                page.close(dialogo_ticket)

            dialogo_ticket = ft.AlertDialog(
                content=ft.Container(
                    width=380,
                    content=ft.Column([
                        ft.Text("NOTA DE VENTA", size=18, weight=ft.FontWeight.BOLD),
                        ft.Text(codigo_ticket, size=15, weight=ft.FontWeight.BOLD),
                        ft.Divider(color=ft.colors.GREY_300),
                        ft.Row([ft.Text(f"F. Emisión: {f_emision}", size=12)], alignment=ft.MainAxisAlignment.START),
                        ft.Row([ft.Text(f"H. Emisión: {h_emision}", size=12)], alignment=ft.MainAxisAlignment.START),
                        ft.Row([ft.Text(f"Vendedor: {str(vendedor).upper()}", size=12)], alignment=ft.MainAxisAlignment.START),
                        ft.Divider(color=ft.colors.GREY_300),
                        ft.Row([ft.Text(f"Cliente: {nombre_final}", size=12)], alignment=ft.MainAxisAlignment.START),
                        ft.Row([ft.Text(f"DNI: {dni_final}", size=12)], alignment=ft.MainAxisAlignment.START),
                        ft.Row([ft.Text(f"Dirección: {dir_final}", size=12)], alignment=ft.MainAxisAlignment.START),
                        ft.Divider(color=ft.colors.GREY_300),
                        *elementos_finales
                    ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO)
                ),
                actions=[
                    ft.ElevatedButton("Imprimir", icon=ft.icons.PRINT, bgcolor=ft.colors.BLUE, color=ft.colors.WHITE, on_click=lambda e: print("Enviando a impresora...")),
                    ft.ElevatedButton("Cerrar Ticket", bgcolor=ft.colors.BLACK, color=ft.colors.WHITE, on_click=cerrar_ticket)
                ]
            )
                
            page.open(dialogo_ticket)

        except Exception as e:
            print(f"Error generando ticket: {e}")
            page.open(ft.SnackBar(ft.Text("No se pudo generar la nota de venta.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def procesar_venta(e):
        if not tabla_carrito.rows:
            page.open(ft.Text(f"⛔ Venta cancelada: Stock insuficiente de '{nombre_prod}'. Quedan {stock_actual} y solicitas {descuento_stock}.", color=ft.colors.WHITE, weight=ft.FontWeight.BOLD),bgcolor=ft.colors.RED, duration=5000)
            return

        conn = conectar_db()
        try:
            cursor = conn.cursor()
            multiplicadores = {"Unidad": 1, "Six-pack": 6, "Caja": 12, "Plancha": 24}

            items = []
            for row in tabla_carrito.rows:
                id_prod = int(row.cells[0].content.content.value)
                empaque = row.cells[3].content.value
                cant = int(row.cells[4].content.value)
                p_unit = float(row.cells[5].content.value)
                sub_pen = float(row.cells[6].content.value)
                sub_usd = float(row.cells[7].content.value)
                descuento_stock = multiplicadores.get(empaque, 1) * cant

                cursor.execute("SELECT nombre, stock FROM productos WHERE id_producto = %s FOR UPDATE", (id_prod,))
                resultado = cursor.fetchone()

                if not resultado:
                    raise ValueError(f"El producto con id {id_prod} ya no existe.")

                nombre_prod, stock_actual = resultado
                if stock_actual < descuento_stock:
                    conn.rollback()
                    page.open(ft.SnackBar(ft.Text(f"⛔ Venta cancelada: Stock insuficiente...", color=ft.colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.colors.RED, duration=5000))
                    return

                items.append((id_prod, empaque, cant, p_unit, sub_pen, sub_usd, descuento_stock))

            cursor.execute("SELECT COUNT(*) FROM ventas")
            total_registros = cursor.fetchone()[0]
            codigo_ticket = f"NV-{total_registros + 1:08d}"

            ahora_local = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5)))
            fecha_actual = ahora_local.date()
            hora_actual = ahora_local.time()
            
            rol_actual = page.rol_usuario.upper() if hasattr(page, 'rol_usuario') and page.rol_usuario else "ADMIN"
            
            if rol_actual == "ADMIN":
                vendedor_actual = "CRISTIAN"
            elif rol_actual == "VENDEDOR":
                vendedor_actual = "YOSELIN"
            else:
                vendedor_actual = rol_actual
                
            obs = input_observacion.value.strip() if input_observacion.value else "Sin observaciones"

            t_pen = sum(item[4] for item in items)
            t_usd = sum(item[5] for item in items)

            cursor.execute("""
                INSERT INTO ventas (codigo_ticket, fecha_emision, hora_emision, vendedor, cliente_nombre, cliente_dni, cliente_direccion, total_pen, total_usd, observaciones)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (codigo_ticket, fecha_actual, hora_actual, vendedor_actual, input_cliente.value, input_dni.value, input_direccion.value, t_pen, t_usd, obs))
            
            id_venta = cursor.lastrowid

            for id_prod, empaque, cant, p_unit, sub_pen, sub_usd, descuento_stock in items:
                cursor.execute("""
                    INSERT INTO detalles_venta (id_venta, id_producto, tipo_empaque, cantidad, precio_unitario, subtotal_pen, subtotal_usd)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (id_venta, id_prod, empaque, cant, p_unit, sub_pen, sub_usd))

                cursor.execute("UPDATE productos SET stock = stock - %s WHERE id_producto = %s", (descuento_stock, id_prod))

            conn.commit()
            cursor.close()

            tabla_carrito.rows.clear()
            input_dni.value = ""
            input_cliente.value = ""
            input_observacion.value = ""
            actualizar_totales()

            def cerrar_alerta_venta(e):
                page.close(alerta_venta)

            alerta_venta = ft.AlertDialog(
                title=ft.Text("¡Venta Realizada!", color=ft.colors.GREEN, weight=ft.FontWeight.BOLD),
                content=ft.Text(f"Ticket generado: {codigo_ticket}\nEl stock se ha descontado correctamente.", size=16),
                actions=[
                    ft.TextButton("Ver Nota de Venta", on_click=lambda e, id_v=id_venta, cod=codigo_ticket: ver_nota_venta(id_v, cod)),
                    ft.ElevatedButton("Aceptar", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=cerrar_alerta_venta)
                ]
            )
            
            page.open(alerta_venta)

        except Exception as ex:
            conn.rollback()
            print(f"Error procesando la venta: {ex}")
            page.open(ft.SnackBar(ft.Text("Error de conexión a la base de datos.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
        finally:
            conn.close()

    def procesar_excel(e: ft.FilePickerResultEvent):
        if not e.files: return
        ruta = e.files[0].path
        try:
            df = pd.read_excel(ruta)
            with obtener_cursor(commit=True) as cursor:
                for _, fila in df.iterrows():
                    cursor.execute(
                        "INSERT INTO productos (nombre, presentacion, precio) VALUES (%s, %s, %s)",
                        (fila['Nombre'], fila['Presentacion'], fila['Precio'])
                    )
            page.open(ft.SnackBar(ft.Text("Base de datos actualizada con éxito", color=ft.colors.GREEN)))
        except Exception as ex:
            print(f"Error procesando Excel: {ex}")
            page.open(ft.SnackBar(ft.Text(f"❌ Error al procesar el Excel: {ex}", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def cerrar_sesion(e):
        page.client_storage.remove("rol_usuario")

        page.rol_usuario = None 
        input_usuario.value = ""
        input_password.value = ""
        
        vista_dashboard.visible = False 
        vista_login.visible = True
        
        page.update()

    def tiene_permiso():    
        if not hasattr(page, 'rol_usuario') or page.rol_usuario != "admin": 
            page.open(ft.SnackBar(ft.Text("Acceso denegado: Solo el administrador puede modificar.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            return False
        return True

    def accion_protegida_ejemplo(e):
        if tiene_permiso():
            print("Acción permitida: El administrador está modificando datos...")

    tabla_inventario = ft.DataTable(
        heading_row_color=ft.colors.GREY_100,
        border_radius=8,
        border=ft.border.all(1, ft.colors.GREY_200),
        columns=[
            ft.DataColumn(ft.Text("#", weight=ft.FontWeight.BOLD)),
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
            page.open(ft.SnackBar(ft.Text("No se pudo cargar el producto para editar.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            return

        input_add_stock = ft.TextField(label="Añadir Stock (+)", value="0", col={"sm": 12, "md": 4}, bgcolor=ft.colors.BLUE_50, prefix_icon=ft.icons.ADD_BOX)
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
            try:
                stock_sumar = int(input_add_stock.value) if input_add_stock.value.isdigit() else 0

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
                        input_nom.value.strip(), input_pres.value.strip(), stock_sumar,
                        float(inp_pu_pen.value) if inp_pu_pen.value else 0.0, float(inp_pu_usd.value) if inp_pu_usd.value else 0.0,
                        float(inp_ps_pen.value) if inp_ps_pen.value else 0.0, float(inp_ps_usd.value) if inp_ps_usd.value else 0.0,
                        float(inp_pc_pen.value) if inp_pc_pen.value else 0.0, float(inp_pc_usd.value) if inp_pc_usd.value else 0.0,
                        float(inp_pp_pen.value) if inp_pp_pen.value else 0.0, float(inp_pp_usd.value) if inp_pp_usd.value else 0.0,
                        id_prod
                    ))
                page.close(dialogo_editar)
                cargar_datos_inventario()
                page.open(ft.SnackBar(ft.Text("✅ Producto actualizado correctamente", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
            except Exception as ex:
                page.open(ft.SnackBar(ft.Text(f"❌ Error al guardar: {ex}", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
        dialogo_editar = ft.AlertDialog(
            title=ft.Text("Modificar Producto", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=650, 
                content=ft.Column([
                    ft.ResponsiveRow([input_add_stock, input_nom, input_pres]),
                    ft.Divider(),
                    ft.Text("Precios por Unidad", weight=ft.FontWeight.BOLD, size=12, color=ft.colors.GREY_700),
                    ft.ResponsiveRow([inp_pu_pen, inp_pu_usd]),
                    ft.Text("Precios por Six-pack", weight=ft.FontWeight.BOLD, size=12, color=ft.colors.GREY_700),
                    ft.ResponsiveRow([inp_ps_pen, inp_ps_usd]),
                    ft.Text("Precios por Caja", weight=ft.FontWeight.BOLD, size=12, color=ft.colors.GREY_700),
                    ft.ResponsiveRow([inp_pc_pen, inp_pc_usd]),
                    ft.Text("Precios por Plancha", weight=ft.FontWeight.BOLD, size=12, color=ft.colors.GREY_700),
                    ft.ResponsiveRow([inp_pp_pen, inp_pp_usd]),
                ], scroll=ft.ScrollMode.AUTO, tight=True)
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: page.close(dialogo_editar)),
                ft.ElevatedButton("Guardar Cambios", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=guardar_edicion)
            ]
        )
        page.open(dialogo_editar)

    def confirmar_eliminacion(id_prod, nombre_prod):
        if not tiene_permiso(): return
        
        def borrar_bd(e):
            try:
                with obtener_cursor(commit=True) as cursor:
                    cursor.execute("DELETE FROM productos WHERE id_producto = %s", (id_prod,))

                page.close(dialogo_borrar)
                cargar_datos_inventario() 
                
                page.open(ft.SnackBar(ft.Text(f"🗑️ '{nombre_prod}' eliminado", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            except mysql.connector.Error as err:
                if err.errno == 1451:
                    mensaje = f"❌ Protegido: '{nombre_prod}' tiene ventas registradas y no puede eliminarse."
                else:
                    mensaje = f"Error DB: {err}"
                    
                page.close(dialogo_borrar)
                page.open(ft.SnackBar(ft.Text(mensaje, color=ft.colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.colors.RED, duration=5000)) 

        def cancelar_borrado(e):
            page.close(dialogo_borrar)

        dialogo_borrar = ft.AlertDialog(
            title=ft.Text("Confirmar Eliminación", color=ft.colors.RED, weight=ft.FontWeight.BOLD),
            content=ft.Text(f"¿Estás seguro de eliminar '{nombre_prod}' del inventario de forma permanente?"),
            actions=[
                ft.TextButton("Cancelar", on_click=cancelar_borrado),
                ft.ElevatedButton("Eliminar", bgcolor=ft.colors.RED, color=ft.colors.WHITE, on_click=borrar_bd)
            ]
        )
        page.open(dialogo_borrar)

    def cargar_datos_inventario():
        tabla_inventario.rows.clear()
        page.update()
        
        try:
            cat = filtro_cat_inv.value
            nom = filtro_nom_inv.value.strip() if filtro_nom_inv.value else ""
            
            query = "SELECT id_producto, nombre, presentacion, stock, precio_uni_pen, precio_caja_pen FROM productos WHERE 1=1"
            params = []
            
            if cat and cat != "TODAS":
                query += " AND categoria = %s"
                params.append(cat)
            if nom:
                query += " AND nombre LIKE %s"
                params.append(f"%{nom}%")
                
            query += " ORDER BY id_producto ASC"

            with obtener_cursor() as cursor:
                cursor.execute(query, tuple(params))
                filas = cursor.fetchall()
            
            alerta_no_encontrado.visible = (len(filas) == 0)

            correlativo = 1
            for fila in filas:
                id_real = fila[0] 
                nombre_prod = str(fila[1])
                
                btn_editar = ft.IconButton(ft.icons.EDIT, icon_color=ft.colors.BLUE, on_click=lambda e, i=id_real: solicitar_password(lambda: abrir_edicion(i)))
                btn_borrar = ft.IconButton(ft.icons.DELETE, icon_color=ft.colors.RED, on_click=lambda e, i=id_real, n=nombre_prod: solicitar_password(lambda: confirmar_eliminacion(i, n)))
                
                tabla_inventario.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(correlativo))), ft.DataCell(ft.Text(nombre_prod)), ft.DataCell(ft.Text(str(fila[2]))),
                    ft.DataCell(ft.Text(str(fila[3]))), ft.DataCell(ft.Text(f"{fila[4]:.2f}")), ft.DataCell(ft.Text(f"{fila[5]:.2f}")),
                    ft.DataCell(ft.Row([btn_editar, btn_borrar]))
                ]))
                correlativo += 1

            page.update()
        except Exception as e:
            print(f"Error cargando inventario: {e}")
            page.open(ft.SnackBar(ft.Text("No se pudo cargar el inventario.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def exportar_excel(e):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT id_producto, nombre, presentacion, precio_caja_pen, precio_caja_usd, stock FROM productos")
                columnas = [col[0] for col in cursor.description]
                filas = cursor.fetchall()

            df = pd.DataFrame(filas, columns=columnas)

            os.makedirs("assets", exist_ok=True)
            nombre_archivo = "Inventario_LicorStore.xlsx"
            ruta_archivo = os.path.join("assets", nombre_archivo)
            df.to_excel(ruta_archivo, index=False)

            page.launch_url(f"/{nombre_archivo}", web_window_name="_blank")

            page.open(ft.SnackBar(ft.Text("¡Excel generado con éxito! Se abrió en una pestaña nueva.", color=ft.colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.colors.GREEN, duration=6000))

        except Exception as ex:
            print(f"Error al exportar: {ex}")
            page.open(ft.SnackBar(ft.Text(f"❌ Error al exportar: {ex}", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def cambiar_vista(e):
        seccion_pos.visible = False
        vista_inventario.visible = False
        panel_reportes.visible = False
        
        nombre_boton = e.control.data
        
        if nombre_boton == "Ventas":
            seccion_pos.visible = True
        elif nombre_boton == "Inventario":
            vista_inventario.visible = True
            cargar_datos_inventario()
        elif nombre_boton == "Reportes":
            panel_reportes.visible = True
            cargar_ventas_diarias() 
            
        page.update()

    def toggle_menu(e):
        menu_lateral.visible = not menu_lateral.visible
        page.update()

    def crear_boton_menu(texto, icono, funcion_click, color_fondo="#F39C12"):
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(icono, color=ft.colors.BLACK, size=20),
                        bgcolor=color_fondo,
                        border_radius=6,
                        padding=6, 
                    ),
                    ft.Text(texto, color=ft.colors.BLACK, weight=ft.FontWeight.BOLD, size=16),
                ],
                spacing=10,
            ),
            bgcolor=color_fondo,
            padding=10, 
            border_radius=8,
            ink=True,          
            data=texto,        
            on_click=funcion_click,
        )

    menu_lateral = ft.Container(
        width=200, bgcolor="#1A1A1A", padding=20, border_radius=ft.border_radius.only(top_right=15, bottom_right=15),
        content=ft.Column([
            ft.Text("LICOR STORE", color="#F39C12", weight=ft.FontWeight.BOLD, size=20),
            ft.Divider(color="white24"),
            
            crear_boton_menu("Ventas", ft.icons.MONETIZATION_ON, cambiar_vista),
            crear_boton_menu("Inventario", ft.icons.INVENTORY, cambiar_vista),
            crear_boton_menu("Reportes", ft.icons.BAR_CHART, cambiar_vista),
            crear_boton_menu("Configuración", ft.icons.SETTINGS, None),
            
            ft.Divider(color="white24"),
            crear_boton_menu("Cerrar Sesión", ft.icons.EXIT_TO_APP, cerrar_sesion, color_fondo="#E74C3C")
        ], spacing=15)
    )

    input_dni = ft.TextField(label="DNI", hint_text="00000000", col={"sm": 12, "md": 3})
    input_cliente = ft.TextField(label="Cliente", hint_text="Varios", col={"sm": 12, "md": 5})
    input_direccion = ft.TextField(label="Dirección", value="Tacna", col={"sm": 12, "md": 4})
    
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
    
    btn_agregar = ft.ElevatedButton("Agregar", style=ft.ButtonStyle(color=ft.colors.WHITE, bgcolor="#2FA572"), height=50, on_click=agregar_producto, col={"sm": 12, "md": 2})
    
    input_observacion = ft.TextField(label="Comentarios de la venta (Solo uso interno)", multiline=True, col={"sm": 12, "md": 12})

    lbl_total_pen = ft.Text("S/ 0.00", size=24, weight=ft.FontWeight.BOLD, color="#A7BA00")
    lbl_total_usd = ft.Text("$ 0.00", size=24, weight=ft.FontWeight.BOLD, color="#0b9007")
    
    tabla_carrito = ft.DataTable(
        column_spacing=15, 
        heading_row_color=ft.colors.GREY_100,
        border_radius=8,
        border=ft.border.all(1, ft.colors.GREY_200),
        data_row_max_height=65,
        columns=[
            ft.DataColumn(ft.Container(ft.Text("ID"), width=30)), 
            ft.DataColumn(ft.Container(ft.Text("Descripción"), width=170)), # <-- Ancho ampliado
            ft.DataColumn(ft.Text("Pres.")),
            ft.DataColumn(ft.Text("Tipo")),
            ft.DataColumn(ft.Text("Cant.")),
            ft.DataColumn(ft.Text("P. Unit")),
            ft.DataColumn(ft.Text("Sub (S/)")),
            ft.DataColumn(ft.Text("Sub ($)")),
            ft.DataColumn(ft.Text("Acción")), 
        ],
        rows=[]
    )

    lista_resultados = ft.ListView(spacing=2, padding=5, visible=False, height=150)
    input_buscar = ft.TextField(label="Buscar Producto", hint_text="Nombre...", on_change=buscar_dinamico, col={"sm": 12, "md": 3})

    panel_izquierdo = ft.Container(
        **estilo_tarjeta,
        content=ft.Column([
            ft.Text("Registrar venta", size=24, weight=ft.FontWeight.BOLD),
            ft.ResponsiveRow([input_dni, input_cliente, input_direccion]), 
            ft.Divider(color="#EEEEEE"),
            ft.ResponsiveRow([input_buscar, dropdown_empaque, input_cantidad, input_precio_esp, dropdown_moneda, btn_agregar]),
            lista_resultados,
            ft.Container(content=tabla_carrito), 
            ft.ResponsiveRow([input_observacion])
        ]) 
    )

    panel_derecho = ft.Container(
        **estilo_tarjeta,
        content=ft.Column([
            ft.Text("Detalle de venta", size=20, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Row([ft.Text("Subtotal (S/):"), lbl_total_pen], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([ft.Text("En Dólares ($):"), lbl_total_usd], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(),
            ft.ElevatedButton("Procesar Venta", style=ft.ButtonStyle(bgcolor="#F39C12", color=ft.colors.WHITE), width=250, height=50, on_click=procesar_venta)
        ], spacing=20)
    )
    seccion_pos = ft.Container(
        padding=20, 
        content=ft.ResponsiveRow([
            ft.Column([panel_izquierdo], col={"sm": 12, "md": 8}),
            ft.Column([panel_derecho], col={"sm": 12, "md": 4})
        ]),
        visible=True
    )
    input_nombre_prod = ft.TextField(label="Nombre del Producto", col={"sm": 12, "md": 7})
    input_presentacion_prod = ft.TextField(label="Presentación", col={"sm": 12, "md": 5})
    opciones_cat = ["WHISKY", "WHISKEY", "RON","HIELO","CIGARRO", "GOLOSINA", "PISCO", "VINO", "LICOR", "TEQUILA", "CREMA", "GIN", "VODKA", "VERMOUTH", "BRANDY", "COGNAC", "ESPUMANTE", "CHAMPAGNE", "MEZCAL", "CERVEZA", "RTD", "AGUA", "GASEOSA", "ENERGIZANTE", "AGUA TÓNICA", "GINGER ALE", "JUGO"]
    dropdown_categoria = ft.Dropdown(
        label="Categoría",
        options=[ft.dropdown.Option(cat) for cat in opciones_cat],
        col={"sm": 12, "md": 6}
    )
    input_stock_prod = ft.TextField(label="Stock Inicial", value="0", col={"sm": 12, "md": 6})
    input_precio_uni_pen = ft.TextField(label="Unidad (S/)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_uni_usd = ft.TextField(label="Unidad ($)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_six_pen = ft.TextField(label="Six-pack (S/)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_six_usd = ft.TextField(label="Six-pack ($)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_caja_pen = ft.TextField(label="Caja (S/)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_caja_usd = ft.TextField(label="Caja ($)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_plancha_pen = ft.TextField(label="Plancha (S/)", value="0.00", col={"sm": 6, "md": 4})
    input_precio_plancha_usd = ft.TextField(label="Plancha ($)", value="0.00", col={"sm": 6, "md": 4})

    dialogo_exito = ft.AlertDialog(
        title=ft.Text("¡Operación Exitosa!", color=ft.colors.GREEN, weight=ft.FontWeight.BOLD),
        content=ft.Text(""), 
        actions=[ft.ElevatedButton("Aceptar", on_click=lambda _: cerrar_dialogo_exito())]
    )

    def cerrar_dialogo_exito():
        page.close(dialogo_exito)

    def cerrar_dialogo(e):
        page.close(dialogo_producto)

    def guardar_producto_bd(e):
        boton = e.control
        boton.text = "Guardando..."
        boton.disabled = True
        page.update()

        nombre = input_nombre_prod.value.strip()
        presentacion = input_presentacion_prod.value.strip()
        categoria = dropdown_categoria.value if dropdown_categoria.value else "LICOR"
        
        if not nombre:
            page.open(ft.SnackBar(ft.Text("El nombre es obligatorio"), bgcolor=ft.colors.RED))
            boton.text = "Guardar"
            boton.disabled = False
            page.update()
            return

        try:
            stock_ingresado = int(input_stock_prod.value) if input_stock_prod.value.isdigit() else 0
            p_uni_pen = float(input_precio_uni_pen.value) if input_precio_uni_pen.value else 0.00
            p_uni_usd = float(input_precio_uni_usd.value) if input_precio_uni_usd.value else 0.00
            p_six_pen = float(input_precio_six_pen.value) if input_precio_six_pen.value else 0.00
            p_six_usd = float(input_precio_six_usd.value) if input_precio_six_usd.value else 0.00
            p_caja_pen = float(input_precio_caja_pen.value) if input_precio_caja_pen.value else 0.00
            p_caja_usd = float(input_precio_caja_usd.value) if input_precio_caja_usd.value else 0.00
            p_plan_pen = float(input_precio_plancha_pen.value) if input_precio_plancha_pen.value else 0.00
            p_plan_usd = float(input_precio_plancha_usd.value) if input_precio_plancha_usd.value else 0.00

            with obtener_cursor(commit=True) as cursor:
                cursor.execute("SELECT id_producto, stock FROM productos WHERE nombre = %s AND presentacion = %s LIMIT 1", (nombre, presentacion))
                producto_existente = cursor.fetchone()

                if producto_existente:
                    id_prod, stock_actual = producto_existente[0], producto_existente[1]
                    nuevo_stock = stock_actual + stock_ingresado
                    cursor.execute(
                        """UPDATE productos SET stock = %s, categoria = %s, 
                           precio_uni_pen = %s, precio_uni_usd = %s, 
                           precio_six_pen = %s, precio_six_usd = %s, 
                           precio_caja_pen = %s, precio_caja_usd = %s, 
                           precio_plancha_pen = %s, precio_plancha_usd = %s 
                           WHERE id_producto = %s""",
                        (nuevo_stock, categoria, p_uni_pen, p_uni_usd, p_six_pen, p_six_usd, p_caja_pen, p_caja_usd, p_plan_pen, p_plan_usd, id_prod)
                    )
                    mensaje = f"Se sumaron {stock_ingresado} unidades.\nNuevo stock: {nuevo_stock}"
                else:
                    cursor.execute(
                        """INSERT INTO productos (nombre, presentacion, categoria, stock, 
                           precio_uni_pen, precio_uni_usd, precio_six_pen, precio_six_usd, 
                           precio_caja_pen, precio_caja_usd, precio_plancha_pen, precio_plancha_usd) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (nombre, presentacion, categoria, stock_ingresado, p_uni_pen, p_uni_usd, p_six_pen, p_six_usd, p_caja_pen, p_caja_usd, p_plan_pen, p_plan_usd)
                    )
                    mensaje = "Producto registrado correctamente."

            page.close(dialogo_producto) 
            dialogo_exito.content.value = mensaje
            page.open(dialogo_exito)
            
            cargar_datos_inventario() 
            
        except Exception as ex:
            print(f"Error guardando: {ex}")
            page.open(ft.SnackBar(ft.Text("Error al procesar en la BD"), bgcolor=ft.colors.RED))
            
        boton.text = "Guardar"
        boton.disabled = False
        page.update()

    dialogo_producto = ft.AlertDialog(
        title=ft.Text("Registrar Nuevo Producto", weight=ft.FontWeight.BOLD),
        content=ft.Container(
            width=650, 
            content=ft.Column(
                [
                    ft.ResponsiveRow([input_nombre_prod, input_presentacion_prod]),
                    ft.ResponsiveRow([dropdown_categoria, input_stock_prod]),
                    ft.Divider(),
                    ft.Text("Precios por Unidad", weight=ft.FontWeight.BOLD, size=12, color=ft.colors.GREY_700),
                    ft.ResponsiveRow([input_precio_uni_pen, input_precio_uni_usd]),
                    ft.Text("Precios por Six-pack", weight=ft.FontWeight.BOLD, size=12, color=ft.colors.GREY_700),
                    ft.ResponsiveRow([input_precio_six_pen, input_precio_six_usd]),
                    ft.Text("Precios por Caja", weight=ft.FontWeight.BOLD, size=12, color=ft.colors.GREY_700),
                    ft.ResponsiveRow([input_precio_caja_pen, input_precio_caja_usd]),
                    ft.Text("Precios por Plancha", weight=ft.FontWeight.BOLD, size=12, color=ft.colors.GREY_700),
                    ft.ResponsiveRow([input_precio_plancha_pen, input_precio_plancha_usd]),
                ],
                scroll=ft.ScrollMode.AUTO, 
                tight=True
            )
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=cerrar_dialogo),
            ft.ElevatedButton("Guardar", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=guardar_producto_bd)
        ]
    )

    def abrir_dialogo_nuevo(e):
        if tiene_permiso():
            input_nombre_prod.value = ""
            input_presentacion_prod.value = ""
            dropdown_categoria.value = None
            input_stock_prod.value = "0"
            input_precio_uni_pen.value = "0.00"
            input_precio_uni_usd.value = "0.00"
            input_precio_six_pen.value = "0.00"
            input_precio_six_usd.value = "0.00"
            input_precio_caja_pen.value = "0.00"
            input_precio_caja_usd.value = "0.00"
            input_precio_plancha_pen.value = "0.00"
            input_precio_plancha_usd.value = "0.00"
            
            page.open(dialogo_producto)

    opciones_filtro = ["TODAS", "WHISKY", "WHISKEY", "RON", "PISCO", "VINO", "LICOR", "TEQUILA", "CREMA", "GIN", "VODKA", "VERMOUTH", "BRANDY", "COGNAC", "ESPUMANTE", "CHAMPAGNE", "MEZCAL", "CERVEZA", "RTD", "AGUA", "GASEOSA", "ENERGIZANTE", "AGUA TÓNICA", "GINGER ALE", "JUGO"]
    
    filtro_cat_inv = ft.Dropdown(options=[ft.dropdown.Option(c) for c in opciones_filtro], value="TODAS", label="Filtrar Categoría", col={"sm": 12, "md": 4}, on_change=lambda _: cargar_datos_inventario())
    filtro_nom_inv = ft.TextField(label="Buscar producto por nombre...", prefix_icon=ft.icons.SEARCH, col={"sm": 12, "md": 8}, on_change=lambda _: cargar_datos_inventario())
    alerta_no_encontrado = ft.Text("❌ Producto no encontrado.", color=ft.colors.RED, visible=False, weight=ft.FontWeight.BOLD)

    vista_inventario = ft.Container(
        visible=False, 
        **estilo_tarjeta,
        content=ft.Column([
            ft.Row([
                ft.Text("Gestión de Inventario", size=22, weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.ElevatedButton("Excel", icon=ft.icons.DOWNLOAD, style=ft.ButtonStyle(bgcolor=ft.colors.BLUE, color=ft.colors.WHITE), on_click=exportar_excel),
                    ft.ElevatedButton("Agregar", icon=ft.icons.ADD, style=ft.ButtonStyle(bgcolor=ft.colors.GREEN, color=ft.colors.WHITE), on_click=abrir_dialogo_nuevo),
                ])
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.ResponsiveRow([filtro_cat_inv, filtro_nom_inv]),
            alerta_no_encontrado,
            ft.Divider(),
            ft.Column([tabla_inventario])
        ])
    )
    tabla_ventas_diarias = ft.DataTable(
        heading_row_color=ft.colors.GREY_100,
        border_radius=8,
        border=ft.border.all(1, ft.colors.GREY_200),
        columns=[
            ft.DataColumn(ft.Text("Ticket", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Fecha y Hora", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Cliente", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Total (S/)", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Total ($)", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Acciones", weight=ft.FontWeight.BOLD)),
        ],
        rows=[]
    )

    def exportar_ticket_pdf(id_venta, codigo_ticket):
        page.open(ft.SnackBar(ft.Text(f"⏳ Generando PDF de {codigo_ticket}...", color=ft.colors.BLACK, weight=ft.FontWeight.BOLD), bgcolor=ft.colors.YELLOW))

        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT fecha_emision, hora_emision, vendedor, cliente_nombre, cliente_dni, cliente_direccion, total_pen, total_usd FROM ventas WHERE id_venta = %s", (id_venta,))
                cabecera = cursor.fetchone()

                cursor.execute("SELECT p.nombre, d.cantidad, d.tipo_empaque, d.precio_unitario, d.subtotal_pen, d.subtotal_usd FROM detalles_venta d JOIN productos p ON d.id_producto = p.id_producto WHERE d.id_venta = %s", (id_venta,))
                detalles = cursor.fetchall()

            if not cabecera:
                raise ValueError(f"No se encontró la venta con id {id_venta}.")

            f_emision, h_emision, vendedor, c_nombre, c_dni, c_dir, t_pen, t_usd = cabecera

            alto_base = 120 
            alto_productos = len(detalles) * 5  
            alto_total = alto_base + alto_productos

            pdf = FPDF(orientation='P', unit='mm', format=(80, alto_total)) 
            pdf.set_margins(5, 5, 5) 
            pdf.set_auto_page_break(auto=False, margin=0) 
            pdf.add_page()
            
            pdf.image("LogoLK.png", x=15, y=5, w=50) 
            pdf.ln(18) 
            
            pdf.set_font("Arial", size=7)
            pdf.cell(70, 4, txt="Calle Uruguay 409, CC Polvos Rosados", ln=True, align='C')
            pdf.cell(70, 4, txt="Al Costado De La Puerta 15", ln=True, align='C')
            pdf.ln(3)

            pdf.set_font("Arial", 'B', 10)
            pdf.cell(70, 5, txt="Nota de Venta", ln=True, align='C')
            pdf.cell(70, 5, txt=codigo_ticket, ln=True, align='C')
            pdf.ln(3)
            
            pdf.set_font("Arial", size=7)
            
            def dibujar_fila_cliente(etiqueta, valor):
                pdf.cell(18, 4, txt=etiqueta, align='L')
                pdf.cell(52, 4, txt=str(valor), ln=True, align='L')

            dibujar_fila_cliente("F. Emisión:", f_emision)
            dibujar_fila_cliente("H. Emisión:", h_emision)
            dibujar_fila_cliente("Cliente:", c_nombre if c_nombre else 'VARIOS')
            dibujar_fila_cliente("DNI:", c_dni if c_dni else '00000000')
            dibujar_fila_cliente("Dirección:", c_dir[:30] if c_dir else 'Tacna')
            pdf.ln(2)
            
            pdf.set_font("Arial", 'B', 6) 
            pdf.cell(6, 5, txt="Cant", border=1, align='C')
            pdf.cell(8, 5, txt="Unid", border=1, align='C')
            pdf.cell(26, 5, txt="Descripción", border=1, align='C')
            pdf.cell(10, 5, txt="P.U.", border=1, align='C')
            pdf.cell(10, 5, txt="Total S/", border=1, align='C')
            pdf.cell(10, 5, txt="Total $", border=1, ln=True, align='C')
            
            pdf.set_font("Arial", size=5)
            for det in detalles:
                lineas_desc = textwrap.wrap(str(det[0]), width=22)
                if not lineas_desc: lineas_desc = [""]

                if len(lineas_desc) == 1:
                    pdf.cell(6, 5, txt=str(det[1]), border=1, align='C')
                    pdf.cell(8, 5, txt=str(det[2][:3]).upper(), border=1, align='C') 
                    pdf.cell(26, 5, txt=lineas_desc[0], border=1, align='L')
                    pdf.cell(10, 5, txt=f"{det[3]:.2f}", border=1, align='C')
                    pdf.cell(10, 5, txt=f"{det[4]:.2f}", border=1, align='R')
                    pdf.cell(10, 5, txt=f"{det[5]:.2f}", border=1, ln=True, align='R')
                
                else:
                    pdf.cell(6, 5, txt=str(det[1]), border='LTR', align='C')
                    pdf.cell(8, 5, txt=str(det[2][:3]).upper(), border='LTR', align='C') 
                    pdf.cell(26, 5, txt=lineas_desc[0], border='LTR', align='L')
                    pdf.cell(10, 5, txt=f"{det[3]:.2f}", border='LTR', align='C')
                    pdf.cell(10, 5, txt=f"{det[4]:.2f}", border='LTR', align='R')
                    pdf.cell(10, 5, txt=f"{det[5]:.2f}", border='LTR', ln=True, align='R')

                    for i, linea_extra in enumerate(lineas_desc[1:]):
                        es_ultima = (i == len(lineas_desc[1:]) - 1)
                        borde_estilo = 'LBR' if es_ultima else 'LR'
                        
                        pdf.cell(6, 5, txt="", border=borde_estilo, align='C')
                        pdf.cell(8, 5, txt="", border=borde_estilo, align='C') 
                        pdf.cell(26, 5, txt=linea_extra, border=borde_estilo, align='L')
                        pdf.cell(10, 5, txt="", border=borde_estilo, align='C')
                        pdf.cell(10, 5, txt="", border=borde_estilo, align='R')
                        pdf.cell(10, 5, txt="", border=borde_estilo, ln=True, align='R')
                
            pdf.ln(3)
            
            pdf.set_font("Arial", 'B', 7)
            if t_pen > 0:
                pdf.cell(40, 4, txt="", align='L')
                pdf.cell(20, 4, txt="Total a pagar: S/", align='R')
                pdf.cell(10, 4, txt=f"{t_pen:.2f}", ln=True, align='R')
            if t_usd > 0:
                pdf.cell(40, 4, txt="", align='L')
                pdf.cell(20, 4, txt="Total a pagar: $", align='R')
                pdf.cell(10, 4, txt=f"{t_usd:.2f}", ln=True, align='R')
                
            pdf.ln(2)
            
            pdf.set_font("Arial", 'B', 7)
            if t_pen > 0:
                entero = int(t_pen)
                centimos = int(round((t_pen - entero) * 100))
                texto_pen = num2words(entero, lang='es').capitalize()
                pdf.cell(70, 4, txt=f"Son: {texto_pen} con {centimos:02d}/100 Soles", ln=True, align='L')
            
            if t_usd > 0:
                entero_usd = int(t_usd)
                centimos_usd = int(round((t_usd - entero_usd) * 100))
                texto_usd = num2words(entero_usd, lang='es').capitalize()
                pdf.cell(70, 4, txt=f"Son: {texto_usd} con {centimos_usd:02d}/100 Dólares Americanos", ln=True, align='L')
            
            pdf.ln(3)
            
            pdf.cell(70, 4, txt="Condición de Pago: Contado", ln=True, align='L')
            pdf.cell(70, 4, txt="Pagos:", ln=True, align='L')
            
            pdf.set_font("Arial", size=7)
            if t_pen > 0:
                pdf.cell(70, 4, txt=f"- Efectivo - S/ {t_pen:.2f}", ln=True, align='L')
            if t_usd > 0:
                pdf.cell(70, 4, txt=f"- Efectivo - $ {t_usd:.2f}", ln=True, align='L')
                
            pdf.set_font("Arial", 'B', 7)
            pdf.cell(70, 4, txt=f"Vendedor: {str(vendedor).upper()}", ln=True, align='L')

            pdf.ln(5)
            pdf.set_font("Arial", size=7)
            pdf.cell(70, 4, txt="¡Gracias por su compra!", ln=True, align='C')

            os.makedirs("assets", exist_ok=True)
            ruta_pdf = os.path.join("assets", f"{codigo_ticket}.pdf")
            pdf.output(ruta_pdf)

            page.launch_url(f"/{codigo_ticket}.pdf", web_window_name="_blank") 

            page.open(ft.SnackBar(ft.Text("✅ ¡PDF generado! Se abrió en una pestaña nueva.", color=ft.colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.colors.GREEN, duration=6000))

        except Exception as e:
            print(f"Error PDF Térmico: {e}")
            page.open(ft.SnackBar(ft.Text(f"❌ Error al exportar: {e}", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def anular_venta(id_v, cod_ticket):
        def confirmar_anulacion(e):
            try:
                with obtener_cursor(commit=True) as cursor:
                    cursor.execute("UPDATE ventas SET estado = 'Anulada' WHERE id_venta = %s", (id_v,))
                    
                    cursor.execute("SELECT id_producto, cantidad, tipo_empaque FROM detalles_venta WHERE id_venta = %s", (id_v,))
                    detalles = cursor.fetchall()
                    multiplicadores = {"Unidad": 1, "Six-pack": 6, "Caja": 12, "Plancha": 24}
                    
                    for det in detalles:
                        id_p, cant, emp = det
                        devolucion = cant * multiplicadores.get(emp, 1)
                        cursor.execute("UPDATE productos SET stock = stock + %s WHERE id_producto = %s", (devolucion, id_p))
                page.close(dialogo_anular)
                cargar_ventas_diarias()
                cargar_datos_inventario() 
                page.open(ft.SnackBar(ft.Text(f"Ticket {cod_ticket} anulado y stock devuelto.", color=ft.colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.colors.ORANGE))
            except Exception as ex:
                print(f"Error anulando: {ex}")
                page.open(ft.SnackBar(ft.Text("Error al procesar la anulación.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

        dialogo_anular = ft.AlertDialog(
            title=ft.Text("Confirmar Anulación", color=ft.colors.RED, weight=ft.FontWeight.BOLD),
            content=ft.Text(f"¿Estás seguro de anular la venta {cod_ticket}?\n\nEl stock de estos productos se devolverá automáticamente a tu inventario."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: page.close(dialogo_anular)),
                ft.ElevatedButton("Anular Venta", bgcolor=ft.colors.RED, color=ft.colors.WHITE, on_click=confirmar_anulacion)
            ]
        )
    
        page.open(dialogo_anular)

    def cargar_ventas_diarias():
        tabla_ventas_diarias.rows.clear()
        
        def clic_ver(e):
            id_v, cod = e.control.data
            ver_nota_venta(id_v, cod)

        def clic_pdf(e):
            id_v, cod = e.control.data
            exportar_ticket_pdf(id_v, cod)

        def clic_anular(e):
            id_v, cod = e.control.data
            solicitar_password(lambda: anular_venta(id_v, cod))

        try:
            rango = filtro_rango_rep.value
            fecha_hoy = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).date()
            
            query = "SELECT id_venta, codigo_ticket, fecha_emision, hora_emision, cliente_nombre, total_pen, total_usd, estado FROM ventas WHERE 1=1"
            params = []
            
            if rango == "Hoy":
                query += " AND fecha_emision = %s"
                params.append(fecha_hoy)
            elif rango == "Últimos 7 días":
                query += " AND fecha_emision >= %s"
                params.append(fecha_hoy - datetime.timedelta(days=7))
            elif rango == "Últimos 30 días":
                query += " AND fecha_emision >= %s"
                params.append(fecha_hoy - datetime.timedelta(days=30))
            elif rango == "Personalizado" and input_fecha_inicio.value and input_fecha_fin.value:
                query += " AND fecha_emision BETWEEN %s AND %s"
                params.extend([input_fecha_inicio.value, input_fecha_fin.value])
                
            query += " ORDER BY id_venta DESC"

            with obtener_cursor() as cursor:
                cursor.execute(query, tuple(params))
                filas = cursor.fetchall()

            for fila in filas:
                id_v, cod, fecha, hora, cliente, t_pen, t_usd, estado = fila 
                
                es_anulada = (estado == "Anulada")
                color_texto = ft.colors.RED if es_anulada else ft.colors.BLACK
                texto_cliente = f"{cliente} (ANULADO)" if es_anulada else (cliente if cliente else "VARIOS")
                
                fecha_hora_str = f"{fecha}  {hora}" 

                btn_ver = ft.IconButton(ft.icons.VISIBILITY, icon_color=ft.colors.BLUE, tooltip="Ver Ticket", data=(id_v, cod), on_click=clic_ver)
                btn_imprimir = ft.IconButton(ft.icons.PRINT, icon_color=ft.colors.GREEN, tooltip="Imprimir", data=(id_v, cod), on_click=clic_pdf)
                btn_pdf = ft.IconButton(ft.icons.PICTURE_AS_PDF, icon_color=ft.colors.RED, tooltip="Descargar PDF", data=(id_v, cod), on_click=clic_pdf)
                btn_anular = ft.IconButton(ft.icons.CANCEL, icon_color=ft.colors.GREY if es_anulada else ft.colors.RED, disabled=es_anulada, data=(id_v, cod), on_click=clic_anular)
                
                acciones = ft.Row([btn_ver, btn_imprimir, btn_pdf, btn_anular], spacing=0)
                
                tabla_ventas_diarias.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(cod, color=color_texto)), 
                    ft.DataCell(ft.Text(fecha_hora_str, color=color_texto)),
                    ft.DataCell(ft.Text(texto_cliente, color=color_texto, weight=ft.FontWeight.BOLD if es_anulada else ft.FontWeight.NORMAL)),
                    ft.DataCell(ft.Text(f"{t_pen:.2f}", color=color_texto)),
                    ft.DataCell(ft.Text(f"{t_usd:.2f}", color=color_texto)),
                    ft.DataCell(acciones)
                ]))
                
            tabla_ventas_diarias.update()
            page.update()
        except Exception as e:
            print(f"Error cargando ventas: {e}")
            page.open(ft.SnackBar(ft.Text("No se pudieron cargar las ventas.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def cuadrar_caja_diaria(e):
        try:
            rango = filtro_rango_rep.value
            fecha_hoy = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).date()
            
            query = "SELECT SUM(total_pen), SUM(total_usd), COUNT(id_venta) FROM ventas WHERE estado != 'Anulada'"
            params = []
            
            if rango == "Hoy":
                query += " AND fecha_emision = %s"
                params.append(fecha_hoy)
            elif rango == "Últimos 7 días":
                query += " AND fecha_emision >= %s"
                params.append(fecha_hoy - datetime.timedelta(days=7))
            elif rango == "Últimos 30 días":
                query += " AND fecha_emision >= %s"
                params.append(fecha_hoy - datetime.timedelta(days=30))
            elif rango == "Personalizado" and input_fecha_inicio.value and input_fecha_fin.value:
                query += " AND fecha_emision BETWEEN %s AND %s"
                params.extend([input_fecha_inicio.value, input_fecha_fin.value])

            with obtener_cursor() as cursor:
                cursor.execute(query, tuple(params))
                resultado = cursor.fetchone()
            
            total_pen = resultado[0] if resultado[0] else 0.00
            total_usd = resultado[1] if resultado[1] else 0.00
            cantidad_tickets = resultado[2] if resultado[2] else 0
            
            def cerrar_cuadre(e):
                page.close(dialogo_cuadre)
            
            dialogo_cuadre = ft.AlertDialog(
                title=ft.Text("Cuadre de Caja Diaria", weight=ft.FontWeight.BOLD, color="#F39C12"),
                content=ft.Column([
                    ft.Text(f"Tickets Válidos Emitidos Hoy: {cantidad_tickets}", size=16),
                    ft.Divider(),
                    ft.Text(f"Total Ingresos (S/): {total_pen:.2f}", size=22, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN),
                    ft.Text(f"Total Ingresos ($): {total_usd:.2f}", size=22, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE),
                ], tight=True),
                actions=[ft.ElevatedButton("Aceptar", bgcolor=ft.colors.BLACK, color=ft.colors.WHITE, on_click=cerrar_cuadre)]
            )
            
            page.open(dialogo_cuadre)
            
        except Exception as ex:
            print(f"Error al cuadrar caja: {ex}")
            page.open(ft.SnackBar(ft.Text("No se pudo calcular el cuadre de caja.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

            # --- GRÁFICO DE BARRAS (INGRESOS DIARIOS) ---
    #grafico_ingresos = ft.BarChart(
        #bar_groups=[
            #ft.BarChartGroup(x=0, bar_rods=[ft.BarChartRod(from_y=0, to_y=0, width=45, color=ft.colors.GREEN, tooltip="Soles")]),
            #ft.BarChartGroup(x=1, bar_rods=[ft.BarChartRod(from_y=0, to_y=0, width=45, color=ft.colors.BLUE, tooltip="Dólares")])
        #],
        #bottom_axis=ft.ChartAxis(
            #labels=[
                #ft.ChartAxisLabel(value=0, label=ft.Text("Soles (S/)", weight=ft.FontWeight.BOLD)),
                #ft.ChartAxisLabel(value=1, label=ft.Text("Dólares ($)", weight=ft.FontWeight.BOLD))
            #],
            #labels_size=40
        #),
        #horizontal_grid_lines=ft.ChartGridLines(color=ft.colors.GREY_300, width=1, dash_pattern=[3, 3]),
        #tooltip_bgcolor=ft.colors.BLACK87
        #interactive=True
    #)

    #contenedor_grafico = ft.Container(
        #content=grafico_ingresos,
        #height=300,
        #padding=20,
        #bgcolor=ft.colors.WHITE,
        #border_radius=10,
        #border=ft.border.all(1, ft.colors.GREY_200)
    #)

    #def actualizar_grafico_barras():
        #try:
            #conn = conectar_db()
            #cursor = conn.cursor()
            #cursor.execute("SELECT SUM(total_pen), SUM(total_usd) FROM ventas WHERE fecha_emision = CURDATE()")
            #resultado = cursor.fetchone()
            #conn.close()

            # Evitamos valores nulos si no hay ventas
            #total_pen = float(resultado[0]) if resultado[0] else 0.0
            #total_usd = float(resultado[1]) if resultado[1] else 0.0

            # Inyectamos los totales a la altura de cada barra respectiva
            #grafico_ingresos.bar_groups[0].bar_rods[0].to_y = total_pen
            #grafico_ingresos.bar_groups[1].bar_rods[0].to_y = total_usd
            
            # Dinamismo del techo visual: Le damos un 20% de aire por encima del valor más alto
            #max_y = max(total_pen, total_usd)
            #grafico_ingresos.max_y = max_y + (max_y * 0.2) if max_y > 0 else 100
            
            #page.update()
        #except Exception as e:
            #print(f"Error al cargar gráfico: {e}")


    def cambiar_filtro_reportes(e):
        es_personalizado = (filtro_rango_rep.value == "Personalizado")
        input_fecha_inicio.visible = es_personalizado
        input_fecha_fin.visible = es_personalizado
        btn_aplicar_fechas.visible = es_personalizado
        page.update()
        if not es_personalizado:
            cargar_ventas_diarias()

    filtro_rango_rep = ft.Dropdown(
        label="Rango de Fechas",
        options=[
            ft.dropdown.Option("Hoy"), ft.dropdown.Option("Últimos 7 días"), 
            ft.dropdown.Option("Últimos 30 días"), ft.dropdown.Option("Todo el historial"),
            ft.dropdown.Option("Personalizado")
        ],
        value="Hoy", col={"sm": 12, "md": 4}, on_change=cambiar_filtro_reportes
    )
    
    input_fecha_inicio = ft.TextField(label="Inicio (YYYY-MM-DD)", hint_text="Ej: 2026-09-01", col={"sm": 6, "md": 3}, visible=False)
    input_fecha_fin = ft.TextField(label="Fin (YYYY-MM-DD)", hint_text="Ej: 2026-09-30", col={"sm": 6, "md": 3}, visible=False)
    btn_aplicar_fechas = ft.ElevatedButton("Aplicar", bgcolor=ft.colors.BLUE, color=ft.colors.WHITE, on_click=lambda _: cargar_ventas_diarias(), col={"sm": 12, "md": 2}, visible=False)

    panel_reportes = ft.Container(
        visible=False, 
        **estilo_tarjeta,
        content=ft.Column([
            ft.Text("Cierre de Caja - Historial de Ventas", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(color="#EEEEEE"),
            ft.ResponsiveRow([filtro_rango_rep, input_fecha_inicio, input_fecha_fin, btn_aplicar_fechas]),
            ft.Divider(color=ft.colors.TRANSPARENT, height=10),
            ft.ResponsiveRow([
                ft.ElevatedButton("Cuadrar Caja (Rango Actual)", icon=ft.icons.CALCULATE, bgcolor="#F39C12", color=ft.colors.WHITE, on_click=cuadrar_caja_diaria, col={"sm": 12, "md": 4})
            ]),
            ft.Divider(color=ft.colors.TRANSPARENT, height=10),
            ft.Container(content=tabla_ventas_diarias, padding=ft.Padding(left=0, top=15, right=0, bottom=0))
        ])
    )

    boton_hamburguesa = ft.IconButton(icon=ft.icons.MENU, icon_size=30, on_click=toggle_menu)

    area_derecha = ft.Column([
        ft.Row([boton_hamburguesa]),
        seccion_pos,
        vista_inventario,
        panel_reportes
    ], expand=True, scroll=ft.ScrollMode.AUTO)

    vista_dashboard = ft.Row([menu_lateral, area_derecha], visible=False, expand=True, vertical_alignment=ft.CrossAxisAlignment.START)

    input_usuario = ft.TextField(label="Correo electrónico", width=300)
    input_password = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, width=300)

    def iniciar_sesion(e):
        usuario = (input_usuario.value or "").strip()
        password = input_password.value or ""

        datos_usuario = USUARIOS.get(usuario)
        password_ok = datos_usuario and hashlib.sha256(password.encode()).hexdigest() == datos_usuario["password_hash"]

        if not password_ok:
            page.open(ft.SnackBar(ft.Text("Credenciales incorrectas", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            return

        page.rol_usuario = datos_usuario["rol"]
        page.client_storage.set("rol_usuario", page.rol_usuario)
        vista_login.visible = False
        vista_dashboard.visible = True

        if page.rol_usuario == "vendedor":
            seccion_pos.visible = True
            vista_inventario.visible = False
            panel_reportes.visible = False

        for boton in menu_lateral.content.controls:
            if hasattr(boton, 'data') and boton.data in ["Inventario", "Reportes"]:
                boton.visible = (page.rol_usuario == "admin")

        page.update()

    btn_login = ft.ElevatedButton("Iniciar sesión", style=ft.ButtonStyle(bgcolor="#F39C12", color=ft.colors.WHITE), width=300, height=50, on_click=iniciar_sesion)

    vista_login = ft.Container(
        expand=True,
        content=ft.Column([
            ft.Icon(ft.icons.STORE, size=60, color="#F39C12"),
            ft.Text("Bienvenido de vuelta", size=30, weight=ft.FontWeight.BOLD),
            ft.Text("Inicia sesión para continuar", color=ft.colors.GREY),
            ft.Divider(color=ft.colors.TRANSPARENT, height=20),
            input_usuario,
            input_password,
            ft.Divider(color=ft.colors.TRANSPARENT, height=10),
            btn_login
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        alignment=ft.Alignment(0, 0)
    )

    rol_guardado = page.client_storage.get("rol_usuario")
    
    if rol_guardado:
        page.rol_usuario = rol_guardado
        vista_login.visible = False
        vista_dashboard.visible = True

        if page.rol_usuario == "vendedor":
            seccion_pos.visible = True
            vista_inventario.visible = False
            panel_reportes.visible = False

        for boton in menu_lateral.content.controls:
            if hasattr(boton, 'data') and boton.data in ["Inventario", "Reportes"]:
                boton.visible = (page.rol_usuario == "admin")
    else:
        vista_login.visible = True
        vista_dashboard.visible = False

    page.add(vista_login, vista_dashboard)

ft.app(target=main, view=ft.WEB_BROWSER, assets_dir="assets", port=int(os.getenv("PORT", 8080)))