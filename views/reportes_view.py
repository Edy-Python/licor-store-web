import flet as ft
import datetime
import threading
import pandas as pd
import os
from database import obtener_cursor
from pdf_generator import exportar_ticket_pdf
from time_service import fecha_local

class ReportesView(ft.Container):
    def __init__(self, page: ft.Page, fn_ver_nota_venta=None, fn_solicitar_password=None, fn_cargar_inventario=None):
        super().__init__()
        self.page = page
        self.fn_ver_nota_venta = fn_ver_nota_venta
        self.fn_solicitar_password = fn_solicitar_password
        self.fn_cargar_inventario = fn_cargar_inventario
        self.visible = False

        # Estilo de tarjeta principal
        self.padding = 25
        self.bgcolor = ft.colors.WHITE
        self.border_radius = 16
        self.shadow = ft.BoxShadow(
            spread_radius=0,    
            blur_radius=25,
            color=ft.colors.with_opacity(0.04, ft.colors.BLACK),
            offset=ft.Offset(0, 8)
        )
        self.border = ft.border.all(1, "#E2E8F0")

        # Variables de estado nativas OOP
        self.timer_reporte = None

        self.construir_interfaz()

    def construir_interfaz(self):
        # 1. Filtros de Fecha (DatePickers)
        self.dp_inicio = ft.DatePicker(on_change=self.cambiar_fecha_inicio, cancel_text="Cancelar", confirm_text="Seleccionar")
        self.dp_fin = ft.DatePicker(on_change=self.cambiar_fecha_fin, cancel_text="Cancelar", confirm_text="Seleccionar")
        self.page.overlay.extend([self.dp_inicio, self.dp_fin])

        self.filtro_rango_rep = ft.Dropdown(
            label="Rango de Fechas",
            options=[
                ft.dropdown.Option("Hoy"),
                ft.dropdown.Option("Ayer"),
                ft.dropdown.Option("Personalizado")
            ],
            value="Hoy", col={"sm": 12, "md": 4},
            height=42, text_size=13, dense=True,
            on_change=self.cambiar_filtro_reportes
        )

        self.input_fecha_inicio = ft.TextField(label="Inicio", hint_text="YYYY-MM-DD", read_only=True, visible=False, col={"sm": 8, "md": 3}, height=42, text_size=13, dense=True)
        self.btn_cal_inicio = ft.IconButton(icon=ft.icons.CALENDAR_MONTH, icon_color=ft.colors.BLUE, on_click=lambda _: self.page.open(self.dp_inicio), visible=False, col={"sm": 4, "md": 1})

        self.input_fecha_fin = ft.TextField(label="Fin", hint_text="YYYY-MM-DD", read_only=True, visible=False, col={"sm": 8, "md": 3}, height=42, text_size=13, dense=True)
        self.btn_cal_fin = ft.IconButton(icon=ft.icons.CALENDAR_MONTH, icon_color=ft.colors.BLUE, on_click=lambda _: self.page.open(self.dp_fin), visible=False, col={"sm": 4, "md": 1})

        self.btn_aplicar_fechas = ft.ElevatedButton("Aplicar Rango", bgcolor=ft.colors.BLUE, color=ft.colors.WHITE, on_click=lambda _: self.cargar_ventas_diarias(), col={"sm": 12, "md": 4}, height=42, visible=False)

        # 2. Búsqueda y Resultados en Reportes
        self.lista_resultados_reporte = ft.ListView(spacing=2, padding=5, visible=False, height=150)
        self.input_buscar_reporte = ft.TextField(
            label="Buscar producto en el historial de ventas...", prefix_icon=ft.icons.SEARCH,
            suffix=ft.IconButton(ft.icons.CLEAR, on_click=self.limpiar_busqueda_reporte),
            on_change=self.buscar_dinamico_reporte,
            on_submit=lambda _: self.cargar_ventas_diarias(),
            col={"sm": 12, "md": 8},
            height=42, text_size=13, dense=True
        )

        # 3. Gráfico de Barras de Rotación
        self.grafico_rotacion = ft.BarChart(
            bar_groups=[], bottom_axis=ft.ChartAxis(labels=[], labels_size=60),
            horizontal_grid_lines=ft.ChartGridLines(color=ft.colors.GREY_300, width=1, dash_pattern=[3, 3]),
            tooltip_bgcolor=ft.colors.BLACK87, interactive=True
        )

        self.contenedor_grafico = ft.Container(
            content=self.grafico_rotacion, height=320, padding=20, bgcolor=ft.colors.WHITE,
            border_radius=10, border=ft.border.all(1, ft.colors.GREY_200)
        )

        # 4. Tabla de Ventas Diarias
        self.tabla_ventas_diarias = ft.DataTable(
            heading_row_color=ft.colors.GREY_100,
            border_radius=8,
            border=ft.border.all(1, ft.colors.GREY_200),
            columns=[
                ft.DataColumn(ft.Text("Ticket", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Fecha y Hora", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Cliente/Estado", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Total (S/)", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Util (S/)", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_700)),
                ft.DataColumn(ft.Text("Total ($)", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Util ($)", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_700)),
                ft.DataColumn(ft.Text("Acciones", weight=ft.FontWeight.BOLD)),
            ],
            rows=[]
        )

        # 5. Tab Gráficos
        self.tab_graficos = ft.Container(
            padding=10,
            visible=True,
            content=ft.Column([
                ft.ResponsiveRow([self.filtro_rango_rep, self.input_fecha_inicio, self.btn_cal_inicio, self.input_fecha_fin, self.btn_cal_fin, self.btn_aplicar_fechas], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.ResponsiveRow([
                    self.input_buscar_reporte,
                    ft.ElevatedButton("Cuadrar Caja (Rango)", icon=ft.icons.CALCULATE, bgcolor="#F39C12", color=ft.colors.WHITE, on_click=self.cuadrar_caja_diaria, col={"sm": 12, "md": 3}),
                    ft.ElevatedButton("Exportar Excel", icon=ft.icons.FILE_DOWNLOAD, bgcolor=ft.colors.TEAL_800, color=ft.colors.WHITE, on_click=self.exportar_reporte_ventas_excel, col={"sm": 12, "md": 3})
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.lista_resultados_reporte,
                self.contenedor_grafico,
                ft.Column([self.tabla_ventas_diarias])
            ])
        )

        # 6. Tab Auditoría y Utilidades
        self.tabla_auditoria = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("Fecha/Hora")), ft.DataColumn(ft.Text("Tipo")), ft.DataColumn(ft.Text("Ticket/Prod")), ft.DataColumn(ft.Text("Comentario/Justificación"))],
            rows=[]
        )
        self.lbl_utilidad_neta = ft.Text("S/ 0.00", size=24, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN)

        self.tab_auditoria = ft.Container(
            padding=10,
            visible=False,
            content=ft.Column([
                ft.Row([ft.Text("Utilidad Neta del Día:", size=18, weight=ft.FontWeight.BOLD), self.lbl_utilidad_neta]),
                ft.Divider(),
                ft.Text("Registro de Comentarios y Justificaciones", weight=ft.FontWeight.BOLD),
                ft.Column([self.tabla_auditoria])
            ])
        )

        # 7. Tabs de navegación de Reportes
        self.tabs_reportes = ft.Tabs(
            selected_index=0,
            on_change=self.cambiar_pestana_reportes,
            tabs=[
                ft.Tab(text="Historial y Gráficos"),
                ft.Tab(text="Auditoría y Utilidades")
            ]
        )

        # Montaje del contenedor
        self.content = ft.Column([
            ft.Text("Centro de Reportes", size=24, weight=ft.FontWeight.BOLD),
            self.tabs_reportes,
            self.tab_graficos,
            self.tab_auditoria
        ])

    # --- CONTROLADORES DE FECHA Y FILTROS ---
    def cambiar_fecha_inicio(self, e):
        if self.dp_inicio.value:
            self.input_fecha_inicio.value = self.dp_inicio.value.strftime("%Y-%m-%d")
            self.page.update()

    def cambiar_fecha_fin(self, e):
        if self.dp_fin.value:
            self.input_fecha_fin.value = self.dp_fin.value.strftime("%Y-%m-%d")
            self.page.update()

    def cambiar_filtro_reportes(self, e):
        es_personalizado = (self.filtro_rango_rep.value == "Personalizado")
        self.input_fecha_inicio.visible = es_personalizado
        self.btn_cal_inicio.visible = es_personalizado
        self.input_fecha_fin.visible = es_personalizado
        self.btn_cal_fin.visible = es_personalizado
        self.btn_aplicar_fechas.visible = es_personalizado
        self.page.update()
        if not es_personalizado:
            self.cargar_ventas_diarias()

    def cambiar_pestana_reportes(self, e):
        if e.control.selected_index == 0:
            self.tab_graficos.visible = True
            self.tab_auditoria.visible = False
        else:
            self.tab_graficos.visible = False
            self.tab_auditoria.visible = True
        self.page.update()

    def refrescar_datos(self):
        self.cargar_ventas_diarias()
        self.cargar_auditoria_y_utilidad()

    # --- BÚSQUEDA DINÁMICA DE REPORTES ---
    def seleccionar_auto_reporte(self, nombre):
        self.input_buscar_reporte.value = nombre
        self.lista_resultados_reporte.visible = False
        self.cargar_ventas_diarias()
        self.page.update()

    def ejecutar_buscar_reporte(self, busqueda):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT DISTINCT nombre FROM productos WHERE nombre LIKE %s LIMIT 20", (f"%{busqueda}%",))
                resultados = cursor.fetchall()
            if self.input_buscar_reporte.value.strip() != busqueda:
                return

            self.lista_resultados_reporte.controls.clear()
            if resultados:
                self.lista_resultados_reporte.visible = True
                for fila in resultados:
                    n = str(fila[0]).strip()
                    self.lista_resultados_reporte.controls.append(ft.ListTile(title=ft.Text(n, size=13), on_click=lambda e, nom=n: self.seleccionar_auto_reporte(nom)))
            else:
                self.lista_resultados_reporte.visible = False
            self.page.update()
        except Exception:
            pass

    def buscar_dinamico_reporte(self, e):
        busqueda = self.input_buscar_reporte.value.strip()
        if len(busqueda) < 2:
            if self.timer_reporte:
                self.timer_reporte.cancel()
            self.lista_resultados_reporte.controls.clear()
            self.lista_resultados_reporte.visible = False
            self.cargar_ventas_diarias()
            return

        if self.timer_reporte:
            self.timer_reporte.cancel()
        self.timer_reporte = threading.Timer(0.3, lambda: self.ejecutar_buscar_reporte(busqueda))
        self.timer_reporte.start()

    def limpiar_busqueda_reporte(self, e):
        self.input_buscar_reporte.value = ""
        self.lista_resultados_reporte.controls.clear()
        self.lista_resultados_reporte.visible = False
        self.cargar_ventas_diarias()
        self.page.update()

    def _construir_condicion_fecha(self, columna="fecha_emision"):
        rango = self.filtro_rango_rep.value
        fecha_hoy = fecha_local()
        clausula = ""
        params = []
        if rango == "Hoy":
            clausula = f" AND {columna} = %s"
            params.append(fecha_hoy)
        elif rango == "Ayer":
            clausula = f" AND {columna} = %s"
            params.append(fecha_hoy - datetime.timedelta(days=1))
        elif rango == "Personalizado" and self.input_fecha_inicio.value and self.input_fecha_fin.value:
            clausula = f" AND {columna} BETWEEN %s AND %s"
            params.extend([self.input_fecha_inicio.value, self.input_fecha_fin.value])
        return clausula, params

    # --- LÓGICA DE VENTAS Y AUDITORÍA ---
    def cargar_ventas_diarias(self):
        self.tabla_ventas_diarias.rows.clear()

        def clic_ver(e):
            id_v, cod = e.control.data
            if self.fn_ver_nota_venta:
                self.fn_ver_nota_venta(id_v, cod)

        def clic_pdf(e):
            id_v, cod = e.control.data
            exportar_ticket_pdf(self.page, id_v, cod)

        def clic_anular(e):
            id_v, cod = e.control.data
            if self.fn_solicitar_password:
                self.fn_solicitar_password(lambda: self.anular_venta(id_v, cod))
            else:
                self.anular_venta(id_v, cod)

        try:
            busqueda_prod = self.input_buscar_reporte.value.strip()

            query = "SELECT DISTINCT v.id_venta, v.codigo_ticket, v.fecha_emision, v.hora_emision, v.cliente_nombre, v.total_pen, v.utilidad_pen, v.total_usd, v.utilidad_usd, v.estado, v.condicion_pago FROM ventas v"

            if busqueda_prod:
                query += " JOIN detalles_venta d ON v.id_venta = d.id_venta JOIN productos p ON d.id_producto = p.id_producto"

            query += " WHERE 1=1"
            cond_fecha, params = self._construir_condicion_fecha("v.fecha_emision")
            query += cond_fecha

            if busqueda_prod:
                query += " AND p.nombre LIKE %s"
                params.append(f"%{busqueda_prod}%")

            query += " ORDER BY v.id_venta DESC"

            with obtener_cursor() as cursor:
                cursor.execute(query, tuple(params))
                filas = cursor.fetchall()

            for fila in filas:
                id_v, cod, fecha, hora, cliente, t_pen, u_pen, t_usd, u_usd, estado, cond_pago = fila
                es_anulada = (estado == "Anulada")
                color_texto = ft.colors.RED if es_anulada else ft.colors.BLACK
                texto_cliente = f"{cliente} (ANULADO)" if es_anulada else f"{cliente if cliente else 'VARIOS'} - {cond_pago}"
                fecha_hora_str = f"{fecha}  {hora}"

                btn_ver = ft.IconButton(ft.icons.VISIBILITY, icon_color=ft.colors.BLUE, tooltip="Ver Ticket", data=(id_v, cod), on_click=clic_ver)
                btn_pdf = ft.IconButton(ft.icons.PICTURE_AS_PDF, icon_color=ft.colors.RED, tooltip="Exportar / Imprimir PDF", data=(id_v, cod), on_click=clic_pdf)
                btn_anular = ft.IconButton(ft.icons.CANCEL, icon_color=ft.colors.GREY if es_anulada else ft.colors.RED, disabled=es_anulada, data=(id_v, cod), on_click=clic_anular)

                acciones = ft.Row([btn_ver, btn_pdf, btn_anular], spacing=0)

                self.tabla_ventas_diarias.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(cod, color=color_texto)),
                    ft.DataCell(ft.Text(fecha_hora_str, color=color_texto)),
                    ft.DataCell(ft.Text(texto_cliente, color=color_texto, weight=ft.FontWeight.BOLD if es_anulada else ft.FontWeight.NORMAL)),
                    ft.DataCell(ft.Text(f"{t_pen:.2f}", color=color_texto)),
                    ft.DataCell(ft.Text(f"{u_pen:.2f}", color=ft.colors.GREEN_700, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(f"{t_usd:.2f}", color=color_texto)),
                    ft.DataCell(ft.Text(f"{u_usd:.2f}", color=ft.colors.GREEN_700, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(acciones)
                ]))

            self.tabla_ventas_diarias.update()
            self.actualizar_grafico_barras()
            self.page.update()
        except Exception as e:
            print(f"Error cargando ventas: {e}")
            self.page.open(ft.SnackBar(ft.Text("No se pudieron cargar las ventas.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def anular_venta(self, id_v, cod_ticket):
        def confirmar_anulacion(e):
            e.control.disabled = True
            self.page.update()
            try:
                with obtener_cursor(commit=True) as cursor:
                    cursor.execute("SELECT estado FROM ventas WHERE id_venta = %s", (id_v,))
                    fila_v = cursor.fetchone()
                    if not fila_v or fila_v[0] == "Anulada":
                        self.page.close(dialogo_anular)
                        self.page.open(ft.SnackBar(ft.Text(f"El ticket {cod_ticket} ya se encuentra anulado.", color=ft.colors.WHITE), bgcolor=ft.colors.AMBER))
                        return

                    cursor.execute("UPDATE ventas SET estado = 'Anulada' WHERE id_venta = %s AND estado != 'Anulada'", (id_v,))

                    cursor.execute("SELECT id_producto, cantidad, tipo_empaque FROM detalles_venta WHERE id_venta = %s", (id_v,))
                    detalles = cursor.fetchall()
                    multiplicadores = {"Unidad": 1, "Pack-4": 4, "Six-pack": 6, "Caja": 12, "Pack-15": 15, "Plancha": 24, "Mix Six": 1, "Mix Caj": 1, "Mix Pla": 1}

                    for det in detalles:
                        id_p, cant, emp = det
                        devolucion = cant * multiplicadores.get(emp, 1)
                        cursor.execute("UPDATE productos SET stock = stock + %s WHERE id_producto = %s", (devolucion, id_p))
                self.page.close(dialogo_anular)
                self.cargar_ventas_diarias()
                if self.fn_cargar_inventario:
                    self.fn_cargar_inventario()
                self.page.open(ft.SnackBar(ft.Text(f"Ticket {cod_ticket} anulado y stock devuelto.", color=ft.colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.colors.ORANGE))
            except Exception as ex:
                print(f"Error anulando: {ex}")
                self.page.open(ft.SnackBar(ft.Text("Error al procesar la anulación.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

        dialogo_anular = ft.AlertDialog(
            title=ft.Text("Confirmar Anulación", color=ft.colors.RED, weight=ft.FontWeight.BOLD),
            content=ft.Text(f"¿Estás seguro de anular la venta {cod_ticket}?\n\nEl stock de estos productos se devolverá automáticamente a tu inventario."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.close(dialogo_anular)),
                ft.ElevatedButton("Anular Venta", bgcolor=ft.colors.RED, color=ft.colors.WHITE, on_click=confirmar_anulacion)
            ]
        )

        self.page.open(dialogo_anular)

    def cuadrar_caja_diaria(self, e):
        try:
            query = "SELECT SUM(total_pen), SUM(total_usd), COUNT(id_venta) FROM ventas WHERE estado != 'Anulada'"
            cond_fecha, params = self._construir_condicion_fecha("fecha_emision")
            query += cond_fecha

            with obtener_cursor() as cursor:
                cursor.execute(query, tuple(params))
                resultado = cursor.fetchone()

            total_pen = resultado[0] if resultado[0] else 0.00
            total_usd = resultado[1] if resultado[1] else 0.00
            cantidad_tickets = resultado[2] if resultado[2] else 0

            def cerrar_cuadre(ev):
                self.page.close(dialogo_cuadre)

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
            self.page.open(dialogo_cuadre)
        except Exception as ex:
            print(f"Error al cuadrar caja: {ex}")
            self.page.open(ft.SnackBar(ft.Text("No se pudo calcular el cuadre de caja.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def exportar_reporte_ventas_excel(self, e):
        try:
            query = """
                SELECT codigo_ticket, fecha_emision, hora_emision, vendedor, cliente_nombre, cliente_dni, 
                       condicion_pago, metodo_pago, monto_efectivo, monto_yape, monto_plin, monto_tarjeta, vuelto, 
                       total_pen, total_usd, utilidad_pen, estado, observaciones
                FROM ventas 
                WHERE 1=1
            """
            cond_fecha, params = self._construir_condicion_fecha("fecha_emision")
            query += cond_fecha
            query += " ORDER BY fecha_emision DESC, hora_emision DESC"

            with obtener_cursor() as cursor:
                cursor.execute(query, tuple(params))
                filas = cursor.fetchall()

            if not filas:
                self.page.open(ft.SnackBar(ft.Text("⚠️ No hay ventas registradas en el rango seleccionado."), bgcolor=ft.colors.ORANGE_800))
                return

            columnas_sql = [
                "Ticket", "Fecha", "Hora", "Vendedor", "Cliente", "DNI/RUC",
                "Condición", "Método Pago", "Efectivo (S/)", "Yape (S/)", "Transferencia (S/)", "Tarjeta (S/)", "Vuelto (S/)",
                "Total (S/)", "Total ($)", "Utilidad Neta (S/)", "Estado", "Observaciones"
            ]

            df = pd.DataFrame(filas, columns=columnas_sql)

            os.makedirs("assets", exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            nombre_archivo = f"Reporte_Ventas_{timestamp}.xlsx"
            ruta_archivo = os.path.join("assets", nombre_archivo)
            df.to_excel(ruta_archivo, index=False)

            self.page.launch_url(f"/{nombre_archivo}", web_window_name="_blank")
            self.page.open(ft.SnackBar(ft.Text(f"✅ Reporte de ventas exportado exitosamente ({nombre_archivo}).", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
        except Exception as ex:
            print(f"Error exportando ventas a Excel: {ex}")
            self.page.open(ft.SnackBar(ft.Text(f"❌ Error al exportar: {ex}", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def actualizar_grafico_barras(self):
        try:
            query = """
                SELECT p.nombre, SUM(CASE d.tipo_empaque WHEN 'Unidad' THEN d.cantidad * 1 WHEN 'Six-pack' THEN d.cantidad * 6 WHEN 'Caja' THEN d.cantidad * 12 WHEN 'Plancha' THEN d.cantidad * 24 ELSE d.cantidad END) as unidades_vendidas
                FROM detalles_venta d JOIN ventas v ON d.id_venta = v.id_venta JOIN productos p ON d.id_producto = p.id_producto
                WHERE v.estado != 'Anulada'
            """
            cond_fecha, params = self._construir_condicion_fecha("v.fecha_emision")
            query += cond_fecha
            query += " GROUP BY p.id_producto, p.nombre ORDER BY unidades_vendidas DESC LIMIT 5"

            with obtener_cursor() as cursor:
                cursor.execute(query, tuple(params))
                resultados = cursor.fetchall()
            self.grafico_rotacion.bar_groups.clear()
            self.grafico_rotacion.bottom_axis.labels.clear()

            colores = [ft.colors.BLUE, ft.colors.GREEN, ft.colors.ORANGE, ft.colors.PURPLE, ft.colors.RED]
            max_y = 0

            if resultados:
                for i, fila in enumerate(resultados):
                    nombre_completo = str(fila[0])
                    nombre_corto = nombre_completo[:12] + "..." if len(nombre_completo) > 12 else nombre_completo
                    unidades = float(fila[1]) if fila[1] else 0.0
                    if unidades > max_y:
                        max_y = unidades
                    self.grafico_rotacion.bar_groups.append(ft.BarChartGroup(x=i, bar_rods=[ft.BarChartRod(from_y=0, to_y=unidades, width=35, color=colores[i % len(colores)], tooltip=f"{unidades} unid.")]))
                    self.grafico_rotacion.bottom_axis.labels.append(ft.ChartAxisLabel(value=i, label=ft.Text(nombre_corto, size=11, weight=ft.FontWeight.BOLD)))
            else:
                self.grafico_rotacion.bar_groups.append(ft.BarChartGroup(x=0, bar_rods=[ft.BarChartRod(from_y=0, to_y=0, width=35, color=ft.colors.GREY)]))
                self.grafico_rotacion.bottom_axis.labels.append(ft.ChartAxisLabel(value=0, label=ft.Text("Sin datos", size=11)))

            self.grafico_rotacion.max_y = max_y + (max_y * 0.2) if max_y > 0 else 10
            self.page.update()

        except Exception as e:
            print(f"Error al cargar gráfico de rotación: {e}")

    def cargar_auditoria_y_utilidad(self):
        self.tabla_auditoria.rows.clear()
        fecha_hoy = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).date()
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT fecha_emision, hora_emision, codigo_ticket, observaciones FROM ventas WHERE fecha_emision = %s AND observaciones != ''", (fecha_hoy,))
                for v in cursor.fetchall():
                    self.tabla_auditoria.rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(f"{v[0]} {v[1]}")), ft.DataCell(ft.Text("Venta", color=ft.colors.BLUE)), ft.DataCell(ft.Text(v[2])), ft.DataCell(ft.Text(v[3]))]))

                cursor.execute("SELECT fecha_ingreso, p.nombre, comentarios FROM historial_ingresos h JOIN productos p ON h.id_producto = p.id_producto WHERE DATE(fecha_ingreso) = %s AND comentarios != ''", (fecha_hoy,))
                for i in cursor.fetchall():
                    self.tabla_auditoria.rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(str(i[0])[:16])), ft.DataCell(ft.Text("Ingreso Inv.", color=ft.colors.ORANGE)), ft.DataCell(ft.Text(i[1])), ft.DataCell(ft.Text(i[2]))]))

                cursor.execute("""
                    SELECT SUM(total_pen), SUM(utilidad_pen) 
                    FROM ventas 
                    WHERE fecha_emision = %s AND estado != 'Anulada'
                """, (fecha_hoy,))
                resultado = cursor.fetchone()
                utilidad = float(resultado[1]) if resultado and resultado[1] else 0.00
                self.lbl_utilidad_neta.value = f"S/ {utilidad:.2f}"
            self.page.update()
        except Exception as e:
            print(e)

