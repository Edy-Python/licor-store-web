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
    cursor = conn.cursor(buffered=True)
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
    page.bgcolor = "#F8FAFC"

    estilo_tarjeta = {
        "padding": 25,
        "bgcolor": ft.colors.WHITE,
        "border_radius": 16,
        "shadow": ft.BoxShadow(
            spread_radius=0, 
            blur_radius=25,
            color=ft.colors.with_opacity(0.04, ft.colors.BLACK), 
            offset=ft.Offset(0, 8)
        ),
        "border": ft.border.all(1, "#E2E8F0")
    }

    accion_guardada = [None] 
    
    input_pass_seguridad = ft.TextField(
        label="Contraseña de Administrador", 
        password=True, 
        can_reveal_password=True,
        on_submit=lambda e: confirmar_seguridad(e)
    )
    
    def confirmar_seguridad(e):
        password = input_pass_seguridad.value or ""
        hash_ingresado = hashlib.sha256(password.encode()).hexdigest()
        
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT id FROM usuarios WHERE TRIM(LOWER(rol)) = 'admin' AND password_hash = %s", (hash_ingresado,))
                es_admin = cursor.fetchone()
        except Exception as ex:
            print(f"Error técnico en seguridad: {ex}")
            es_admin = False
    
        if es_admin:
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
        
        if len(busqueda) < 2:
            lista_resultados.controls.clear()
            lista_resultados.visible = False
            page.update()
            return
            
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT DISTINCT nombre FROM productos WHERE nombre LIKE %s LIMIT 50", (f"%{busqueda}%",))
                resultados = cursor.fetchall()  
            if input_buscar.value.strip() != busqueda:
                return
            lista_resultados.controls.clear()
            if resultados:
                lista_resultados.visible = True
                for fila in resultados:
                    nombre_limpio = str(fila[0]).strip()
                    lista_resultados.controls.append(ft.ListTile(title=ft.Text(nombre_limpio), on_click=lambda e, n=nombre_limpio: seleccionar_autocompletado(n)))
            else:
                lista_resultados.visible = False
            page.update()
        except Exception as ex:
            print(f"Error en búsqueda dinámica: {ex}")

    surtidor_items = []
    surtidor_estado = {"requeridas": 0, "seleccionadas": 0, "precio_u_pen": 0.0, "precio_u_usd": 0.0, "empaque_base": ""}

    def actualizar_contador_surtidor():
        total = sum(item["cant"] for item in surtidor_items)
        surtidor_estado["seleccionadas"] = total
        lbl_contador_surtidor.value = f"Seleccionadas: {total} / {surtidor_estado['requeridas']}"
        lbl_contador_surtidor.color = ft.colors.GREEN if total == surtidor_estado["requeridas"] else ft.colors.RED
        btn_confirmar_surtidor.disabled = (total != surtidor_estado["requeridas"])
        page.update()

    def cambiar_cant_surtidor(item, delta):
        nueva_cant = item["cant"] + delta
        if 0 <= nueva_cant <= item["stock"]:
            if delta > 0 and surtidor_estado["seleccionadas"] >= surtidor_estado["requeridas"]: return
            item["cant"] = nueva_cant
            item["text_cant"].value = str(nueva_cant)
            actualizar_contador_surtidor()

    lbl_contador_surtidor = ft.Text("Seleccionadas: 0 / 0", size=18, weight=ft.FontWeight.BOLD)
    lista_surtidor_ui = ft.Column(scroll=ft.ScrollMode.AUTO, height=250)

    def confirmar_surtidor(e):
        for item in surtidor_items:
            if item["cant"] > 0:
                sub_pen = item["cant"] * surtidor_estado["precio_u_pen"]
                sub_usd = item["cant"] * surtidor_estado["precio_u_usd"]
                
                id_formateado = str(item["id"]).zfill(3)
                emp_mix = f"Mix {surtidor_estado['empaque_base'][:3]}"
                
                nueva_fila = ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(id_formateado), width=30)),
                    ft.DataCell(ft.Container(content=ft.Text(str(item["nombre"]), size=12, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS), width=170)),
                    ft.DataCell(ft.Text(str(item["pres"]))),
                    ft.DataCell(ft.Text(emp_mix)),
                    ft.DataCell(ft.Text(str(item["cant"]))),
                    ft.DataCell(ft.Text(f"{surtidor_estado['precio_u_pen']:.2f}")),
                    ft.DataCell(ft.Text(f"{sub_pen:.2f}")),
                    ft.DataCell(ft.Text(f"{sub_usd:.2f}"))
                ])
                
                def accion_borrar_carrito(e):
                    fila = e.control.data
                    if fila in tabla_carrito.rows:
                        tabla_carrito.rows.remove(fila)
                        tabla_carrito.update()
                        actualizar_totales()

                btn_eliminar = ft.IconButton(icon=ft.icons.DELETE, icon_color=ft.colors.RED, data=nueva_fila, on_click=accion_borrar_carrito)
                nueva_fila.cells.append(ft.DataCell(btn_eliminar))
                tabla_carrito.rows.append(nueva_fila)
                
        tabla_carrito.update()
        actualizar_totales()
        page.close(dialogo_surtidor)

    btn_confirmar_surtidor = ft.ElevatedButton("Confirmar Combo", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=confirmar_surtidor)

    dialogo_surtidor = ft.AlertDialog(
        title=ft.Text("Armar Combo Surtido", weight=ft.FontWeight.BOLD),
        content=ft.Container(
            width=450,
            content=ft.Column([
                ft.Text("Selecciona los sabores para completar el empaque:", size=13, color=ft.colors.GREY_700),
                lbl_contador_surtidor,
                ft.Divider(),
                lista_surtidor_ui
            ], tight=True)
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: page.close(dialogo_surtidor)),
            btn_confirmar_surtidor
        ]
    )

    def agregar_producto(e):
        busqueda = input_buscar.value.strip()
        if not busqueda: return
        
        cant_ingresada = int(input_cantidad.value) if input_cantidad.value and input_cantidad.value.isdigit() else 1
        
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT id_producto, nombre, presentacion, 
                           precio_uni_pen, precio_uni_usd, precio_six_pen, precio_six_usd, 
                           precio_caja_pen, precio_caja_usd, precio_plancha_pen, precio_plancha_usd,
                           grupo_surtido
                    FROM productos WHERE id_producto = %s OR nombre = %s LIMIT 1
                """, (busqueda if busqueda.isdigit() else 0, busqueda))
                producto = cursor.fetchone()

            if producto:
                (id_prod, nombre, pres, p_uni_pen, p_uni_usd, p_six_pen, p_six_usd, p_caja_pen, p_caja_usd, p_plan_pen, p_plan_usd, grupo_sur) = producto
                
                moneda = dropdown_moneda.value
                empaque = dropdown_empaque.value
                if grupo_sur and empaque != "Unidad":
                    multiplicadores = {"Six-pack": 6, "Caja": 12, "Plancha": 24}
                    unidades_requeridas = multiplicadores[empaque] * cant_ingresada
                    
                    precio_total_pen = (p_six_pen if empaque=="Six-pack" else (p_caja_pen if empaque=="Caja" else p_plan_pen)) * cant_ingresada
                    precio_total_usd = (p_six_usd if empaque=="Six-pack" else (p_caja_usd if empaque=="Caja" else p_plan_usd)) * cant_ingresada
                    
                    if input_precio_esp.value:
                        try:
                            precio_total_pen = float(input_precio_esp.value) * cant_ingresada
                            precio_total_usd = float(input_precio_esp.value) * cant_ingresada
                        except ValueError: pass

                    surtidor_estado["requeridas"] = unidades_requeridas
                    surtidor_estado["seleccionadas"] = 0
                    surtidor_estado["precio_u_pen"] = precio_total_pen / unidades_requeridas if moneda == "PEN" else 0.00
                    surtidor_estado["precio_u_usd"] = precio_total_usd / unidades_requeridas if moneda == "USD" else 0.00
                    surtidor_estado["empaque_base"] = empaque
                    
                    with obtener_cursor() as cursor2:
                        cursor2.execute("SELECT id_producto, nombre, presentacion, stock FROM productos WHERE grupo_surtido = %s", (grupo_sur,))
                        hermanos = cursor2.fetchall()
                        
                    surtidor_items.clear()
                    lista_surtidor_ui.controls.clear()
                    
                    for h in hermanos:
                        item_dict = {"id": h[0], "nombre": h[1], "pres": h[2], "stock": int(h[3]), "cant": 0, "text_cant": ft.Text("0", size=16, weight=ft.FontWeight.BOLD)}
                        surtidor_items.append(item_dict)
                        
                        btn_menos = ft.IconButton(ft.icons.REMOVE_CIRCLE, icon_color=ft.colors.RED, on_click=lambda e, i=item_dict: cambiar_cant_surtidor(i, -1))
                        btn_mas = ft.IconButton(ft.icons.ADD_CIRCLE, icon_color=ft.colors.GREEN, on_click=lambda e, i=item_dict: cambiar_cant_surtidor(i, 1))
                        
                        fila_ui = ft.Row([
                            ft.Container(content=ft.Text(f"{h[1]} ({h[2]})\nStock: {h[3]}", size=12), width=230),
                            btn_menos, item_dict["text_cant"], btn_mas
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                        lista_surtidor_ui.controls.append(fila_ui)
                    
                    actualizar_contador_surtidor()
                    page.open(dialogo_surtidor)
                    
                    input_buscar.value = ""; input_cantidad.value = "1"; input_precio_esp.value = ""; lista_resultados.visible = False
                    return

                precio_final = 0.00
                if empaque == "Unidad": precio_final = p_uni_pen if moneda == "PEN" else p_uni_usd
                elif empaque == "Pack-4": precio_final = (p_uni_pen * 4) if moneda == "PEN" else (p_uni_usd * 4)
                elif empaque == "Six-pack": precio_final = p_six_pen if moneda == "PEN" else p_six_usd
                elif empaque == "Caja": precio_final = p_caja_pen if moneda == "PEN" else p_caja_usd
                elif empaque == "Pack-15": precio_final = (p_uni_pen * 15) if moneda == "PEN" else (p_uni_usd * 15)
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
                    ft.DataCell(ft.Container(content=ft.Text(str(nombre), size=12, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS), width=170)),
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
                # 1. Traer nombre de la empresa
                cursor.execute("SELECT nombre_negocio FROM configuracion LIMIT 1")
                conf = cursor.fetchone()
                c_nom_emp = conf[0] if conf else "LICOR STORE"

                cursor.execute("SELECT fecha_emision, hora_emision, vendedor, cliente_nombre, cliente_dni, cliente_direccion, total_pen, total_usd, metodo_pago, monto_efectivo, monto_yape, monto_plin, monto_tarjeta, vuelto FROM ventas WHERE id_venta = %s", (id_venta_reciente,))
                cabecera = cursor.fetchone()

                cursor.execute("""
                    SELECT d.cantidad, d.tipo_empaque, p.nombre, d.precio_unitario, d.subtotal_pen, d.subtotal_usd, p.grupo_surtido, p.presentacion 
                    FROM detalles_venta d 
                    JOIN productos p ON d.id_producto = p.id_producto 
                    WHERE d.id_venta = %s
                """, (id_venta_reciente,))
                detalles_db = cursor.fetchall()

            detalles = []
            mixes_agrupados = {}
            
            for det in detalles_db:
                cant, emp, nom, pu, sub_pen, sub_usd, grupo, pres = det
                if str(emp).startswith("Mix ") and grupo:
                    clave = (grupo, emp, pres)
                    if clave not in mixes_agrupados:
                        mixes_agrupados[clave] = {"cant": 0, "sub_pen": 0.0, "sub_usd": 0.0}
                    mixes_agrupados[clave]["cant"] += cant
                    mixes_agrupados[clave]["sub_pen"] += float(sub_pen)
                    mixes_agrupados[clave]["sub_usd"] += float(sub_usd)
                else:
                    detalles.append([cant, emp, nom, pu, sub_pen, sub_usd])
            
            for clave, data in mixes_agrupados.items():
                grupo, emp, pres = clave
                divisor = 6 if emp == "Mix Six" else (12 if emp == "Mix Caj" else 24)
                emp_real = "Six-pack" if emp == "Mix Six" else ("Caja" if emp == "Mix Caj" else "Plancha")
                cant_real = data["cant"] // divisor
                
                if cant_real > 0:
                    nombre_consolidado = f"{grupo} SURTIDO {pres}"
                    pu_real = data["sub_pen"] / cant_real
                    detalles.append([cant_real, emp_real, nombre_consolidado, pu_real, data["sub_pen"], data["sub_usd"]])

            if not cabecera:
                raise ValueError(f"No se encontró la venta con id {id_venta_reciente}.")

            f_emision, h_emision, vendedor, c_nombre, c_dni, c_dir, t_pen, t_usd, m_pago, m_efec, m_yape, m_plin, m_tarj, vuelto = cabecera
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
                elementos_finales.append(ft.Divider(color=ft.colors.GREY_300))
                elementos_finales.append(ft.Row([ft.Text("Método de Pago:", size=11, weight=ft.FontWeight.BOLD), ft.Text(str(m_pago), size=11)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
            
                
                if m_efec > 0: elementos_finales.append(ft.Row([ft.Text("Efectivo:", size=11), ft.Text(f"S/ {m_efec:.2f}", size=11)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
                total_yape_plin = m_yape + m_plin
                if m_efec > 0: elementos_finales.append(ft.Row([ft.Text("Efectivo:", size=11), ft.Text(f"S/ {m_efec:.2f}", size=11)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
                if total_yape_plin > 0: elementos_finales.append(ft.Row([ft.Text("Yape/Plin:", size=11), ft.Text(f"S/ {total_yape_plin:.2f}", size=11)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
                if m_tarj > 0: elementos_finales.append(ft.Row([ft.Text("Tarjeta:", size=11), ft.Text(f"S/ {m_tarj:.2f}", size=11)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
            
                if vuelto > 0:
                   elementos_finales.append(ft.Row([ft.Text("Vuelto:", size=12, weight=ft.FontWeight.BOLD), ft.Text(f"S/ {vuelto:.2f}", size=12, weight=ft.FontWeight.BOLD, color=ft.colors.RED)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
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
                        ft.Text(str(c_nom_emp).upper(), size=18, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_900),
                        ft.Text("NOTA DE VENTA", size=14, weight=ft.FontWeight.BOLD),
                        ft.Text(codigo_ticket, size=14),
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

    input_pago_efectivo = ft.TextField(label="Efectivo (S/)", value="0.00", col={"sm": 12, "md": 4})
    input_pago_yape_plin = ft.TextField(label="Yape / Plin (S/)", value="0.00", col={"sm": 12, "md": 4})
    input_pago_tarjeta = ft.TextField(label="Tarjeta (S/)", value="0.00", col={"sm": 12, "md": 4})
    
    lbl_resumen_cobro = ft.Text("Total a cobrar: S/ 0.00", size=18, weight=ft.FontWeight.BOLD)
    lbl_vuelto = ft.Text("Faltante: S/ 0.00", size=18, weight=ft.FontWeight.BOLD, color=ft.colors.RED)

    def calcular_vuelto(e=None):
        try:
            t_pen = sum(float(row.cells[6].content.value) for row in tabla_carrito.rows)
            ef = float(input_pago_efectivo.value) if input_pago_efectivo.value else 0.0
            yp = float(input_pago_yape_plin.value) if input_pago_yape_plin.value else 0.0
            ta = float(input_pago_tarjeta.value) if input_pago_tarjeta.value else 0.0
            
            total_pagado = ef + yp + ta
            diferencia = total_pagado - t_pen
            
            if diferencia < 0:
                lbl_vuelto.value = f"Faltante: S/ {abs(diferencia):.2f}"
                lbl_vuelto.color = ft.colors.RED
            else:
                lbl_vuelto.value = f"Vuelto: S/ {diferencia:.2f}"
                lbl_vuelto.color = ft.colors.GREEN
            page.update()
        except ValueError:
            pass

    input_pago_efectivo.on_change = calcular_vuelto
    input_pago_yape_plin.on_change = calcular_vuelto
    input_pago_tarjeta.on_change = calcular_vuelto

    def confirmar_y_guardar_venta(e):
        # PROTECCIÓN ANTI DOBLE-CLIC
        e.control.disabled = True
        e.control.text = "Procesando..."
        page.update()

        try:
            t_pen = sum(float(row.cells[6].content.value) for row in tabla_carrito.rows)
            ef = float(input_pago_efectivo.value) if input_pago_efectivo.value else 0.0
            yp = float(input_pago_yape_plin.value) if input_pago_yape_plin.value else 0.0
            ta = float(input_pago_tarjeta.value) if input_pago_tarjeta.value else 0.0
            
            total_pagado = ef + yp + ta
            if total_pagado < t_pen:
                page.open(ft.SnackBar(ft.Text("❌ El monto pagado no cubre el total.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
                return
                
            # CORRECCIÓN DE PAGO MIXTO DEL INFORME
            if (yp + ta) > t_pen:
                page.open(ft.SnackBar(ft.Text("❌ Yape o Tarjeta no pueden exceder el total del ticket.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
                return

            vuelto = total_pagado - t_pen if ef > 0 else 0.0 
            pagos = {"Efectivo": ef, "Yape/Plin": yp, "Tarjeta": ta}
            activos = [k for k, v in pagos.items() if v > 0]
            metodo_principal = "Mixto" if len(activos) > 1 else (activos[0] if activos else "Efectivo")

            conn = conectar_db()
            cursor = conn.cursor(buffered=True)
            multiplicadores = {"Unidad": 1, "Pack-4": 4, "Six-pack": 6, "Caja": 12, "Pack-15": 15, "Plancha": 24, "Mix Six": 1, "Mix Caj": 1, "Mix Pla": 1}

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

                if not resultado or resultado[1] < descuento_stock:
                    conn.rollback()
                    page.open(ft.SnackBar(ft.Text("⛔ Stock insuficiente para procesar la venta.", color=ft.colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.colors.RED))
                    return

                items.append((id_prod, empaque, cant, p_unit, sub_pen, sub_usd, descuento_stock))

            cursor.execute("SELECT COUNT(*) FROM ventas")
            total_registros = cursor.fetchone()[0]
            codigo_ticket = f"NV-{total_registros + 1:08d}"

            ahora_local = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5)))
            fecha_actual = ahora_local.date()
            hora_actual = ahora_local.time()
            
            rol_actual = page.rol_usuario.upper() if hasattr(page, 'rol_usuario') and page.rol_usuario else "ADMIN"
            vendedor_actual = "CRISTHIAN" if rol_actual == "ADMIN" else ("YOSELIN" if rol_actual == "VENDEDOR" else rol_actual)
                
            obs = input_observacion.value.strip() if input_observacion.value else ""
            t_usd = sum(item[5] for item in items)
            cursor.execute("""
                INSERT INTO ventas (codigo_ticket, fecha_emision, hora_emision, vendedor, cliente_nombre, cliente_dni, cliente_direccion, total_pen, total_usd, observaciones, metodo_pago, monto_efectivo, monto_yape, monto_plin, monto_tarjeta, vuelto)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (codigo_ticket, fecha_actual, hora_actual, vendedor_actual, input_cliente.value, input_dni.value, input_direccion.value, t_pen, t_usd, obs, metodo_principal, ef, yp, 0.0, ta, vuelto))
            
            id_venta = cursor.lastrowid

            for id_prod, empaque, cant, p_unit, sub_pen, sub_usd, descuento_stock in items:
                cursor.execute("INSERT INTO detalles_venta (id_venta, id_producto, tipo_empaque, cantidad, precio_unitario, subtotal_pen, subtotal_usd) VALUES (%s, %s, %s, %s, %s, %s, %s)", (id_venta, id_prod, empaque, cant, p_unit, sub_pen, sub_usd))
                cursor.execute("UPDATE productos SET stock = stock - %s WHERE id_producto = %s", (descuento_stock, id_prod))

            conn.commit()
            cursor.close()

            tabla_carrito.rows.clear()
            input_dni.value = ""
            input_cliente.value = ""
            input_observacion.value = ""
            actualizar_totales()
            page.close(dialogo_cobro)

            def cerrar_alerta_venta(e): page.close(alerta_venta)

            alerta_venta = ft.AlertDialog(
                title=ft.Text("¡Venta Realizada!", color=ft.colors.GREEN, weight=ft.FontWeight.BOLD),
                content=ft.Text(f"Ticket generado: {codigo_ticket}\nEl stock se descontó correctamente.", size=16),
                actions=[
                    ft.TextButton("Ver Nota de Venta", on_click=lambda e, id_v=id_venta, cod=codigo_ticket: ver_nota_venta(id_v, cod)),
                    ft.ElevatedButton("Aceptar", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=cerrar_alerta_venta)
                ]
            )
            page.open(alerta_venta)

        except Exception as ex:
            if 'conn' in locals(): conn.rollback()
            print(f"Error procesando: {ex}")
            page.open(ft.SnackBar(ft.Text("Error de base de datos.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
        finally:
            if 'conn' in locals(): conn.close()
            e.control.disabled = False
            e.control.text = "Confirmar Venta"
            page.update()

    dialogo_cobro = ft.AlertDialog(
        title=ft.Text("Procesar Cobro", weight=ft.FontWeight.BOLD),
        content=ft.Container(
            width=500,
            content=ft.Column([
                lbl_resumen_cobro,
                ft.Divider(),
                ft.Text("Ingrese los montos recibidos:", size=14, color=ft.colors.GREY_700),
                ft.ResponsiveRow([input_pago_efectivo, input_pago_yape_plin, input_pago_tarjeta]),
                ft.Divider(),
                lbl_vuelto
            ], tight=True)
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: page.close(dialogo_cobro)),
            ft.ElevatedButton("Confirmar Venta", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=confirmar_y_guardar_venta)
        ]
    )

    def procesar_venta(e):
        if not tabla_carrito.rows:
            page.open(ft.SnackBar(ft.Text("⛔ El carrito está vacío.", color=ft.colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.colors.RED))
            return
        
        t_pen = sum(float(row.cells[6].content.value) for row in tabla_carrito.rows)
        lbl_resumen_cobro.value = f"Total a cobrar: S/ {t_pen:.2f}"
        input_pago_efectivo.value = f"{t_pen:.2f}" 
        input_pago_yape_plin.value = "0.00"
        input_pago_tarjeta.value = "0.00"
        calcular_vuelto()
        page.open(dialogo_cobro)

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
            ft.DataColumn(ft.Text("Costo (S/)", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Costo ($)", weight=ft.FontWeight.BOLD)),
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
                SELECT nombre, presentacion, categoria, costo, costo_usd,
                       precio_uni_pen, precio_uni_usd, 
                       precio_six_pen, precio_six_usd, 
                       precio_caja_pen, precio_caja_usd, 
                       precio_plancha_pen, precio_plancha_usd,
                       grupo_surtido
                FROM productos WHERE id_producto = %s
            """, (id_prod,))
                datos = cursor.fetchone()

            if not datos: return
            (n, pres, cat, costo_compra, costo_usd_compra, pu_pen, pu_usd, ps_pen, ps_usd, pc_pen, pc_usd, pp_pen, pp_usd, grupo_sur) = datos

        except Exception as e:
            page.open(ft.SnackBar(ft.Text("No se pudo cargar el producto.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            return

        input_nom = ft.TextField(label="Nombre del Producto", value=str(n), col={"sm": 12, "md": 12})
        input_pres = ft.TextField(label="Presentación", value=str(pres), col={"sm": 12, "md": 4})
        drop_cat_edit = ft.Dropdown(label="Categoría", options=[ft.dropdown.Option(c) for c in opciones_cat], value=str(cat) if cat else "LICOR", col={"sm": 12, "md": 4})
        
        inp_costo_edit = ft.TextField(label="Costo (S/)", value=f"{costo_compra:.2f}" if costo_compra else "0.00", col={"sm": 6, "md": 2})
        inp_costo_usd_edit = ft.TextField(label="Costo ($)", value=f"{costo_usd_compra:.2f}" if costo_usd_compra else "0.00", col={"sm": 6, "md": 2})
        
        inp_grupo_edit = ft.TextField(label="Grupo Surtido", value=str(grupo_sur) if grupo_sur else "", hint_text="Ej: MIKES", col={"sm": 12, "md": 12})
        
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
                with obtener_cursor(commit=True) as cursor:
                    cursor.execute("""
                        UPDATE productos SET 
                            nombre = %s, presentacion = %s, categoria = %s, costo = %s, costo_usd = %s,
                            precio_uni_pen = %s, precio_uni_usd = %s,
                            precio_six_pen = %s, precio_six_usd = %s,
                            precio_caja_pen = %s, precio_caja_usd = %s,
                            precio_plancha_pen = %s, precio_plancha_usd = %s,
                            grupo_surtido = %s
                        WHERE id_producto = %s
                    """, (
                        input_nom.value.strip(), input_pres.value.strip(), drop_cat_edit.value, 
                        float(inp_costo_edit.value) if inp_costo_edit.value else 0.0,
                        float(inp_costo_usd_edit.value) if inp_costo_usd_edit.value else 0.0,
                        float(inp_pu_pen.value) if inp_pu_pen.value else 0.0, float(inp_pu_usd.value) if inp_pu_usd.value else 0.0,
                        float(inp_ps_pen.value) if inp_ps_pen.value else 0.0, float(inp_ps_usd.value) if inp_ps_usd.value else 0.0,
                        float(inp_pc_pen.value) if inp_pc_pen.value else 0.0, float(inp_pc_usd.value) if inp_pc_usd.value else 0.0,
                        float(inp_pp_pen.value) if inp_pp_pen.value else 0.0, float(inp_pp_usd.value) if inp_pp_usd.value else 0.0,
                        inp_grupo_edit.value.strip().upper(), id_prod
                    ))
                page.close(dialogo_editar)
                cargar_datos_inventario()
                page.open(ft.SnackBar(ft.Text("✅ Producto actualizado", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
            except Exception as ex:
                page.open(ft.SnackBar(ft.Text(f"❌ Error al guardar: {ex}", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
                
        dialogo_editar = ft.AlertDialog(
            title=ft.Text("Modificar Producto", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=650, 
                content=ft.Column([
                    ft.Container(height=10),
                    ft.ResponsiveRow([input_nom]),
                    ft.ResponsiveRow([input_pres, drop_cat_edit, inp_costo_edit, inp_costo_usd_edit]),
                    ft.ResponsiveRow([inp_grupo_edit]),
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
            
            query = "SELECT id_producto, nombre, presentacion, stock, costo, costo_usd, precio_uni_pen, precio_caja_pen FROM productos WHERE 1=1"
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
                stock_actual = int(fila[3])
                costo_pen = float(fila[4]) if fila[4] else 0.00
                costo_usd = float(fila[5]) if fila[5] else 0.00
                p_uni = float(fila[6]) if fila[6] else 0.00
                p_caja = float(fila[7]) if fila[7] else 0.00
                
                if stock_actual <= 0:
                    color_alerta = ft.colors.RED
                    icono_alerta = ft.icons.ERROR
                elif stock_actual <= 30:
                    color_alerta = ft.colors.ORANGE_700
                    icono_alerta = ft.icons.WARNING
                else:
                    color_alerta = ft.colors.BLACK
                    icono_alerta = None
                
                if icono_alerta:
                    celda_stock = ft.Row([ft.Icon(icono_alerta, color=color_alerta, size=16), ft.Text(str(stock_actual), color=color_alerta, weight=ft.FontWeight.BOLD)])
                else:
                    celda_stock = ft.Text(str(stock_actual), color=color_alerta)
                
                btn_editar = ft.IconButton(ft.icons.EDIT, icon_color=ft.colors.BLUE, on_click=lambda e, i=id_real: solicitar_password(lambda: abrir_edicion(i)))
                btn_borrar = ft.IconButton(ft.icons.DELETE, icon_color=ft.colors.RED, on_click=lambda e, i=id_real, n=nombre_prod: solicitar_password(lambda: confirmar_eliminacion(i, n)))
                
                tabla_inventario.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(correlativo), color=color_alerta)), 
                    ft.DataCell(ft.Text(nombre_prod, color=color_alerta, weight=ft.FontWeight.BOLD if stock_actual <= 0 else ft.FontWeight.NORMAL)), 
                    ft.DataCell(ft.Text(str(fila[2]), color=color_alerta)),
                    ft.DataCell(celda_stock), 
                    ft.DataCell(ft.Text(f"{costo_pen:.2f}", color=ft.colors.RED_700, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(f"{costo_usd:.2f}", color=ft.colors.RED_700, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(f"{p_uni:.2f}", color=color_alerta)), 
                    ft.DataCell(ft.Text(f"{p_caja:.2f}", color=color_alerta)),
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
        panel_cajas.visible = False
        panel_configuracion.visible = False
        
        nombre_boton = e.control.data
        
        if nombre_boton == "Ventas":
            seccion_pos.visible = True
        elif nombre_boton == "Inventario":
            vista_inventario.visible = True
            cargar_datos_inventario()
        elif nombre_boton == "Reportes":
            panel_reportes.visible = True
            cargar_ventas_diarias()
            cargar_auditoria_y_utilidad()
        elif nombre_boton == "Cajas":
            panel_cajas.visible = True
            input_fecha_caja.value = str(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).date())
            cargar_datos_cajas()
        elif nombre_boton == "Configuración":
            panel_configuracion.visible = True
            cargar_datos_negocio()
            cargar_usuarios()
            
        page.update()

    def toggle_menu(e):
        menu_lateral.visible = not menu_lateral.visible
        page.update()

    def crear_boton_menu(texto, icono, funcion_click, es_peligro=False):
        color_icono = ft.colors.RED_400 if es_peligro else "#94A3B8"
        color_texto = ft.colors.RED_400 if es_peligro else "#F8FAFC"

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icono, color=color_icono, size=22),
                    ft.Text(texto, color=color_texto, weight=ft.FontWeight.W_500, size=15),
                ],
                spacing=15,
            ),
            padding=ft.padding.symmetric(horizontal=15, vertical=12), 
            border_radius=10,
            ink=True,       
            data=texto,        
            on_click=funcion_click,
        )

    menu_lateral = ft.Container(
        width=240,
        bgcolor="#1E293B",
        padding=20, 
        border_radius=ft.border_radius.only(top_right=20, bottom_right=20),
        shadow=ft.BoxShadow(blur_radius=15, color=ft.colors.with_opacity(0.1, ft.colors.BLACK), offset=ft.Offset(5, 0)),
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.icons.LOCAL_BAR, color="#38BDF8", size=28),
                    ft.Text("LIKIO STORE", color="#F8FAFC", weight=ft.FontWeight.BOLD, size=20)
                ]),
                margin=ft.margin.only(bottom=10)
            ),
            ft.Divider(color="#334155", height=20),
            
            crear_boton_menu("Ventas", ft.icons.POINT_OF_SALE_ROUNDED, cambiar_vista),
            crear_boton_menu("Cajas", ft.icons.ACCOUNT_BALANCE_WALLET_ROUNDED, cambiar_vista),
            crear_boton_menu("Inventario", ft.icons.INVENTORY_2_ROUNDED, cambiar_vista),
            crear_boton_menu("Reportes", ft.icons.INSERT_CHART_ROUNDED, cambiar_vista),
            crear_boton_menu("Configuración", ft.icons.SETTINGS_ROUNDED, cambiar_vista),
            
            ft.Divider(color="#334155", height=20),
            crear_boton_menu("Cerrar Sesión", ft.icons.EXIT_TO_APP_ROUNDED, cerrar_sesion, es_peligro=True)
        ], spacing=5)
    )

    def buscar_cliente_historial(e):
        dni = input_dni.value.strip()
        if len(dni) >= 8:
            try:
                with obtener_cursor() as cursor:
                    cursor.execute("SELECT cliente_nombre, cliente_direccion FROM ventas WHERE cliente_dni = %s AND cliente_nombre != 'VARIOS' AND cliente_nombre != '' ORDER BY id_venta DESC LIMIT 1", (dni,))
                    cliente = cursor.fetchone()
                    if cliente:
                        input_cliente.value = cliente[0]
                        input_direccion.value = cliente[1]
                        page.update()
            except Exception as ex: print(f"Error cliente: {ex}")

    estilo_input = {"border_color": "#CBD5E1", "focused_border_color": "#2563EB", "border_radius": 8}

    input_dni = ft.TextField(label="DNI/RUC", hint_text="00000000", col={"sm": 12, "md": 4, "lg": 3}, on_change=buscar_cliente_historial, **estilo_input)
    input_cliente = ft.TextField(label="Cliente", hint_text="Varios", col={"sm": 12, "md": 8, "lg": 5}, **estilo_input)
    input_direccion = ft.TextField(label="Dirección", value="Tacna", col={"sm": 12, "md": 12, "lg": 4}, **estilo_input)
    
    dropdown_empaque = ft.Dropdown(
        label="Empaque", options=[
            ft.dropdown.Option("Unidad"), 
            ft.dropdown.Option("Pack-4"), 
            ft.dropdown.Option("Six-pack"), 
            ft.dropdown.Option("Caja"), 
            ft.dropdown.Option("Pack-15"), 
            ft.dropdown.Option("Plancha")
        ],
        value="Unidad", col={"sm": 6, "md": 3, "lg": 3}, **estilo_input
    )
    
    input_cantidad = ft.TextField(label="Cant.", value="1", keyboard_type=ft.KeyboardType.NUMBER, col={"sm": 3, "md": 2, "lg": 2}, on_submit=agregar_producto, **estilo_input)
    input_precio_esp = ft.TextField(label="P. Esp.", hint_text="Opcional", keyboard_type=ft.KeyboardType.NUMBER, col={"sm": 3, "md": 2, "lg": 2}, on_submit=agregar_producto, **estilo_input)
    dropdown_moneda = ft.Dropdown(label="Moneda", options=[ft.dropdown.Option("PEN"), ft.dropdown.Option("USD")], value="PEN", col={"sm": 4, "md": 2, "lg": 2}, **estilo_input)
    
    btn_agregar = ft.ElevatedButton("Agregar", icon=ft.icons.ADD_SHOPPING_CART, style=ft.ButtonStyle(color=ft.colors.WHITE, bgcolor="#10B981", shape=ft.RoundedRectangleBorder(radius=8)), height=50, on_click=agregar_producto, col={"sm": 8, "md": 3, "lg": 3})
    
    input_observacion = ft.TextField(label="Comentarios de la venta (Opcional)", col={"sm": 12}, **estilo_input)

    lbl_total_pen = ft.Text("S/ 0.00", size=32, weight=ft.FontWeight.W_800, color="#059669") 
    lbl_total_usd = ft.Text("$ 0.00", size=24, weight=ft.FontWeight.BOLD, color="#64748B") 
    
    tabla_carrito = ft.DataTable(
        column_spacing=20, 
        heading_row_color="#F1F5F9", 
        border_radius=8,
        border=ft.border.all(1, "#E2E8F0"),
        data_row_max_height=65,
        columns=[
            ft.DataColumn(ft.Container(ft.Text("ID", color="#475569"), width=30)), 
            ft.DataColumn(ft.Container(ft.Text("Descripción", color="#475569"), width=150)), 
            ft.DataColumn(ft.Text("Pres.", color="#475569")),
            ft.DataColumn(ft.Text("Tipo", color="#475569")),
            ft.DataColumn(ft.Text("Cant.", color="#475569")),
            ft.DataColumn(ft.Text("P. Unit", color="#475569")),
            ft.DataColumn(ft.Text("Sub (S/)", color="#475569")),
            ft.DataColumn(ft.Text("Sub ($)", color="#475569")), 
            ft.DataColumn(ft.Text("Acción", color="#475569")), 
        ],
        rows=[]
    )

    lista_resultados = ft.ListView(spacing=2, padding=5, visible=False, height=150)
    
    def limpiar_busqueda(e):
        input_buscar.value = ""
        lista_resultados.visible = False
        page.update()

    input_buscar = ft.TextField(
        label="Buscar Producto", hint_text="Nombre o ID...", 
        on_change=buscar_dinamico, on_submit=agregar_producto, 
        col={"sm": 12, "md": 12, "lg": 12}, prefix_icon=ft.icons.SEARCH, 
        suffix=ft.IconButton(ft.icons.CLEAR, on_click=limpiar_busqueda),
        **estilo_input
    )

    panel_izquierdo = ft.Container(
        **estilo_tarjeta,
        content=ft.Column([
            ft.Text("Terminal de Ventas", size=22, weight=ft.FontWeight.W_700, color="#1E293B"),
            ft.Divider(color="#E2E8F0", height=20),
            ft.ResponsiveRow([input_dni, input_cliente, input_direccion]), 
            ft.Divider(color="#E2E8F0", height=20),
            ft.ResponsiveRow([input_buscar]),
            lista_resultados,
            ft.ResponsiveRow([dropdown_empaque, input_cantidad, input_precio_esp, dropdown_moneda, btn_agregar], alignment=ft.MainAxisAlignment.START),
            ft.Container(content=ft.Column([tabla_carrito], scroll=ft.ScrollMode.AUTO)), 
            ft.ResponsiveRow([input_observacion])
        ]) 
    )

    panel_derecho = ft.Container(
        **estilo_tarjeta,
        content=ft.Column([
            ft.Text("Resumen", size=18, weight=ft.FontWeight.W_700, color="#1E293B"),
            ft.Divider(color="#E2E8F0"),
            ft.Text("Subtotal (S/):", size=13, color="#64748B"),
            lbl_total_pen,
            ft.Container(height=10),
            ft.Text("Subtotal ($):", size=13, color="#64748B"),
            lbl_total_usd,
            ft.Divider(color="#E2E8F0"),
            ft.ElevatedButton("Cobrar Ticket", icon=ft.icons.PAYMENTS, style=ft.ButtonStyle(bgcolor="#3B82F6", color=ft.colors.WHITE, shape=ft.RoundedRectangleBorder(radius=10)), width=float('inf'), height=55, on_click=procesar_venta)
        ], spacing=5)
    )
    
    seccion_pos = ft.Container(
        padding=20, 
        content=ft.ResponsiveRow([
            ft.Column([panel_izquierdo], col={"sm": 12, "md": 12, "lg": 8, "xl": 9}),
            ft.Column([panel_derecho], col={"sm": 12, "md": 12, "lg": 4, "xl": 3})
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
    input_stock_prod = ft.TextField(label="Stock Inicial", value="0", col={"sm": 12, "md": 3})
    input_costo_prod = ft.TextField(label="Costo (S/)", value="0.00", col={"sm": 6, "md": 3})
    input_costo_usd_prod = ft.TextField(label="Costo ($)", value="0.00", col={"sm": 6, "md": 3})
    input_grupo_prod = ft.TextField(label="Grupo Surtido", hint_text="Ej: MIKES (Opcional)", col={"sm": 12, "md": 3})
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
        grupo_ingresado = input_grupo_prod.value.strip().upper()
        
        if not nombre:
            page.open(ft.SnackBar(ft.Text("El nombre es obligatorio"), bgcolor=ft.colors.RED))
            boton.text = "Guardar"; boton.disabled = False; page.update()
            return

        try:
            stock_ingresado = int(input_stock_prod.value) if input_stock_prod.value.isdigit() else 0
            costo_ingresado = float(input_costo_prod.value) if input_costo_prod.value else 0.00
            costo_usd_ingresado = float(input_costo_usd_prod.value) if input_costo_usd_prod.value else 0.00
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
                        """UPDATE productos SET stock = %s, categoria = %s, costo = %s, costo_usd = %s, grupo_surtido = %s,
                           precio_uni_pen = %s, precio_uni_usd = %s, precio_six_pen = %s, precio_six_usd = %s, 
                           precio_caja_pen = %s, precio_caja_usd = %s, precio_plancha_pen = %s, precio_plancha_usd = %s 
                           WHERE id_producto = %s""",
                        (nuevo_stock, categoria, costo_ingresado, costo_usd_ingresado, grupo_ingresado, p_uni_pen, p_uni_usd, p_six_pen, p_six_usd, p_caja_pen, p_caja_usd, p_plan_pen, p_plan_usd, id_prod)
                    )
                    mensaje = f"Se sumaron {stock_ingresado} unidades.\nNuevo stock: {nuevo_stock}"
                else:
                    cursor.execute(
                        """INSERT INTO productos (nombre, presentacion, categoria, costo, costo_usd, grupo_surtido, stock, 
                           precio_uni_pen, precio_uni_usd, precio_six_pen, precio_six_usd, 
                           precio_caja_pen, precio_caja_usd, precio_plancha_pen, precio_plancha_usd) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (nombre, presentacion, categoria, costo_ingresado, costo_usd_ingresado, grupo_ingresado, stock_ingresado, p_uni_pen, p_uni_usd, p_six_pen, p_six_usd, p_caja_pen, p_caja_usd, p_plan_pen, p_plan_usd)
                    )
                    mensaje = "Producto registrado correctamente."

            page.close(dialogo_producto) 
            dialogo_exito.content.value = mensaje
            page.open(dialogo_exito)
            cargar_datos_inventario() 
            
        except Exception as ex:
            page.open(ft.SnackBar(ft.Text(f"Error BD: {ex}"), bgcolor=ft.colors.RED))
            
        boton.text = "Guardar"; boton.disabled = False; page.update()

    dialogo_producto = ft.AlertDialog(
        title=ft.Text("Registrar Nuevo Producto", weight=ft.FontWeight.BOLD),
        content=ft.Container(
            width=650, 
            content=ft.Column([
                ft.Container(height=10),
                ft.ResponsiveRow([input_nombre_prod, input_presentacion_prod]),
                ft.ResponsiveRow([dropdown_categoria, input_grupo_prod, input_stock_prod, input_costo_prod, input_costo_usd_prod]),
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
            input_grupo_prod.value = ""
            dropdown_categoria.value = None
            input_costo_prod.value = "0.00"
            input_costo_usd_prod.value = "0.00"
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

    id_producto_ingreso = [None]

    input_buscar_ingreso = ft.TextField(label="Buscar Producto...", hint_text="Escribe el nombre...", col={"sm": 12, "md": 8})
    lista_resultados_ingreso = ft.ListView(spacing=2, padding=5, visible=False, height=120)
    input_ingreso_cant = ft.TextField(label="Cantidad", value="0", col={"sm": 12, "md": 4})
    
    drop_ingreso_destino = ft.Dropdown(
        label="Destino de Mercadería",
        options=[
            ft.dropdown.Option("INVENTARIO DE TIENDA (Suma al Stock)"),
            ft.dropdown.Option("DEVOLUCIÓN A VECINO (No suma al Stock)"),
            ft.dropdown.Option("CONSUMO INTERNO (No suma al Stock)")
        ],
        value="INVENTARIO DE TIENDA (Suma al Stock)",
        col={"sm": 12, "md": 12}
    )
    input_ingreso_obs = ft.TextField(label="Comentarios / Justificación", multiline=True, col={"sm": 12, "md": 12})

    def seleccionar_prod_ingreso(id_prod, texto):
        id_producto_ingreso[0] = id_prod
        input_buscar_ingreso.value = texto
        lista_resultados_ingreso.visible = False
        page.update()

    def buscar_dinamico_ingreso(e):
        busqueda = input_buscar_ingreso.value.strip()
        if len(busqueda) < 2:
            lista_resultados_ingreso.controls.clear()
            lista_resultados_ingreso.visible = False
            page.update()
            return
            
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT id_producto, nombre, presentacion FROM productos WHERE nombre LIKE %s LIMIT 20", (f"%{busqueda}%",))
                resultados = cursor.fetchall()
                
            if input_buscar_ingreso.value.strip() != busqueda: return
            
            lista_resultados_ingreso.controls.clear()
            if resultados:
                lista_resultados_ingreso.visible = True
                for fila in resultados:
                    id_prod, nom, pres = fila
                    texto_lista = f"{nom} ({pres})"
                    lista_resultados_ingreso.controls.append(
                        ft.ListTile(
                            title=ft.Text(texto_lista, size=13),
                            on_click=lambda e, i=id_prod, t=texto_lista: seleccionar_prod_ingreso(i, t)
                        )
                    )
            else:
                lista_resultados_ingreso.visible = False
            page.update()
        except Exception as ex:
            print(f"Error en búsqueda de ingreso: {ex}")

    input_buscar_ingreso.on_change = buscar_dinamico_ingreso

    def abrir_dialogo_ingreso(e):
        if not tiene_permiso(): return
        id_producto_ingreso[0] = None
        input_buscar_ingreso.value = ""
        lista_resultados_ingreso.visible = False
        input_ingreso_cant.value = "0"
        input_ingreso_obs.value = ""
        page.open(dialogo_ingreso)

    def guardar_ingreso(e):
        if not id_producto_ingreso[0] or not input_ingreso_cant.value.isdigit() or int(input_ingreso_cant.value) <= 0:
            page.open(ft.SnackBar(ft.Text("Busque un producto de la lista y coloque una cantidad válida", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            return
            
        id_prod = id_producto_ingreso[0]
        cant = int(input_ingreso_cant.value)
        destino = drop_ingreso_destino.value
        obs = input_ingreso_obs.value
        
        try:
            with obtener_cursor(commit=True) as cursor:
                cursor.execute("INSERT INTO historial_ingresos (id_producto, cantidad, destino, comentarios) VALUES (%s, %s, %s, %s)", 
                               (id_prod, cant, destino, obs))
                
                if "Suma al Stock" in destino:
                    cursor.execute("UPDATE productos SET stock = stock + %s WHERE id_producto = %s", (cant, id_prod))
                    mensaje = "✅ Ingreso registrado y sumado al stock de la tienda."
                else:
                    mensaje = f"✅ Ingreso registrado como: {destino.split(' (')[0]}"

            page.close(dialogo_ingreso)
            cargar_datos_inventario()
            page.open(ft.SnackBar(ft.Text(mensaje, color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
        except Exception as ex:
            page.open(ft.SnackBar(ft.Text(f"Error: {ex}", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    dialogo_ingreso = ft.AlertDialog(
        title=ft.Text("Registrar Compra / Ingreso", weight=ft.FontWeight.BOLD),
        content=ft.Container(
            width=500,
            content=ft.Column([
                ft.Container(height=10),
                ft.ResponsiveRow([input_buscar_ingreso, input_ingreso_cant]),
                lista_resultados_ingreso,
                ft.ResponsiveRow([drop_ingreso_destino]),
                ft.ResponsiveRow([input_ingreso_obs])
            ], tight=True)
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: page.close(dialogo_ingreso)),
            ft.ElevatedButton("Guardar Registro", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=guardar_ingreso)
        ]
    )

    vista_inventario = ft.Container(
        visible=False, 
        **estilo_tarjeta,
        content=ft.Column([
            ft.Row([
                ft.Text("Gestión de Inventario", size=22, weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.ElevatedButton("Ingresar Stock", icon=ft.icons.LOCAL_SHIPPING, style=ft.ButtonStyle(bgcolor=ft.colors.ORANGE_700, color=ft.colors.WHITE), on_click=abrir_dialogo_ingreso),
                    ft.ElevatedButton("Excel", icon=ft.icons.DOWNLOAD, style=ft.ButtonStyle(bgcolor=ft.colors.BLUE, color=ft.colors.WHITE), on_click=exportar_excel),
                    ft.ElevatedButton("Agregar Nuevo", icon=ft.icons.ADD, style=ft.ButtonStyle(bgcolor=ft.colors.GREEN, color=ft.colors.WHITE), on_click=abrir_dialogo_nuevo),
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
                cursor.execute("SELECT nombre_negocio, ruc, direccion, telefono, mensaje_ticket FROM configuracion LIMIT 1")
                conf = cursor.fetchone()
                c_nom_emp = conf[0] if conf else "LICOR STORE"
                c_ruc_emp = conf[1] if conf else ""
                c_dir_emp = conf[2] if conf else ""
                c_tel_emp = conf[3] if conf else ""
                c_msg_emp = conf[4] if conf else "¡Gracias por su compra!"

                cursor.execute("SELECT fecha_emision, hora_emision, vendedor, cliente_nombre, cliente_dni, cliente_direccion, total_pen, total_usd, metodo_pago, monto_efectivo, monto_yape, monto_plin, monto_tarjeta, vuelto FROM ventas WHERE id_venta = %s", (id_venta,))
                cabecera = cursor.fetchone()

                cursor.execute("""
                    SELECT p.nombre, d.cantidad, d.tipo_empaque, d.precio_unitario, d.subtotal_pen, d.subtotal_usd, p.grupo_surtido, p.presentacion 
                    FROM detalles_venta d 
                    JOIN productos p ON d.id_producto = p.id_producto 
                    WHERE d.id_venta = %s
                """, (id_venta,))
                detalles_db = cursor.fetchall()

            detalles = []
            mixes_agrupados = {}
            
            for det in detalles_db:
                nom, cant, emp, pu, sub_pen, sub_usd, grupo, pres = det
                if str(emp).startswith("Mix ") and grupo:
                    clave = (grupo, emp, pres)
                    if clave not in mixes_agrupados:
                        mixes_agrupados[clave] = {"cant": 0, "sub_pen": 0.0, "sub_usd": 0.0}
                    mixes_agrupados[clave]["cant"] += cant
                    mixes_agrupados[clave]["sub_pen"] += float(sub_pen)
                    mixes_agrupados[clave]["sub_usd"] += float(sub_usd)
                else:
                    detalles.append([nom, cant, emp, pu, sub_pen, sub_usd])
            
            for clave, data in mixes_agrupados.items():
                grupo, emp, pres = clave
                divisor = 6 if emp == "Mix Six" else (12 if emp == "Mix Caj" else 24)
                emp_real = "Six-pack" if emp == "Mix Six" else ("Caja" if emp == "Mix Caj" else "Plancha")
                cant_real = data["cant"] // divisor
                
                if cant_real > 0:
                    nombre_consolidado = f"{grupo} SURTIDO {pres}"
                    pu_real = data["sub_pen"] / cant_real
                    detalles.append([nombre_consolidado, cant_real, emp_real, pu_real, data["sub_pen"], data["sub_usd"]])

            if not cabecera:
                raise ValueError(f"No se encontró la venta con id {id_venta}.")

            f_emision, h_emision, vendedor, c_nombre, c_dni, c_dir, t_pen, t_usd, m_pago, m_efec, m_yape, m_plin, m_tarj, vuelto = cabecera

            lineas_totales_productos = sum(max(1, len(textwrap.wrap(str(d[0]), width=22))) for d in detalles)
            alto_total = 140 + (lineas_totales_productos * 5) 

            pdf = FPDF(orientation='P', unit='mm', format=(80, alto_total)) 
            pdf.set_margins(5, 5, 5) 
            pdf.set_auto_page_break(auto=False, margin=0) 
            pdf.add_page()
            
            pdf.image("LogoLK.png", x=15, y=5, w=50) 
            pdf.ln(18) 
            
            pdf.set_font("Arial", 'B', 9)
            if c_nom_emp and str(c_nom_emp).strip():
                pdf.cell(70, 4, txt=str(c_nom_emp).strip().upper(), ln=True, align='C')
            pdf.set_font("Arial", size=7)
            if c_ruc_emp and str(c_ruc_emp).strip(): 
                pdf.cell(70, 4, txt=f"RUC: {str(c_ruc_emp).strip()}", ln=True, align='C')
            if c_dir_emp and str(c_dir_emp).strip(): 
                for linea_dir in textwrap.wrap(str(c_dir_emp).strip(), width=35):
                    pdf.cell(70, 4, txt=linea_dir, ln=True, align='C')
            if c_tel_emp and str(c_tel_emp).strip(): 
                pdf.cell(70, 4, txt=f"Cel: {str(c_tel_emp).strip()}", ln=True, align='C')
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
            pdf.ln(3)
            
            pdf.set_font("Arial", 'B', 6) 
            pdf.cell(6, 4, txt="Cant", align='C')
            pdf.cell(8, 4, txt="Unid", align='C')
            pdf.cell(26, 4, txt="Descripción", align='C')
            pdf.cell(10, 4, txt="P.U.", align='C')
            pdf.cell(10, 4, txt="Sub S/", align='C')
            pdf.cell(10, 4, txt="Sub $", ln=True, align='C')
            
            y_actual = pdf.get_y()
            pdf.line(5, y_actual, 75, y_actual)
            pdf.ln(1)
            
            pdf.set_font("Arial", size=5)
            for det in detalles:
                lineas_desc = textwrap.wrap(str(det[0]), width=22)
                if not lineas_desc: lineas_desc = [""]

                pdf.cell(6, 3, txt=str(det[1]), align='C')
                pdf.cell(8, 3, txt=str(det[2][:3]).upper(), align='C') 
                pdf.cell(26, 3, txt=lineas_desc[0], align='L')
                pdf.cell(10, 3, txt=f"{det[3]:.2f}", align='C')
                pdf.cell(10, 3, txt=f"{det[4]:.2f}", align='R')
                pdf.cell(10, 3, txt=f"{det[5]:.2f}", ln=True, align='R')
                
                for linea_extra in lineas_desc[1:]:
                    pdf.cell(14, 3, txt="", align='C') 
                    pdf.cell(26, 3, txt=linea_extra, align='L')
                    pdf.cell(30, 3, txt="", ln=True, align='R') 
                
                y_actual = pdf.get_y()
                pdf.set_draw_color(200, 200, 200)
                pdf.line(5, y_actual, 75, y_actual)
                pdf.set_draw_color(0, 0, 0)
                pdf.ln(1)
                
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
            
            if t_pen > 0:
                entero = int(t_pen)
                centimos = int(round((t_pen - entero) * 100))
                texto_pen = num2words(entero, lang='es').capitalize()
                pdf.set_font("Arial", size=7)
                pdf.write(4, "Son: ")
                pdf.set_font("Arial", 'B', 7)
                pdf.write(4, f"{texto_pen} con {centimos:02d}/100 Soles\n")
            
            if t_usd > 0:
                entero_usd = int(t_usd)
                centimos_usd = int(round((t_usd - entero_usd) * 100))
                texto_usd = num2words(entero_usd, lang='es').capitalize()
                pdf.set_font("Arial", size=7)
                pdf.write(4, "Son: ")
                pdf.set_font("Arial", 'B', 7)
                pdf.write(4, f"{texto_usd} con {centimos_usd:02d}/100 Dólares Americanos\n")
            
            pdf.ln(3)
            
            pdf.set_font("Arial", 'B', 7)
            pdf.write(4, "Condición de Pago: ")
            pdf.set_font("Arial", size=7)
            pdf.write(4, "Contado\n")
            
            pdf.set_font("Arial", 'B', 7)
            pdf.cell(70, 4, txt="Pagos:", ln=True, align='L')
            
            total_yape_plin = m_yape + m_plin
            pdf.set_font("Arial", size=7)
            
            if m_efec > 0: 
                pdf.cell(70, 4, txt=f"- Efectivo - S/ {m_efec:.2f}", ln=True, align='L')
            if total_yape_plin > 0: 
                pdf.cell(70, 4, txt=f"- Yape/Plin - S/ {total_yape_plin:.2f}", ln=True, align='L')
            if m_tarj > 0: 
                pdf.cell(70, 4, txt=f"- Tarjeta - S/ {m_tarj:.2f}", ln=True, align='L')
            if t_usd > 0: 
                pdf.cell(70, 4, txt=f"- Efectivo - $ {t_usd:.2f}", ln=True, align='L')
    
            pdf.set_font("Arial", 'B', 7)
            pdf.write(4, "Vuelto: ")
            pdf.set_font("Arial", size=7)
            pdf.write(4, f"S/ {vuelto:.2f}\n")

            # --- 5. VENDEDOR ---
            pdf.set_font("Arial", 'B', 7)
            pdf.write(4, "Vendedor: ")
            pdf.set_font("Arial", size=7)
            pdf.write(4, f"{str(vendedor).upper()}\n")

            if c_msg_emp and str(c_msg_emp).strip():
                pdf.ln(5)
                pdf.set_font("Arial", 'B', 7)
                pdf.cell(70, 4, txt=str(c_msg_emp).strip(), ln=True, align='C')

            import os
            dir_base = os.path.dirname(os.path.abspath(__file__))
            ruta_pdf = os.path.join(dir_base, "assets", f"{codigo_ticket}.pdf")
            os.makedirs(os.path.dirname(ruta_pdf), exist_ok=True)
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
                    multiplicadores = {"Unidad": 1, "Pack-4": 4, "Six-pack": 6, "Caja": 12, "Pack-15": 15, "Plancha": 24, "Mix Six": 1, "Mix Caj": 1, "Mix Pla": 1}
                    
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

    def limpiar_busqueda_reporte(e):
        input_buscar_reporte.value = ""
        cargar_ventas_diarias()
        page.update()

    input_buscar_reporte = ft.TextField(
        label="Buscar producto en el historial de ventas...", prefix_icon=ft.icons.SEARCH,
        suffix=ft.IconButton(ft.icons.CLEAR, on_click=limpiar_busqueda_reporte),
        on_submit=lambda _: cargar_ventas_diarias(),
        col={"sm": 12, "md": 8}
    )

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
            busqueda_prod = input_buscar_reporte.value.strip()

            # 2. Modificamos la consulta SQL para que detecte si se busca un producto
            query = "SELECT DISTINCT v.id_venta, v.codigo_ticket, v.fecha_emision, v.hora_emision, v.cliente_nombre, v.total_pen, v.total_usd, v.estado FROM ventas v"
            
            if busqueda_prod:
                query += " JOIN detalles_venta d ON v.id_venta = d.id_venta JOIN productos p ON d.id_producto = p.id_producto"
                
            query += " WHERE 1=1"
            params = []
            
            if rango == "Hoy":
                query += " AND v.fecha_emision = %s"
                params.append(fecha_hoy)
            elif rango == "Últimos 7 días":
                query += " AND v.fecha_emision >= %s"
                params.append(fecha_hoy - datetime.timedelta(days=7))
            elif rango == "Últimos 30 días":
                query += " AND v.fecha_emision >= %s"
                params.append(fecha_hoy - datetime.timedelta(days=30))
            elif rango == "Personalizado" and input_fecha_inicio.value and input_fecha_fin.value:
                query += " AND v.fecha_emision BETWEEN %s AND %s"
                params.extend([input_fecha_inicio.value, input_fecha_fin.value])
                
            if busqueda_prod:
                query += " AND p.nombre LIKE %s"
                params.append(f"%{busqueda_prod}%")
                
            query += " ORDER BY v.id_venta DESC"

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
            actualizar_grafico_barras()
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
                    ft.Text(f"Tickets Válidos Emitidos: {cantidad_tickets}", size=16),
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

    grafico_rotacion = ft.BarChart(
        bar_groups=[], bottom_axis=ft.ChartAxis(labels=[], labels_size=60),
        horizontal_grid_lines=ft.ChartGridLines(color=ft.colors.GREY_300, width=1, dash_pattern=[3, 3]),
        tooltip_bgcolor=ft.colors.BLACK87, interactive=True
    )

    contenedor_grafico = ft.Container(
        content=grafico_rotacion, height=320, padding=20, bgcolor=ft.colors.WHITE,
        border_radius=10, border=ft.border.all(1, ft.colors.GREY_200)
    )

    def actualizar_grafico_barras():
        try:
            rango = filtro_rango_rep.value
            fecha_hoy = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).date()

            query = """
                SELECT p.nombre, SUM(CASE d.tipo_empaque WHEN 'Unidad' THEN d.cantidad * 1 WHEN 'Six-pack' THEN d.cantidad * 6 WHEN 'Caja' THEN d.cantidad * 12 WHEN 'Plancha' THEN d.cantidad * 24 ELSE d.cantidad END) as unidades_vendidas
                FROM detalles_venta d JOIN ventas v ON d.id_venta = v.id_venta JOIN productos p ON d.id_producto = p.id_producto
                WHERE v.estado != 'Anulada'
            """
            params = []

            if rango == "Hoy":
                query += " AND v.fecha_emision = %s"
                params.append(fecha_hoy)
            elif rango == "Últimos 7 días":
                query += " AND v.fecha_emision >= %s"
                params.append(fecha_hoy - datetime.timedelta(days=7))
            elif rango == "Últimos 30 días":
                query += " AND v.fecha_emision >= %s"
                params.append(fecha_hoy - datetime.timedelta(days=30))
            elif rango == "Personalizado" and input_fecha_inicio.value and input_fecha_fin.value:
                query += " AND v.fecha_emision BETWEEN %s AND %s"
                params.extend([input_fecha_inicio.value, input_fecha_fin.value])

            query += " GROUP BY p.id_producto, p.nombre ORDER BY unidades_vendidas DESC LIMIT 5"

            with obtener_cursor() as cursor:
                cursor.execute(query, tuple(params))
                resultados = cursor.fetchall()
            grafico_rotacion.bar_groups.clear()
            grafico_rotacion.bottom_axis.labels.clear()

            colores = [ft.colors.BLUE, ft.colors.GREEN, ft.colors.ORANGE, ft.colors.PURPLE, ft.colors.RED]
            max_y = 0

            if resultados:
                for i, fila in enumerate(resultados):
                    nombre_completo = str(fila[0])
                    nombre_corto = nombre_completo[:12] + "..." if len(nombre_completo) > 12 else nombre_completo
                    unidades = float(fila[1]) if fila[1] else 0.0
                    if unidades > max_y: max_y = unidades
                    grafico_rotacion.bar_groups.append(ft.BarChartGroup(x=i, bar_rods=[ft.BarChartRod(from_y=0, to_y=unidades, width=35, color=colores[i % len(colores)], tooltip=f"{unidades} unid.")]))
                    grafico_rotacion.bottom_axis.labels.append(ft.ChartAxisLabel(value=i, label=ft.Text(nombre_corto, size=11, weight=ft.FontWeight.BOLD)))
            else:
                grafico_rotacion.bar_groups.append(ft.BarChartGroup(x=0, bar_rods=[ft.BarChartRod(from_y=0, to_y=0, width=35, color=ft.colors.GREY)]))
                grafico_rotacion.bottom_axis.labels.append(ft.ChartAxisLabel(value=0, label=ft.Text("Sin datos", size=11)))

            grafico_rotacion.max_y = max_y + (max_y * 0.2) if max_y > 0 else 10
            page.update()

        except Exception as e:
            print(f"Error al cargar gráfico de rotación: {e}")

    def cambiar_fecha_inicio(e):
        if dp_inicio.value: input_fecha_inicio.value = dp_inicio.value.strftime("%Y-%m-%d"); page.update()

    def cambiar_fecha_fin(e):
        if dp_fin.value: input_fecha_fin.value = dp_fin.value.strftime("%Y-%m-%d"); page.update()

    dp_inicio = ft.DatePicker(on_change=cambiar_fecha_inicio, cancel_text="Cancelar", confirm_text="Seleccionar")
    dp_fin = ft.DatePicker(on_change=cambiar_fecha_fin, cancel_text="Cancelar", confirm_text="Seleccionar")
    page.overlay.extend([dp_inicio, dp_fin])

    def cambiar_filtro_reportes(e):
        es_personalizado = (filtro_rango_rep.value == "Personalizado")
        input_fecha_inicio.visible = es_personalizado
        btn_cal_inicio.visible = es_personalizado
        input_fecha_fin.visible = es_personalizado
        btn_cal_fin.visible = es_personalizado
        btn_aplicar_fechas.visible = es_personalizado
        page.update()
        if not es_personalizado:
            cargar_ventas_diarias()

    filtro_rango_rep = ft.Dropdown(
        label="Rango de Fechas",
        options=[
            ft.dropdown.Option("Hoy"), 
            ft.dropdown.Option("Todo el historial"), 
            ft.dropdown.Option("Personalizado")
        ],
        value="Hoy", col={"sm": 12, "md": 4}, on_change=cambiar_filtro_reportes
    )
    
    input_fecha_inicio = ft.TextField(label="Inicio", hint_text="YYYY-MM-DD", read_only=True, visible=False, col={"sm": 8, "md": 3})
    btn_cal_inicio = ft.IconButton(icon=ft.icons.CALENDAR_MONTH, icon_color=ft.colors.BLUE, on_click=lambda _: page.open(dp_inicio), visible=False, col={"sm": 4, "md": 1})

    input_fecha_fin = ft.TextField(label="Fin", hint_text="YYYY-MM-DD", read_only=True, visible=False, col={"sm": 8, "md": 3})
    btn_cal_fin = ft.IconButton(icon=ft.icons.CALENDAR_MONTH, icon_color=ft.colors.BLUE, on_click=lambda _: page.open(dp_fin), visible=False, col={"sm": 4, "md": 1})

    btn_aplicar_fechas = ft.ElevatedButton("Aplicar Rango", bgcolor=ft.colors.BLUE, color=ft.colors.WHITE, on_click=lambda _: cargar_ventas_diarias(), col={"sm": 12, "md": 4}, visible=False)

    tabla_auditoria = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("Fecha/Hora")), ft.DataColumn(ft.Text("Tipo")), ft.DataColumn(ft.Text("Ticket/Prod")), ft.DataColumn(ft.Text("Comentario/Justificación"))], rows=[]
    )
    lbl_utilidad_neta = ft.Text("S/ 0.00", size=24, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN)

    def cargar_auditoria_y_utilidad():
        tabla_auditoria.rows.clear()
        fecha_hoy = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).date()
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT fecha_emision, hora_emision, codigo_ticket, observaciones FROM ventas WHERE fecha_emision = %s AND observaciones != ''", (fecha_hoy,))
                for v in cursor.fetchall(): tabla_auditoria.rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(f"{v[0]} {v[1]}")), ft.DataCell(ft.Text("Venta", color=ft.colors.BLUE)), ft.DataCell(ft.Text(v[2])), ft.DataCell(ft.Text(v[3]))]))
                
                cursor.execute("SELECT fecha_ingreso, p.nombre, comentarios FROM historial_ingresos h JOIN productos p ON h.id_producto = p.id_producto WHERE DATE(fecha_ingreso) = %s AND comentarios != ''", (fecha_hoy,))
                for i in cursor.fetchall(): tabla_auditoria.rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(str(i[0])[:16])), ft.DataCell(ft.Text("Ingreso Inv.", color=ft.colors.ORANGE)), ft.DataCell(ft.Text(i[1])), ft.DataCell(ft.Text(i[2]))]))
                
                cursor.execute("""
                    SELECT SUM(d.subtotal_pen), SUM(d.cantidad * p.costo * CASE d.tipo_empaque WHEN 'Unidad' THEN 1 WHEN 'Pack-4' THEN 4 WHEN 'Six-pack' THEN 6 WHEN 'Caja' THEN 12 WHEN 'Pack-15' THEN 15 WHEN 'Plancha' THEN 24 ELSE 1 END) 
                    FROM detalles_venta d JOIN ventas v ON d.id_venta = v.id_venta JOIN productos p ON d.id_producto = p.id_producto WHERE v.fecha_emision = %s AND v.estado != 'Anulada'
                """, (fecha_hoy,))
                resultado = cursor.fetchone()
                ingresos = resultado[0] if resultado[0] else 0.0; costos = resultado[1] if resultado[1] else 0.0
                lbl_utilidad_neta.value = f"S/ {ingresos - costos:.2f}"
            page.update()
        except Exception as e: print(e)

    tab_graficos = ft.Container(
        padding=10,
        visible=True, 
        content=ft.Column([
            ft.ResponsiveRow([filtro_rango_rep, input_fecha_inicio, btn_cal_inicio, input_fecha_fin, btn_cal_fin, btn_aplicar_fechas], vertical_alignment=ft.CrossAxisAlignment.CENTER), 
            ft.ResponsiveRow([input_buscar_reporte, ft.ElevatedButton("Cuadrar Caja (Rango Actual)", icon=ft.icons.CALCULATE, bgcolor="#F39C12", color=ft.colors.WHITE, on_click=cuadrar_caja_diaria, col={"sm": 12, "md": 4})], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            contenedor_grafico, 
            ft.Column([tabla_ventas_diarias]) 
        ])
    )
    
    tab_auditoria = ft.Container(
        padding=10,
        visible=False,
        content=ft.Column([
            ft.Row([ft.Text("Utilidad Neta del Día:", size=18, weight=ft.FontWeight.BOLD), lbl_utilidad_neta]), 
            ft.Divider(), 
            ft.Text("Registro de Comentarios y Justificaciones", weight=ft.FontWeight.BOLD), 
            ft.Column([tabla_auditoria])
        ])
    )

    def cambiar_pestana_reportes(e):
        if e.control.selected_index == 0:
            tab_graficos.visible = True
            tab_auditoria.visible = False
        else:
            tab_graficos.visible = False
            tab_auditoria.visible = True
        page.update()

    tabs_reportes = ft.Tabs(
        selected_index=0,
        on_change=cambiar_pestana_reportes,
        tabs=[
            ft.Tab(text="Historial y Gráficos"), 
            ft.Tab(text="Auditoría y Utilidades")
        ]
    )

    panel_reportes = ft.Container(
        visible=False, 
        **estilo_tarjeta,
        content=ft.Column([
            ft.Text("Centro de Reportes", size=24, weight=ft.FontWeight.BOLD),
            tabs_reportes,
            tab_graficos,
            tab_auditoria
        ])
    )

    lbl_caja_efectivo = ft.Text("S/ 0.00", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN)
    lbl_caja_yape_plin = ft.Text("S/ 0.00", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.PURPLE)
    lbl_caja_tarjeta = ft.Text("S/ 0.00", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.ORANGE)
    lbl_caja_total = ft.Text("S/ 0.00", size=24, weight=ft.FontWeight.BOLD, color=ft.colors.BLACK)
    lbl_caja_dolares = ft.Text("$ 0.00", size=24, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_800) 

    def crear_tarjeta_caja(titulo, label_valor, color_borde):
        return ft.Container(
            content=ft.Column([ft.Text(titulo, size=14, color=ft.colors.GREY_700, weight=ft.FontWeight.BOLD), label_valor], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=15, bgcolor=ft.colors.WHITE, border_radius=10, border=ft.border.all(2, color_borde), width=160
        )

    tabla_cajas = ft.DataTable(
        heading_row_color=ft.colors.GREY_100, border_radius=8, border=ft.border.all(1, ft.colors.GREY_200),
        columns=[
            ft.DataColumn(ft.Text("Ticket", weight=ft.FontWeight.BOLD)), ft.DataColumn(ft.Text("Hora", weight=ft.FontWeight.BOLD)), 
            ft.DataColumn(ft.Text("M. Principal", weight=ft.FontWeight.BOLD)), ft.DataColumn(ft.Text("Efectivo", weight=ft.FontWeight.BOLD)), 
            ft.DataColumn(ft.Text("Yape/Plin", weight=ft.FontWeight.BOLD)), ft.DataColumn(ft.Text("Tarjeta", weight=ft.FontWeight.BOLD)), 
            ft.DataColumn(ft.Text("Total (S/)", weight=ft.FontWeight.BOLD)), ft.DataColumn(ft.Text("Dólares ($)", weight=ft.FontWeight.BOLD)) 
        ],
        rows=[]
    )

    def cargar_datos_cajas(e=None):
        tabla_cajas.rows.clear()
        fecha_consulta = input_fecha_caja.value if input_fecha_caja.value else datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).date()
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT codigo_ticket, hora_emision, metodo_pago, monto_efectivo, monto_yape, monto_plin, monto_tarjeta, total_pen, total_usd, vuelto 
                    FROM ventas WHERE fecha_emision = %s AND estado != 'Anulada' ORDER BY hora_emision DESC
                """, (fecha_consulta,))
                filas = cursor.fetchall()

                tot_ef, tot_yp, tot_ta, tot_gral, tot_usd = 0.0, 0.0, 0.0, 0.0, 0.0
                for fila in filas:
                    cod, hora, met, ef, ya, pl, ta, total, t_usd, vuelto = fila
                    ef_neto = float(ef) - float(vuelto) 
                    yp_combinado = float(ya) + float(pl)
                    
                    tot_ef += ef_neto; tot_yp += yp_combinado; tot_ta += float(ta); tot_gral += float(total); tot_usd += float(t_usd)
                    
                    tabla_cajas.rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text(cod)), ft.DataCell(ft.Text(str(hora))), ft.DataCell(ft.Text(met)),
                        ft.DataCell(ft.Text(f"{ef_neto:.2f}")), ft.DataCell(ft.Text(f"{yp_combinado:.2f}")), 
                        ft.DataCell(ft.Text(f"{float(ta):.2f}")), ft.DataCell(ft.Text(f"{float(total):.2f}", weight=ft.FontWeight.BOLD)),
                        ft.DataCell(ft.Text(f"{float(t_usd):.2f}", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_800))
                    ]))
                
                lbl_caja_efectivo.value = f"S/ {tot_ef:.2f}"
                lbl_caja_yape_plin.value = f"S/ {tot_yp:.2f}"
                lbl_caja_tarjeta.value = f"S/ {tot_ta:.2f}"
                lbl_caja_total.value = f"S/ {tot_gral:.2f}"
                lbl_caja_dolares.value = f"$ {tot_usd:.2f}"
            
            page.update()
        except Exception as ex:
            print(f"Error cajas: {ex}")

    def cambiar_fecha_calendario(e):
        if date_picker_cajas.value:
            input_fecha_caja.value = date_picker_cajas.value.strftime("%Y-%m-%d")
            cargar_datos_cajas()

    date_picker_cajas = ft.DatePicker(
        on_change=cambiar_fecha_calendario,
        cancel_text="Cancelar",
        confirm_text="Seleccionar",
        help_text="SELECCIONE UNA FECHA",
        field_hint_text="dd/mm/aaaa",
        field_label_text="Ingrese una fecha",
        error_format_text="Formato inválido",
        error_invalid_text="Fecha fuera de rango"
    )
    page.overlay.append(date_picker_cajas)

    input_fecha_caja = ft.TextField(label="Fecha", value=str(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).date()), read_only=True, col={"sm": 8, "md": 4})
    btn_calendario = ft.IconButton(icon=ft.icons.CALENDAR_MONTH, icon_color=ft.colors.BLUE, on_click=lambda _: page.open(date_picker_cajas), col={"sm": 4, "md": 1})
    btn_buscar_caja = ft.ElevatedButton("Buscar Día", on_click=cargar_datos_cajas, bgcolor=ft.colors.BLUE, color=ft.colors.WHITE, col={"sm": 12, "md": 3}, height=50)

    panel_cajas = ft.Container(
        visible=False, **estilo_tarjeta,
        content=ft.Column([
            ft.Text("Control de Cajas Diario", size=24, weight=ft.FontWeight.BOLD),
            ft.ResponsiveRow([input_fecha_caja, btn_calendario, btn_buscar_caja]),
            ft.Divider(),
            ft.Row([
                crear_tarjeta_caja("Efectivo", lbl_caja_efectivo, ft.colors.GREEN),
                crear_tarjeta_caja("Yape / Plin", lbl_caja_yape_plin, ft.colors.PURPLE),
                crear_tarjeta_caja("Tarjeta", lbl_caja_tarjeta, ft.colors.ORANGE),
                crear_tarjeta_caja("TOTAL DÍA (S/)", lbl_caja_total, ft.colors.BLACK),
                crear_tarjeta_caja("DÓLARES FÍSICOS", lbl_caja_dolares, ft.colors.GREEN_800) 
            ], wrap=True, alignment=ft.MainAxisAlignment.SPACE_EVENLY),
            ft.Divider(),
            ft.Column([tabla_cajas], scroll=ft.ScrollMode.AUTO)
        ])
    )

    input_conf_nombre = ft.TextField(label="Nombre Comercial", col={"sm": 12, "md": 6})
    input_conf_ruc = ft.TextField(label="RUC", col={"sm": 12, "md": 6})
    input_conf_dir = ft.TextField(label="Dirección Principal", col={"sm": 12, "md": 12})
    input_conf_tel = ft.TextField(label="Teléfono", col={"sm": 12, "md": 6})
    input_conf_msg = ft.TextField(label="Mensaje final del ticket", col={"sm": 12, "md": 6})

    def cargar_datos_negocio():
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT nombre_negocio, ruc, direccion, telefono, mensaje_ticket FROM configuracion LIMIT 1")
                datos = cursor.fetchone()
                if datos:
                    input_conf_nombre.value, input_conf_ruc.value, input_conf_dir.value, input_conf_tel.value, input_conf_msg.value = datos
            page.update()
        except Exception as ex: print(ex)

    def guardar_datos_negocio(e):
        try:
            with obtener_cursor(commit=True) as cursor:
                cursor.execute("""
                    UPDATE configuracion SET nombre_negocio=%s, ruc=%s, direccion=%s, telefono=%s, mensaje_ticket=%s WHERE id=1
                """, (input_conf_nombre.value, input_conf_ruc.value, input_conf_dir.value, input_conf_tel.value, input_conf_msg.value))
            page.open(ft.SnackBar(ft.Text("✅ Datos del negocio actualizados", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
        except Exception as ex:
            page.open(ft.SnackBar(ft.Text("❌ Error al guardar", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    tab_negocio = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text("Información para Tickets y Recibos", weight=ft.FontWeight.BOLD, size=16),
            ft.ResponsiveRow([input_conf_nombre, input_conf_ruc]),
            ft.ResponsiveRow([input_conf_dir]),
            ft.ResponsiveRow([input_conf_tel, input_conf_msg]),
            ft.ElevatedButton("Guardar Cambios", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=guardar_datos_negocio)
        ])
    )

    # --- 2. Gestión de Usuarios ---
    tabla_usuarios = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("Nombre")), ft.DataColumn(ft.Text("Correo")), ft.DataColumn(ft.Text("Rol")), ft.DataColumn(ft.Text("Acciones"))],
        rows=[]
    )
    
    input_usr_nom = ft.TextField(label="Nombre", col={"sm": 12, "md": 6})
    input_usr_email = ft.TextField(label="Correo Electrónico", col={"sm": 12, "md": 6})
    input_usr_pass = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, col={"sm": 12, "md": 6})
    drop_usr_rol = ft.Dropdown(label="Rol", options=[ft.dropdown.Option("admin"), ft.dropdown.Option("vendedor")], value="vendedor", col={"sm": 12, "md": 6})

    def cargar_usuarios():
        tabla_usuarios.rows.clear()
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT id, nombre, email, rol FROM usuarios")
                for fila in cursor.fetchall():
                    id_u, nom, email, rol = fila
                    
                    btn_borrar = ft.IconButton(ft.icons.DELETE, icon_color=ft.colors.RED, on_click=lambda e, i=id_u: borrar_usuario(i))
                    if rol == "admin": btn_borrar.disabled = True 
                        
                    tabla_usuarios.rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text(nom)), ft.DataCell(ft.Text(email)), ft.DataCell(ft.Text(rol.upper())), ft.DataCell(btn_borrar)
                    ]))
            page.update()
        except Exception as ex: print(ex)

    def guardar_usuario(e):
        if not input_usr_nom.value or not input_usr_email.value or not input_usr_pass.value:
            page.open(ft.SnackBar(ft.Text("Todos los campos son obligatorios", color=ft.colors.WHITE), bgcolor=ft.colors.RED)); return
        try:
            hash_pass = hashlib.sha256(input_usr_pass.value.encode()).hexdigest()
            with obtener_cursor(commit=True) as cursor:
                cursor.execute("INSERT INTO usuarios (nombre, email, password_hash, rol) VALUES (%s, %s, %s, %s)", 
                               (input_usr_nom.value.strip(), input_usr_email.value.strip(), hash_pass, drop_usr_rol.value))
            page.open(ft.SnackBar(ft.Text("✅ Usuario registrado", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
            input_usr_nom.value = ""; input_usr_email.value = ""; input_usr_pass.value = ""
            cargar_usuarios()
        except Exception as ex:
            page.open(ft.SnackBar(ft.Text("❌ Error (Quizás el correo ya existe)", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def borrar_usuario(id_u):
        try:
            with obtener_cursor(commit=True) as cursor: cursor.execute("DELETE FROM usuarios WHERE id=%s", (id_u,))
            page.open(ft.SnackBar(ft.Text("✅ Usuario eliminado", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
            cargar_usuarios()
        except: pass

    tab_usuarios = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text("Registrar Nuevo Cajero/Admin", weight=ft.FontWeight.BOLD, size=16),
            ft.ResponsiveRow([input_usr_nom, input_usr_email]),
            ft.ResponsiveRow([input_usr_pass, drop_usr_rol]),
            ft.ElevatedButton("Crear Usuario", bgcolor=ft.colors.BLUE, color=ft.colors.WHITE, on_click=guardar_usuario),
            ft.Divider(),
            ft.Text("Usuarios Activos", weight=ft.FontWeight.BOLD, size=16),
            ft.Container(content=tabla_usuarios, border=ft.border.all(1, ft.colors.GREY_200), border_radius=8)
        ], scroll=ft.ScrollMode.AUTO)
    )

    input_pass_actual = ft.TextField(label="Contraseña Actual", password=True, can_reveal_password=True, col={"sm": 12, "md": 4})
    input_pass_nueva = ft.TextField(label="Nueva Contraseña", password=True, can_reveal_password=True, col={"sm": 12, "md": 4})
    
    def cambiar_password_personal(e):
        if not input_pass_actual.value or not input_pass_nueva.value:
            page.open(ft.SnackBar(ft.Text("Rellene ambos campos", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            return
            
        hash_actual = hashlib.sha256(input_pass_actual.value.encode()).hexdigest()
        hash_nueva = hashlib.sha256(input_pass_nueva.value.encode()).hexdigest()
        
        try:
            with obtener_cursor(commit=True) as cursor:
                cursor.execute("SELECT id FROM usuarios WHERE rol = %s AND password_hash = %s", (page.rol_usuario, hash_actual))
                if cursor.fetchone():
                    cursor.execute("UPDATE usuarios SET password_hash = %s WHERE rol = %s AND password_hash = %s", (hash_nueva, page.rol_usuario, hash_actual))
                    page.open(ft.SnackBar(ft.Text("✅ Contraseña actualizada con éxito", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
                    input_pass_actual.value = ""; input_pass_nueva.value = ""
                else:
                    page.open(ft.SnackBar(ft.Text("❌ La contraseña actual es incorrecta", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            page.update()
        except Exception as ex: print(ex)

    tab_perfil = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text("Cambiar mi contraseña", weight=ft.FontWeight.BOLD, size=16),
            ft.ResponsiveRow([input_pass_actual, input_pass_nueva]),
            ft.ElevatedButton("Actualizar Seguridad", bgcolor=ft.colors.BLUE_800, color=ft.colors.WHITE, on_click=cambiar_password_personal)
        ])
    )

    panel_configuracion = ft.Container(
        visible=False, **estilo_tarjeta, height=700,
        content=ft.Column([
            ft.Text("Configuración General", size=24, weight=ft.FontWeight.BOLD),
            ft.Tabs(
                selected_index=0, animation_duration=300,
                tabs=[
                    ft.Tab(text="Datos del Negocio", icon=ft.icons.STORE, content=tab_negocio),
                    ft.Tab(text="Gestión de Usuarios", icon=ft.icons.PEOPLE, content=tab_usuarios),
                    ft.Tab(text="Mi Perfil", icon=ft.icons.LOCK_PERSON, content=tab_perfil)
                ],
                expand=1
            )
        ])
    )

    boton_hamburguesa = ft.IconButton(icon=ft.icons.MENU, icon_size=30, on_click=toggle_menu)

    area_derecha = ft.Column([
        ft.Row([boton_hamburguesa]),
        seccion_pos,
        vista_inventario,
        panel_reportes,
        panel_cajas,
        panel_configuracion
    ], expand=True, scroll=ft.ScrollMode.AUTO)

    vista_dashboard = ft.Row([menu_lateral, area_derecha], visible=False, expand=True, vertical_alignment=ft.CrossAxisAlignment.START)

    estilo_input_login = {"border_color": "#CBD5E1", "focused_border_color": "#2563EB", "border_radius": 8, "width": 320}

    input_usuario = ft.TextField(label="Correo electrónico", prefix_icon=ft.icons.EMAIL_OUTLINED, **estilo_input_login)
    input_password = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, prefix_icon=ft.icons.LOCK_OUTLINE, **estilo_input_login)

    def iniciar_sesion(e):
        usuario_email = (input_usuario.value or "").strip()
        password = input_password.value or ""
        hash_ingresado = hashlib.sha256(password.encode()).hexdigest()

        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT nombre, rol, password_hash FROM usuarios WHERE email = %s", (usuario_email,))
                datos_usuario = cursor.fetchone()
        except Exception as ex:
            page.open(ft.SnackBar(ft.Text(f"Error de conexión BD", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            return

        if not datos_usuario or hash_ingresado != datos_usuario[2]:
            page.open(ft.SnackBar(ft.Text("Credenciales incorrectas", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            return

        page.rol_usuario = datos_usuario[1]
        page.client_storage.set("rol_usuario", page.rol_usuario)
        
        vista_login.visible = False
        vista_dashboard.visible = True

        if page.rol_usuario == "vendedor":
            seccion_pos.visible = True
            vista_inventario.visible = False
            panel_reportes.visible = False

        for boton in menu_lateral.content.controls:
            if hasattr(boton, 'data') and boton.data in ["Inventario", "Reportes", "Cajas", "Configuración"]:
                boton.visible = (page.rol_usuario == "admin")

        page.update()

    btn_login = ft.ElevatedButton(
        "Iniciar Sesión", 
        icon=ft.icons.LOGIN_ROUNDED,
        style=ft.ButtonStyle(
            bgcolor="#3B82F6",
            color=ft.colors.WHITE, 
            shape=ft.RoundedRectangleBorder(radius=8)
        ), 
        width=320, 
        height=50, 
        on_click=iniciar_sesion
    )

    tarjeta_login = ft.Container(
        padding=ft.padding.only(left=40, right=40, top=45, bottom=45),
        bgcolor=ft.colors.WHITE,
        border_radius=16,
        border=ft.border.all(1, "#E2E8F0"),
        shadow=ft.BoxShadow(spread_radius=0, blur_radius=30, color=ft.colors.with_opacity(0.06, ft.colors.BLACK), offset=ft.Offset(0, 15)),
        content=ft.Column([
            ft.Icon(ft.icons.LOCAL_BAR, size=60, color="#38BDF8"),
            ft.Text("LIKIO STORE", size=26, weight=ft.FontWeight.W_800, color="#1E293B"),
            ft.Text("Ingresa tus credenciales para continuar", color="#64748B", size=13),
            ft.Divider(color=ft.colors.TRANSPARENT, height=20),
            input_usuario,
            input_password,
            ft.Divider(color=ft.colors.TRANSPARENT, height=10),
            btn_login
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True)
    )

    vista_login = ft.Container(
        expand=True,
        content=tarjeta_login,
        alignment=ft.Alignment(0, 0),
        bgcolor="#F8FAFC"
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

import os
directorio_base = os.path.dirname(os.path.abspath(__file__))
directorio_assets = os.path.join(directorio_base, "assets")
os.makedirs(directorio_assets, exist_ok=True)

ft.app(target=main, view=ft.WEB_BROWSER, assets_dir=directorio_assets, port=int(os.getenv("PORT", 8080)))