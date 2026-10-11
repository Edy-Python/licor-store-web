import flet as ft
import pandas as pd
import os
import threading
from database import obtener_cursor
from time_service import ahora_local, formatear_fecha_hora

class InventarioView(ft.Container):
    def __init__(self, page: ft.Page, fn_solicitar_password):
        super().__init__()
        self.page = page
        self.fn_solicitar_password = fn_solicitar_password
        self.visible = False
        
        # Estilos
        self.padding = 25
        self.bgcolor = ft.colors.WHITE
        self.border_radius = 16
        self.border = ft.border.all(1, "#E2E8F0")
        self.shadow = ft.BoxShadow(spread_radius=0, blur_radius=25, color=ft.colors.with_opacity(0.04, ft.colors.BLACK), offset=ft.Offset(0, 8))
        
        # Variables de estado nativas OOP (reemplazan manejos frágiles [None])
        self.timer_inv = None
        self.opciones_cat = ["WHISKY", "WHISKEY", "RON","HIELO","CIGARRO", "GOLOSINA", "PISCO", "VINO", "LICOR", "TEQUILA", "CREMA", "GIN", "VODKA", "VERMOUTH", "BRANDY", "COGNAC", "ESPUMANTE", "CHAMPAGNE", "MEZCAL", "CERVEZA", "RTD", "AGUA", "GASEOSA", "ENERGIZANTE", "AGUA TÓNICA", "GINGER ALE", "JUGO"]
        
        self.file_picker_excel = ft.FilePicker(on_result=self.procesar_excel)
        self.page.overlay.append(self.file_picker_excel)

        self.construir_interfaz()

    def tiene_permiso(self):    
        if getattr(self.page, 'rol_usuario', None) != "admin": 
            self.page.open(ft.SnackBar(ft.Text("Acceso denegado: Solo el administrador puede modificar.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            return False
        return True

    def cargar_datos_inventario(self):
        self.tabla_inventario.rows.clear()
        self.page.update()
        try:
            cat = self.filtro_cat_inv.value
            nom = self.filtro_nom_inv.value.strip() if self.filtro_nom_inv.value else ""
            query = "SELECT id_producto, nombre, presentacion, stock, costo_uni_pen, costo_uni_usd, precio_uni_pen, precio_caja_pen FROM productos WHERE 1=1"
            params = []
            
            if cat == "SOLO STOCK BAJO (<= 10)": query += " AND stock <= 10"
            elif cat and cat != "TODAS": query += " AND categoria = %s"; params.append(cat)
            if nom: query += " AND nombre LIKE %s"; params.append(f"%{nom}%")
            if cat == "SOLO STOCK BAJO (<= 10)": query += " ORDER BY stock ASC, id_producto ASC"
            else: query += " ORDER BY id_producto ASC"

            with obtener_cursor() as cursor:
                cursor.execute(query, tuple(params))
                filas = cursor.fetchall()
            
            self.alerta_no_encontrado.visible = (len(filas) == 0)
            correlativo = 1
            for fila in filas:
                stock_actual = int(fila[3])
                id_real = fila[0]
                nombre_prod = str(fila[1])
                costo_pen = float(fila[4]) if fila[4] else 0.00
                costo_usd = float(fila[5]) if fila[5] else 0.00
                p_uni = float(fila[6]) if fila[6] else 0.00
                p_caja = float(fila[7]) if fila[7] else 0.00
                
                if stock_actual <= 0: color_alerta, icono_alerta = ft.colors.RED, ft.icons.ERROR
                elif stock_actual <= 30: color_alerta, icono_alerta = ft.colors.ORANGE_700, ft.icons.WARNING
                else: color_alerta, icono_alerta = ft.colors.BLACK, None
                
                celda_stock = ft.Row([ft.Icon(icono_alerta, color=color_alerta, size=16), ft.Text(str(stock_actual), color=color_alerta, weight=ft.FontWeight.BOLD)]) if icono_alerta else ft.Text(str(stock_actual), color=color_alerta)
                
                btn_ver = ft.IconButton(ft.icons.VISIBILITY, icon_color=ft.colors.GREEN, tooltip="Ver", on_click=lambda e, i=id_real: self.abrir_visualizador(i))
                btn_kardex = ft.IconButton(ft.icons.HISTORY_EDU, icon_color=ft.colors.INDIGO_700, tooltip="Kardex", on_click=lambda e, i=id_real, n=nombre_prod: self.abrir_kardex(i, n))
                btn_editar = ft.IconButton(ft.icons.EDIT, icon_color=ft.colors.BLUE, tooltip="Editar", on_click=lambda e, i=id_real: self.fn_solicitar_password(lambda: self.abrir_edicion(i)))
                btn_borrar = ft.IconButton(ft.icons.DELETE, icon_color=ft.colors.RED, tooltip="Eliminar", on_click=lambda e, i=id_real, n=nombre_prod: self.fn_solicitar_password(lambda: self.confirmar_eliminacion(i, n)))
                
                self.tabla_inventario.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(correlativo), color=color_alerta)), 
                    ft.DataCell(ft.Text(nombre_prod, color=color_alerta, weight=ft.FontWeight.BOLD if stock_actual <= 0 else ft.FontWeight.NORMAL)), 
                    ft.DataCell(ft.Text(str(fila[2]), color=color_alerta)), ft.DataCell(celda_stock), 
                    ft.DataCell(ft.Text(f"{costo_pen:.2f}", color=ft.colors.RED_700, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(f"{costo_usd:.2f}", color=ft.colors.RED_700, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(f"{p_uni:.2f}", color=color_alerta)), ft.DataCell(ft.Text(f"{p_caja:.2f}", color=color_alerta)),
                    ft.DataCell(ft.Row([btn_ver, btn_kardex, btn_editar, btn_borrar], spacing=0))
                ]))
                correlativo += 1
            self.page.update()
        except Exception as e:
            self.page.open(ft.SnackBar(ft.Text("Error cargando inventario.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    # --- KARDEX Y VISUALIZADOR ---
    def abrir_visualizador(self, id_prod):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                SELECT nombre, presentacion, categoria, grupo_surtido, costo_uni_pen, costo_uni_usd, costo_pack4_pen, costo_pack4_usd, costo_six_pen, costo_six_usd, costo_caja_pen, costo_caja_usd, costo_pack15_pen, costo_pack15_usd, costo_plancha_pen, costo_plancha_usd, precio_uni_pen, precio_uni_usd, precio_pack4_pen, precio_pack4_usd, precio_six_pen, precio_six_usd, precio_caja_pen, precio_caja_usd, precio_pack15_pen, precio_pack15_usd, precio_plancha_pen, precio_plancha_usd, stock, COALESCE(codigo_barras, '')
                FROM productos WHERE id_producto = %s
                """, (id_prod,))
                datos = cursor.fetchone()
            if not datos: return
            (n, pres, cat, grupo_sur, c_u_pen, c_u_usd, c_p4_pen, c_p4_usd, c_s_pen, c_s_usd, c_c_pen, c_c_usd, c_p15_pen, c_p15_usd, c_pl_pen, c_pl_usd, p_u_pen, p_u_usd, p_p4_pen, p_p4_usd, p_s_pen, p_s_usd, p_c_pen, p_c_usd, p_p15_pen, p_p15_usd, p_pl_pen, p_pl_usd, stock_act, cod_barras) = datos
        except Exception: return

        def text_ro(label, value): return ft.TextField(label=label, value=value, read_only=True, border_color=ft.colors.GREY_300, col={"sm": 4, "md": 2})

        dlg = ft.AlertDialog(
            title=ft.Text(f"Información: {n}", weight=ft.FontWeight.BOLD),
            content=ft.Container(width=850, content=ft.Column([
                ft.ResponsiveRow([ft.TextField(label="Código Barras", value=str(cod_barras), read_only=True, col={"sm": 12, "md": 4}), ft.TextField(label="Nombre", value=str(n), read_only=True, col={"sm": 12, "md": 5}), ft.TextField(label="Presentación", value=str(pres), read_only=True, col={"sm": 6, "md": 3})]),
                ft.ResponsiveRow([ft.TextField(label="Stock Actual", value=str(stock_act), read_only=True, col={"sm": 6, "md": 4}), ft.TextField(label="Categoría", value=str(cat), read_only=True, col={"sm": 6, "md": 4}), ft.TextField(label="Grupo Surtido", value=str(grupo_sur), read_only=True, col={"sm": 6, "md": 4})]),
                ft.Divider(), ft.Text("COSTOS DE COMPRA", weight=ft.FontWeight.BOLD, color=ft.colors.RED_700),
                ft.ResponsiveRow([text_ro("C. Unid (S/)", f"{c_u_pen:.2f}"), text_ro("C. Unid ($)", f"{c_u_usd:.2f}"), text_ro("C. Pck4 (S/)", f"{c_p4_pen:.2f}"), text_ro("C. Pck4 ($)", f"{c_p4_usd:.2f}"), text_ro("C. Six (S/)", f"{c_s_pen:.2f}"), text_ro("C. Six ($)", f"{c_s_usd:.2f}")]),
                ft.ResponsiveRow([text_ro("C. Caja (S/)", f"{c_c_pen:.2f}"), text_ro("C. Caja ($)", f"{c_c_usd:.2f}"), text_ro("C. Pck15 (S/)", f"{c_p15_pen:.2f}"), text_ro("C. Pck15 ($)", f"{c_p15_usd:.2f}"), text_ro("C. Plan (S/)", f"{c_pl_pen:.2f}"), text_ro("C. Plan ($)", f"{c_pl_usd:.2f}")]),
                ft.Divider(), ft.Text("PRECIOS DE VENTA", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_700),
                ft.ResponsiveRow([text_ro("P. Unid (S/)", f"{p_u_pen:.2f}"), text_ro("P. Unid ($)", f"{p_u_usd:.2f}"), text_ro("P. Pck4 (S/)", f"{p_p4_pen:.2f}"), text_ro("P. Pck4 ($)", f"{p_p4_usd:.2f}"), text_ro("P. Six (S/)", f"{p_s_pen:.2f}"), text_ro("P. Six ($)", f"{p_s_usd:.2f}")]),
                ft.ResponsiveRow([text_ro("P. Caja (S/)", f"{p_c_pen:.2f}"), text_ro("P. Caja ($)", f"{p_c_usd:.2f}"), text_ro("P. Pck15 (S/)", f"{p_p15_pen:.2f}"), text_ro("P. Pck15 ($)", f"{p_p15_usd:.2f}"), text_ro("P. Plan (S/)", f"{p_pl_pen:.2f}"), text_ro("P. Plan ($)", f"{p_pl_usd:.2f}")]),
            ], scroll=ft.ScrollMode.AUTO, tight=True)),
            actions=[ft.ElevatedButton("Cerrar", bgcolor=ft.colors.BLACK, color=ft.colors.WHITE, on_click=lambda e: self.page.close(dlg))]
        )
        self.page.open(dlg)

    def abrir_kardex(self, id_prod, nombre_prod):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT stock, presentacion FROM productos WHERE id_producto = %s", (id_prod,))
                p_info = cursor.fetchone()
                cursor.execute("SELECT fecha_ingreso, cantidad, destino, comentarios FROM historial_ingresos WHERE id_producto = %s ORDER BY fecha_ingreso DESC LIMIT 50", (id_prod,))
                ingresos = cursor.fetchall()
                cursor.execute("SELECT v.fecha_emision, v.hora_emision, v.codigo_ticket, d.cantidad, d.tipo_empaque, v.cliente_nombre FROM detalles_venta d JOIN ventas v ON d.id_venta = v.id_venta WHERE d.id_producto = %s AND v.estado != 'Anulada' ORDER BY v.fecha_emision DESC, v.hora_emision DESC LIMIT 50", (id_prod,))
                ventas = cursor.fetchall()

            mult_map = {"Unidad": 1, "Pack-4": 4, "Six-pack": 6, "Caja": 12, "Pack-15": 15, "Plancha": 24, "Mix Six": 1, "Mix Caj": 1, "Mix Pla": 1}
            movs = [{"fecha": str(i[0])[:16], "tipo": "INGRESO", "doc": "Ingreso", "cantidad": int(i[1]), "signo": "+", "color": ft.colors.GREEN_700, "icono": ft.icons.ARROW_DOWNWARD, "detalle": i[3] or ""} for i in ingresos]
            movs += [{"fecha": f"{v[0]} {str(v[1])[:5]}", "tipo": "VENTA", "doc": f"Ticket {v[2]}", "cantidad": mult_map.get(v[4],1)*int(v[3]), "signo": "-", "color": ft.colors.RED_700, "icono": ft.icons.ARROW_UPWARD, "detalle": f"Cliente: {v[5] or 'VARIOS'} ({v[3]} {v[4]})"} for v in ventas]
            movs.sort(key=lambda m: m["fecha"], reverse=True)

            filas_kardex = [ft.DataRow(cells=[ft.DataCell(ft.Text(m["fecha"])), ft.DataCell(ft.Row([ft.Icon(m["icono"], color=m["color"], size=16), ft.Text(m["tipo"], color=m["color"], weight=ft.FontWeight.BOLD)])), ft.DataCell(ft.Text(m["doc"])), ft.DataCell(ft.Text(f"{m['signo']}{m['cantidad']} uds", color=m["color"], weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(m["detalle"]))]) for m in movs[:60]]
            
            dlg = ft.AlertDialog(
                title=ft.Row([ft.Icon(ft.icons.HISTORY_EDU, color=ft.colors.INDIGO_700), ft.Text(f"Kardex: {nombre_prod}", weight=ft.FontWeight.BOLD)]),
                content=ft.Container(width=850, content=ft.Column([
                    ft.Text(f"Stock Actual: {p_info[0] if p_info else 0} uds", weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_900), ft.Divider(),
                    ft.Column([ft.DataTable(columns=[ft.DataColumn(ft.Text("Fecha/Hora")), ft.DataColumn(ft.Text("Tipo")), ft.DataColumn(ft.Text("Documento")), ft.DataColumn(ft.Text("Cant.")), ft.DataColumn(ft.Text("Detalle"))], rows=filas_kardex)], scroll=ft.ScrollMode.AUTO, height=400)
                ], tight=True)),
                actions=[ft.ElevatedButton("Cerrar", bgcolor=ft.colors.BLACK, color=ft.colors.WHITE, on_click=lambda e: self.page.close(dlg))]
            )
            self.page.open(dlg)
        except Exception as ex: print(ex)

    # --- EDICIÓN Y ELIMINACIÓN ---
    def abrir_edicion(self, id_prod):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT nombre, presentacion, categoria, grupo_surtido, costo_uni_pen, costo_uni_usd, costo_pack4_pen, costo_pack4_usd, costo_six_pen, costo_six_usd, costo_caja_pen, costo_caja_usd, costo_pack15_pen, costo_pack15_usd, costo_plancha_pen, costo_plancha_usd, precio_uni_pen, precio_uni_usd, precio_pack4_pen, precio_pack4_usd, precio_six_pen, precio_six_usd, precio_caja_pen, precio_caja_usd, precio_pack15_pen, precio_pack15_usd, precio_plancha_pen, precio_plancha_usd, COALESCE(codigo_barras, '') FROM productos WHERE id_producto = %s", (id_prod,))
                datos = cursor.fetchone()
            if not datos: return
            n, pres, cat, grupo, c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, cb = datos
        except Exception: return

        in_cb = ft.TextField(label="Código de Barras", value=cb, col={"sm": 12, "md": 4}, height=42, text_size=13, dense=True)
        in_n = ft.TextField(label="Nombre", value=n, col={"sm": 12, "md": 5}, height=42, text_size=13, dense=True)
        in_p = ft.TextField(label="Presentación", value=pres, col={"sm": 12, "md": 3}, height=42, text_size=13, dense=True)
        dr_c = ft.Dropdown(label="Categoría", options=[ft.dropdown.Option(c) for c in self.opciones_cat], value=cat if cat else "LICOR", col={"sm": 6, "md": 6}, height=42, text_size=13, dense=True)
        in_g = ft.TextField(label="Grupo Surtido", value=grupo if grupo else "", col={"sm": 6, "md": 6}, height=42, text_size=13, dense=True)
        
        # Helper variables for inputs
        ic = [ft.TextField(label=lbl, value=f"{val:.2f}", col={"sm": 4, "md": 2}, height=42, text_size=13, dense=True) for lbl, val in zip(["C. Unid (S/)", "C. Unid ($)", "C. Pck4 (S/)", "C. Pck4 ($)", "C. Six (S/)", "C. Six ($)", "C. Caja (S/)", "C. Caja ($)", "C. Pck15 (S/)", "C. Pck15 ($)", "C. Plan (S/)", "C. Plan ($)"], [c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12])]
        ip = [ft.TextField(label=lbl, value=f"{val:.2f}", col={"sm": 4, "md": 2}, height=42, text_size=13, dense=True) for lbl, val in zip(["P. Unid (S/)", "P. Unid ($)", "P. Pck4 (S/)", "P. Pck4 ($)", "P. Six (S/)", "P. Six ($)", "P. Caja (S/)", "P. Caja ($)", "P. Pck15 (S/)", "P. Pck15 ($)", "P. Plan (S/)", "P. Plan ($)"], [p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12])]

        def guardar_edicion(e):
            try:
                with obtener_cursor(commit=True) as cursor:
                    cursor.execute("""
                        UPDATE productos SET nombre=%s, presentacion=%s, categoria=%s, grupo_surtido=%s, codigo_barras=%s,
                        costo_uni_pen=%s, costo_uni_usd=%s, costo_pack4_pen=%s, costo_pack4_usd=%s, costo_six_pen=%s, costo_six_usd=%s, costo_caja_pen=%s, costo_caja_usd=%s, costo_pack15_pen=%s, costo_pack15_usd=%s, costo_plancha_pen=%s, costo_plancha_usd=%s,
                        precio_uni_pen=%s, precio_uni_usd=%s, precio_pack4_pen=%s, precio_pack4_usd=%s, precio_six_pen=%s, precio_six_usd=%s, precio_caja_pen=%s, precio_caja_usd=%s, precio_pack15_pen=%s, precio_pack15_usd=%s, precio_plancha_pen=%s, precio_plancha_usd=%s
                        WHERE id_producto = %s
                    """, (in_n.value, in_p.value, dr_c.value, in_g.value.upper(), in_cb.value) + tuple(float(x.value) for x in ic) + tuple(float(x.value) for x in ip) + (id_prod,))
                self.page.close(dlg)
                self.cargar_datos_inventario()
                self.page.open(ft.SnackBar(ft.Text("✅ Actualizado", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
            except Exception as ex: self.page.open(ft.SnackBar(ft.Text(f"❌ Error: {ex}"), bgcolor=ft.colors.RED))

        dlg = ft.AlertDialog(
            title=ft.Text("Modificar Producto", weight=ft.FontWeight.BOLD),
            content=ft.Container(width=850, content=ft.Column([
                ft.ResponsiveRow([in_cb, in_n, in_p]), ft.ResponsiveRow([dr_c, in_g]), ft.Divider(),
                ft.Text("COSTOS DE COMPRA", weight=ft.FontWeight.BOLD, color=ft.colors.RED_700), ft.ResponsiveRow(ic[:6]), ft.ResponsiveRow(ic[6:]), ft.Divider(),
                ft.Text("PRECIOS DE VENTA", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_700), ft.ResponsiveRow(ip[:6]), ft.ResponsiveRow(ip[6:]),
            ], scroll=ft.ScrollMode.AUTO, tight=True)),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(dlg)), ft.ElevatedButton("Guardar", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=guardar_edicion)]
        )
        self.page.open(dlg)

    def confirmar_eliminacion(self, id_prod, nombre_prod):
        def borrar_bd(e):
            try:
                with obtener_cursor(commit=True) as cursor: cursor.execute("DELETE FROM productos WHERE id_producto = %s", (id_prod,))
                self.page.close(dlg)
                self.cargar_datos_inventario()
                self.page.open(ft.SnackBar(ft.Text(f"🗑️ '{nombre_prod}' eliminado", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            except Exception as err:
                self.page.close(dlg)
                self.page.open(ft.SnackBar(ft.Text(f"❌ Error DB: {err}", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

        dlg = ft.AlertDialog(title=ft.Text("Confirmar Eliminación", color=ft.colors.RED, weight=ft.FontWeight.BOLD), content=ft.Text(f"¿Estás seguro de eliminar '{nombre_prod}'?"), actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(dlg)), ft.ElevatedButton("Eliminar", bgcolor=ft.colors.RED, color=ft.colors.WHITE, on_click=borrar_bd)])
        self.page.open(dlg)

    # --- NUEVO PRODUCTO ---
    def guardar_producto_bd(self, e):
        boton = e.control
        boton.text, boton.disabled = "Guardando...", True; self.page.update()
        if not self.input_nombre_prod.value.strip():
            self.page.open(ft.SnackBar(ft.Text("El nombre es obligatorio"), bgcolor=ft.colors.RED))
            boton.text, boton.disabled = "Guardar", False; self.page.update(); return
        try:
            st = int(self.input_stock_prod.value) if self.input_stock_prod.value.isdigit() else 0
            with obtener_cursor(commit=True) as cursor:
                cursor.execute("SELECT id_producto, stock FROM productos WHERE nombre=%s AND presentacion=%s", (self.input_nombre_prod.value, self.input_presentacion_prod.value))
                existe = cursor.fetchone()
                if existe:
                    cursor.execute("UPDATE productos SET stock = stock + %s WHERE id_producto = %s", (st, existe[0]))
                else:
                    cursor.execute("""
                        INSERT INTO productos (nombre, presentacion, categoria, grupo_surtido, stock, codigo_barras,
                        costo_uni_pen, costo_uni_usd, costo_pack4_pen, costo_pack4_usd, costo_six_pen, costo_six_usd, costo_caja_pen, costo_caja_usd, costo_pack15_pen, costo_pack15_usd, costo_plancha_pen, costo_plancha_usd,
                        precio_uni_pen, precio_uni_usd, precio_pack4_pen, precio_pack4_usd, precio_six_pen, precio_six_usd, precio_caja_pen, precio_caja_usd, precio_pack15_pen, precio_pack15_usd, precio_plancha_pen, precio_plancha_usd) 
                        VALUES (%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (self.input_nombre_prod.value, self.input_presentacion_prod.value, self.dropdown_categoria.value, self.input_grupo_prod.value.upper(), st, self.input_codigo_barras_prod.value) + tuple(float(x.value) for x in self.ic_n) + tuple(float(x.value) for x in self.ip_n))
            self.page.close(self.dialogo_producto)
            self.cargar_datos_inventario()
            self.page.open(ft.SnackBar(ft.Text("✅ Producto guardado"), bgcolor=ft.colors.GREEN))
        except Exception as ex: self.page.open(ft.SnackBar(ft.Text(f"Error: {ex}"), bgcolor=ft.colors.RED))
        boton.text, boton.disabled = "Guardar", False; self.page.update()

    def abrir_dialogo_nuevo(self, e):
        if self.tiene_permiso():
            for f in [self.input_codigo_barras_prod, self.input_nombre_prod, self.input_presentacion_prod, self.input_grupo_prod]: f.value = ""
            self.dropdown_categoria.value = None
            self.input_stock_prod.value = "0"
            for f in self.ic_n + self.ip_n: f.value = "0.00"
            self.page.open(self.dialogo_producto)

    # --- EXCEL ---
    def procesar_excel(self, e: ft.FilePickerResultEvent):
        if not e.files or not self.tiene_permiso(): return
        try:
            df = pd.read_excel(e.files[0].path)
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            def to_float(val):
                try:
                    v = float(val)
                    return v if not pd.isna(v) else 0.0
                except (ValueError, TypeError):
                    return 0.0

            with obtener_cursor(commit=True) as cursor:
                for _, fila in df.iterrows():
                    nombre = str(fila.get('nombre', '')).strip()
                    if not nombre or nombre.lower() == 'nan':
                        continue
                    pres = str(fila.get('presentacion', 'UNIDAD')).strip()
                    if not pres or pres.lower() == 'nan':
                        pres = 'UNIDAD'
                    cat = str(fila.get('categoria', 'LICOR')).strip().upper()
                    if not cat or cat.lower() == 'nan':
                        cat = 'LICOR'
                    grupo = str(fila.get('grupo_surtido', '')).strip().upper()
                    if grupo.lower() == 'nan':
                        grupo = ''
                    cod_barras = str(fila.get('codigo_barras', '')).strip()
                    if cod_barras.lower() == 'nan':
                        cod_barras = ''
                    
                    try:
                        st = int(fila.get('stock', 0))
                    except (ValueError, TypeError):
                        st = 0
                    
                    c_u_pen = to_float(fila.get('costo_uni_pen', 0))
                    c_u_usd = to_float(fila.get('costo_uni_usd', 0))
                    p_u_pen = to_float(fila.get('precio_uni_pen', 0))
                    p_u_usd = to_float(fila.get('precio_uni_usd', 0))
                    p_caja_pen = to_float(fila.get('precio_caja_pen', 0))
                    p_six_pen = to_float(fila.get('precio_six_pen', 0))
                    p_plan_pen = to_float(fila.get('precio_plancha_pen', 0))

                    cursor.execute("SELECT id_producto FROM productos WHERE nombre = %s AND presentacion = %s", (nombre, pres))
                    existente = cursor.fetchone()
                    if existente:
                        cursor.execute("""
                            UPDATE productos SET stock = %s, categoria = %s, grupo_surtido = %s,
                                   costo_uni_pen = %s, costo_uni_usd = %s, precio_uni_pen = %s,
                                   precio_uni_usd = %s, precio_caja_pen = %s, precio_six_pen = %s,
                                   precio_plancha_pen = %s
                            WHERE id_producto = %s
                        """, (st, cat, grupo, c_u_pen, c_u_usd, p_u_pen, p_u_usd, p_caja_pen, p_six_pen, p_plan_pen, existente[0]))
                    else:
                        cursor.execute("""
                            INSERT INTO productos (nombre, presentacion, categoria, grupo_surtido, stock, codigo_barras,
                                                   costo_uni_pen, costo_uni_usd, precio_uni_pen, precio_uni_usd,
                                                   precio_caja_pen, precio_six_pen, precio_plancha_pen)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (nombre, pres, cat, grupo, st, cod_barras, c_u_pen, c_u_usd, p_u_pen, p_u_usd, p_caja_pen, p_six_pen, p_plan_pen))

            self.cargar_datos_inventario()
            self.page.open(ft.SnackBar(ft.Text("✅ Excel procesado e inventario actualizado.", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
        except Exception as ex:
            self.page.open(ft.SnackBar(ft.Text(f"❌ Error Excel: {ex}"), bgcolor=ft.colors.RED))

    def exportar_excel(self, e):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT id_producto, nombre, presentacion, categoria, grupo_surtido, stock, costo_uni_pen, costo_uni_usd, precio_uni_pen, precio_uni_usd, precio_six_pen, precio_caja_pen, precio_plancha_pen FROM productos ORDER BY id_producto ASC")
                df = pd.DataFrame(cursor.fetchall(), columns=[col[0] for col in cursor.description])
            ruta = os.path.join("assets", "Inventario_LicorStore.xlsx")
            df.to_excel(ruta, index=False)
            self.page.launch_url(f"/Inventario_LicorStore.xlsx", web_window_name="_blank")
        except Exception as ex: self.page.open(ft.SnackBar(ft.Text(f"❌ Error: {ex}"), bgcolor=ft.colors.RED))

    # --- UI PRINCIPAL ---
    def construir_interfaz(self):
        # UI Tablas
        self.tabla_inventario = ft.DataTable(columns=[ft.DataColumn(ft.Text(h, weight=ft.FontWeight.BOLD)) for h in ["#", "Prod.", "Pres.", "Stock", "C. S/", "C. $", "P. Uni", "P. Caja", "Acc."]], rows=[])
        self.filtro_cat_inv = ft.Dropdown(options=[ft.dropdown.Option(c) for c in ["TODAS", "SOLO STOCK BAJO (<= 10)"] + self.opciones_cat], value="TODAS", label="Categoría", col={"sm": 12, "md": 4}, height=42, text_size=13, dense=True, on_change=lambda _: self.cargar_datos_inventario())
        self.filtro_nom_inv = ft.TextField(label="Buscar producto por nombre...", prefix_icon=ft.icons.SEARCH, col={"sm": 12, "md": 8}, height=42, text_size=13, dense=True, on_change=lambda e: self.cargar_datos_inventario())
        self.alerta_no_encontrado = ft.Text("❌ Producto no encontrado.", color=ft.colors.RED, visible=False)

        # UI Nuevo Producto
        self.input_codigo_barras_prod = ft.TextField(label="Código de Barras", col={"sm": 12, "md": 4}, height=42, text_size=13, dense=True)
        self.input_nombre_prod = ft.TextField(label="Nombre", col={"sm": 12, "md": 5}, height=42, text_size=13, dense=True)
        self.input_presentacion_prod = ft.TextField(label="Presentación", col={"sm": 12, "md": 3}, height=42, text_size=13, dense=True)
        self.dropdown_categoria = ft.Dropdown(label="Categoría", options=[ft.dropdown.Option(cat) for cat in self.opciones_cat], col={"sm": 6, "md": 4}, height=42, text_size=13, dense=True)
        self.input_grupo_prod = ft.TextField(label="Grupo Surtido", col={"sm": 6, "md": 4}, height=42, text_size=13, dense=True)
        self.input_stock_prod = ft.TextField(label="Stock", value="0", col={"sm": 12, "md": 4}, height=42, text_size=13, dense=True)
        self.ic_n = [ft.TextField(label=lbl, value="0.00", col={"sm": 4, "md": 2}, height=42, text_size=13, dense=True) for lbl in ["C. Unid (S/)", "C. Unid ($)", "C. Pck4 (S/)", "C. Pck4 ($)", "C. Six (S/)", "C. Six ($)", "C. Caja (S/)", "C. Caja ($)", "C. Pck15 (S/)", "C. Pck15 ($)", "C. Plan (S/)", "C. Plan ($)"]]
        self.ip_n = [ft.TextField(label=lbl, value="0.00", col={"sm": 4, "md": 2}, height=42, text_size=13, dense=True) for lbl in ["P. Unid (S/)", "P. Unid ($)", "P. Pck4 (S/)", "P. Pck4 ($)", "P. Six (S/)", "P. Six ($)", "P. Caja (S/)", "P. Caja ($)", "P. Pck15 (S/)", "P. Pck15 ($)", "P. Plan (S/)", "P. Plan ($)"]]
        self.dialogo_producto = ft.AlertDialog(title=ft.Text("Nuevo Producto", weight=ft.FontWeight.BOLD), content=ft.Container(width=850, content=ft.Column([ft.ResponsiveRow([self.input_codigo_barras_prod, self.input_nombre_prod, self.input_presentacion_prod]), ft.ResponsiveRow([self.dropdown_categoria, self.input_grupo_prod, self.input_stock_prod]), ft.Divider(), ft.Text("COSTOS", weight=ft.FontWeight.BOLD, color=ft.colors.RED_700), ft.ResponsiveRow(self.ic_n[:6]), ft.ResponsiveRow(self.ic_n[6:]), ft.Divider(), ft.Text("PRECIOS", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_700), ft.ResponsiveRow(self.ip_n[:6]), ft.ResponsiveRow(self.ip_n[6:])], scroll=ft.ScrollMode.AUTO, tight=True)), actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dialogo_producto)), ft.ElevatedButton("Guardar", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=self.guardar_producto_bd)])

        # Contenedor Principal
        self.content = ft.Column([
            ft.Row([
                ft.Text("Gestión de Inventario", size=22, weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.ElevatedButton("Exportar Excel", icon=ft.icons.DOWNLOAD, style=ft.ButtonStyle(bgcolor=ft.colors.BLUE, color=ft.colors.WHITE), on_click=self.exportar_excel),
                    ft.ElevatedButton("Importar Excel", icon=ft.icons.UPLOAD_FILE, style=ft.ButtonStyle(bgcolor=ft.colors.TEAL_700, color=ft.colors.WHITE), on_click=lambda _: self.file_picker_excel.pick_files(allowed_extensions=["xlsx", "xls"])),
                    ft.ElevatedButton("Agregar Nuevo", icon=ft.icons.ADD, style=ft.ButtonStyle(bgcolor=ft.colors.GREEN, color=ft.colors.WHITE), on_click=self.abrir_dialogo_nuevo),
                ], wrap=True)
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
            ft.ResponsiveRow([self.filtro_cat_inv, self.filtro_nom_inv]),
            self.alerta_no_encontrado,
            ft.Divider(),
            ft.Column([self.tabla_inventario], scroll=ft.ScrollMode.AUTO)
        ])