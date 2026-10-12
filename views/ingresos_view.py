import flet as ft
import threading
import json
from database import obtener_cursor
from time_service import ahora_local, fecha_local, hora_local

class IngresosView(ft.Container):
    def __init__(self, page: ft.Page, fn_solicitar_password=None, fn_recargar_inventario=None):
        super().__init__()
        self.page = page
        self.fn_solicitar_password = fn_solicitar_password
        self.fn_recargar_inventario = fn_recargar_inventario
        self.visible = False
        self.padding = 20
        self.alignment = ft.alignment.top_left

        # Estado en memoria
        self.timer_buscar = None
        self.carrito_items = []  # Lista de dicts con datos de los productos en proceso de ingreso
        self.modo_pestana = "nuevo"  # "nuevo" o "historial"

        # Estilos visuales homogéneos y responsivos
        self.estilo_tarjeta = {
            "padding": 18,
            "bgcolor": ft.colors.WHITE,
            "border_radius": 14,
            "shadow": ft.BoxShadow(
                spread_radius=0,
                blur_radius=18,
                color=ft.colors.with_opacity(0.04, ft.colors.BLACK),
                offset=ft.Offset(0, 4)
            ),
            "border": ft.border.all(1, "#E2E8F0")
        }
        self.estilo_input = {
            "border_color": "#CBD5E1",
            "focused_border_color": "#2563EB",
            "border_radius": 8,
            "dense": True,
            "height": 40,
            "text_size": 13
        }

        self.construir_interfaz()

    def tiene_permiso(self):
        rol = getattr(self.page, 'rol_usuario', None)
        if str(rol).strip().lower() != "admin":
            self.page.open(ft.SnackBar(
                ft.Text("Acceso denegado: Solo el administrador puede gestionar ingresos de stock.", color=ft.colors.WHITE),
                bgcolor=ft.colors.RED
            ))
            return False
        return True

    def construir_interfaz(self):
        # ── 0. Barra Superior de Pestañas (Nuevo Ingreso vs Registro Histórico) ──
        self.btn_tab_nuevo = ft.ElevatedButton(
            "Registrar Nuevo Ingreso",
            icon=ft.icons.ADD_SHOPPING_CART,
            style=ft.ButtonStyle(
                bgcolor="#2563EB",
                color=ft.colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=8)
            ),
            on_click=lambda _: self.cambiar_pestana("nuevo")
        )
        self.btn_tab_historial = ft.OutlinedButton(
            "Registro de Ingresos (Historial)",
            icon=ft.icons.RECEIPT_LONG,
            style=ft.ButtonStyle(
                color="#475569",
                shape=ft.RoundedRectangleBorder(radius=8)
            ),
            on_click=lambda _: self.cambiar_pestana("historial")
        )

        self.barra_tabs = ft.Row([
            self.btn_tab_nuevo,
            self.btn_tab_historial,
            ft.Text("Módulo de Ingreso de Mercadería", size=13, weight=ft.FontWeight.W_500, color="#64748B")
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # ── 1. Componentes del Panel Izquierdo (Búsqueda y Tabla del Carrito) ─
        self.btn_limpiar_buscar = ft.IconButton(
            icon=ft.icons.CLEAR, icon_size=16, width=26, height=26,
            style=ft.ButtonStyle(padding=0), tooltip="Limpiar búsqueda",
            on_click=self.limpiar_busqueda
        )
        self.input_buscar = ft.TextField(
            label="Buscar Producto para Ingresar",
            hint_text="Escribe nombre o escanea código de barras y presiona Enter...",
            prefix_icon=ft.icons.SEARCH,
            suffix=self.btn_limpiar_buscar,
            on_change=self.buscar_dinamico,
            on_submit=self.buscar_y_abrir_emergente_inmediato,
            col={"sm": 12},
            **self.estilo_input
        )
        self.lista_resultados = ft.ListView(spacing=2, padding=5, visible=False, height=180)

        # Tabla Principal del Carrito de Ingresos con Encabezados Abreviados
        self.tabla_carrito = ft.DataTable(
            column_spacing=12,
            heading_row_color="#F1F5F9",
            border_radius=8,
            border=ft.border.all(1, "#E2E8F0"),
            data_row_min_height=42,
            data_row_max_height=48,
            columns=[
                ft.DataColumn(ft.Container(ft.Text("ID", color="#475569", weight=ft.FontWeight.BOLD), width=35)),
                ft.DataColumn(ft.Container(ft.Text("Prod.", color="#475569", weight=ft.FontWeight.BOLD), width=160)),
                ft.DataColumn(ft.Container(ft.Text("Cant. Ing.", color="#475569", weight=ft.FontWeight.BOLD), width=125)),
                ft.DataColumn(ft.Container(ft.Text("C. Compra", color="#475569", weight=ft.FontWeight.BOLD), width=120)),
                ft.DataColumn(ft.Container(ft.Text("P. Venta", color="#475569", weight=ft.FontWeight.BOLD), width=120)),
                ft.DataColumn(ft.Container(ft.Text("Subt.", color="#475569", weight=ft.FontWeight.BOLD), width=85)),
                ft.DataColumn(ft.Container(ft.Text("Acc.", color="#475569", weight=ft.FontWeight.BOLD), width=75)),
            ],
            rows=[]
        )

        self.banner_vacio = ft.Container(
            content=ft.Row([
                ft.Icon(ft.icons.SHOPPING_BAG_OUTLINED, color="#94A3B8", size=18),
                ft.Text("El carrito está vacío. Busca un producto arriba o escanea su código de barras.", size=12, color="#94A3B8")
            ], alignment=ft.MainAxisAlignment.CENTER),
            padding=ft.padding.symmetric(vertical=40),
            visible=True
        )

        self.tabla_carrito.visible = False

        self.contenedor_tabla_scroll = ft.Container(
            content=ft.Column([self.banner_vacio, self.tabla_carrito], scroll=ft.ScrollMode.AUTO, tight=True),
            border=ft.border.all(1, "#E2E8F0"),
            border_radius=8,
            padding=4,
            height=320
        )

        self.panel_izquierdo = ft.Container(
            **self.estilo_tarjeta,
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.icons.LOCAL_SHIPPING, color="#2563EB", size=22),
                    ft.Text("Detalle del Ingreso de Lote", size=18, weight=ft.FontWeight.BOLD, color="#1E293B"),
                ], spacing=8),
                ft.Text("Al seleccionar un producto se abre la ventana para completar todos los costos y precios (unidad, six, caja, etc.).", size=11, color="#64748B"),
                ft.Divider(color="#E2E8F0", height=8),
                ft.ResponsiveRow([self.input_buscar]),
                self.lista_resultados,
                self.contenedor_tabla_scroll
            ], spacing=6, tight=True)
        )

        # ── 2. Componentes del Panel Derecho (Documento y Confirmación) ───────
        self.input_fecha_doc = ft.TextField(
            label="Fecha Doc.",
            value=str(fecha_local()),
            read_only=True,
            col={"sm": 12, "md": 6},
            **self.estilo_input
        )
        self.input_hora_doc = ft.TextField(
            label="Hora Local",
            value=hora_local().strftime("%H:%M:%S"),
            read_only=True,
            col={"sm": 12, "md": 6},
            **self.estilo_input
        )
        self.input_usuario_doc = ft.TextField(
            label="Usuario",
            value="ADMIN",
            read_only=True,
            col={"sm": 12},
            **self.estilo_input
        )
        self.input_comentarios_doc = ft.TextField(
            label="Comentarios / N° Guía / Proveedor",
            hint_text="Ej: Factura F001-893 / Distribuidora San Juan...",
            multiline=True,
            min_lines=2,
            max_lines=3,
            text_size=12,
            dense=True,
            border_color="#CBD5E1",
            focused_border_color="#2563EB",
            border_radius=8
        )

        self.lbl_resumen_items = ft.Text("0", size=14, weight=ft.FontWeight.BOLD, color="#1E293B")
        self.lbl_resumen_unidades = ft.Text("0 uds", size=14, weight=ft.FontWeight.BOLD, color="#1E293B")
        self.lbl_resumen_total_costo = ft.Text("S/ 0.00", size=22, weight=ft.FontWeight.W_800, color="#10B981")

        self.btn_confirmar_ingreso = ft.ElevatedButton(
            "Confirmar Ingreso de Stock",
            icon=ft.icons.CHECK_CIRCLE,
            style=ft.ButtonStyle(
                bgcolor="#10B981",
                color=ft.colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=10)
            ),
            width=float('inf'),
            height=46,
            on_click=self.confirmar_ingreso_click
        )

        self.btn_vaciar_carrito = ft.OutlinedButton(
            "Limpiar Carrito",
            icon=ft.icons.DELETE_SWEEP,
            style=ft.ButtonStyle(
                color=ft.colors.RED_700,
                shape=ft.RoundedRectangleBorder(radius=8)
            ),
            width=float('inf'),
            height=36,
            on_click=self.vaciar_carrito
        )

        self.panel_derecho = ft.Container(
            **self.estilo_tarjeta,
            content=ft.Column([
                ft.Text("Resumen del Documento", size=17, weight=ft.FontWeight.BOLD, color="#1E293B"),
                ft.Divider(color="#E2E8F0", height=8),
                ft.ResponsiveRow([self.input_fecha_doc, self.input_hora_doc]),
                ft.ResponsiveRow([self.input_usuario_doc]),
                self.input_comentarios_doc,
                ft.Divider(color="#E2E8F0", height=8),
                ft.Container(
                    bgcolor="#F8FAFC",
                    padding=10,
                    border_radius=8,
                    border=ft.border.all(1, "#E2E8F0"),
                    content=ft.Column([
                        ft.Row([ft.Text("Líneas de producto:", size=12, color="#64748B"), self.lbl_resumen_items], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([ft.Text("Total uds ingresadas:", size=12, color="#64748B"), self.lbl_resumen_unidades], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Divider(height=6),
                        ft.Row([ft.Text("Inversión de Compra:", size=13, weight=ft.FontWeight.BOLD, color="#334155"), self.lbl_resumen_total_costo], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ], spacing=2, tight=True)
                ),
                ft.Container(height=4),
                self.btn_confirmar_ingreso,
                self.btn_vaciar_carrito
            ], spacing=6, tight=True)
        )

        self.panel_izquierdo.col = {"sm": 12, "md": 12, "lg": 8, "xl": 8}
        self.panel_derecho.col = {"sm": 12, "md": 12, "lg": 4, "xl": 4}

        self.contenedor_nuevo_ingreso = ft.ResponsiveRow([
            self.panel_izquierdo,
            self.panel_derecho
        ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START, spacing=12, run_spacing=12)

        # ── 3. Componentes del Registro de Ingresos Guardados (Solo Lectura) ─
        self.input_buscar_historial = ft.TextField(
            label="Buscar en Registro de Ingresos",
            hint_text="Buscar por N° doc, usuario o comentario...",
            prefix_icon=ft.icons.SEARCH,
            on_change=lambda _: self.cargar_registro_ingresos(),
            col={"sm": 12, "md": 8},
            **self.estilo_input
        )
        self.btn_refrescar_historial = ft.ElevatedButton(
            "Actualizar Registro",
            icon=ft.icons.REFRESH,
            style=ft.ButtonStyle(bgcolor="#3B82F6", color=ft.colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)),
            col={"sm": 12, "md": 4},
            height=40,
            on_click=lambda _: self.cargar_registro_ingresos()
        )

        self.tabla_historial_ingresos = ft.DataTable(
            column_spacing=14,
            heading_row_color="#F1F5F9",
            border_radius=8,
            border=ft.border.all(1, "#E2E8F0"),
            data_row_min_height=40,
            data_row_max_height=46,
            columns=[
                ft.DataColumn(ft.Text("# Doc", weight=ft.FontWeight.BOLD, color="#475569")),
                ft.DataColumn(ft.Text("Fecha", weight=ft.FontWeight.BOLD, color="#475569")),
                ft.DataColumn(ft.Text("Hora", weight=ft.FontWeight.BOLD, color="#475569")),
                ft.DataColumn(ft.Text("Usuario", weight=ft.FontWeight.BOLD, color="#475569")),
                ft.DataColumn(ft.Text("Comentarios / Guía", weight=ft.FontWeight.BOLD, color="#475569")),
                ft.DataColumn(ft.Text("Líneas", weight=ft.FontWeight.BOLD, color="#475569")),
                ft.DataColumn(ft.Text("Costo Total", weight=ft.FontWeight.BOLD, color="#475569")),
                ft.DataColumn(ft.Text("Acc.", weight=ft.FontWeight.BOLD, color="#475569")),
            ],
            rows=[]
        )

        self.contenedor_historial = ft.Container(
            **self.estilo_tarjeta,
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.icons.HISTORY_EDU, color="#1E293B", size=22),
                    ft.Text("Registro Histórico de Documentos de Ingreso (Solo Lectura)", size=18, weight=ft.FontWeight.BOLD, color="#1E293B"),
                ], spacing=8),
                ft.Text("Auditoría inmutable de los lotes y mercancías ingresadas al inventario.", size=12, color="#64748B"),
                ft.Divider(color="#E2E8F0", height=8),
                ft.ResponsiveRow([self.input_buscar_historial, self.btn_refrescar_historial]),
                ft.Container(
                    content=ft.Column([self.tabla_historial_ingresos], scroll=ft.ScrollMode.AUTO, tight=True),
                    border=ft.border.all(1, "#E2E8F0"),
                    border_radius=8,
                    padding=4,
                    height=380
                )
            ], spacing=8, tight=True)
        )

        # Contenedor dinámico de cuerpo anclado arriba
        self.contenedor_cuerpo = ft.Container(
            content=self.contenedor_nuevo_ingreso,
            alignment=ft.alignment.top_left,
            padding=0,
            margin=0
        )

        # Contenedor raíz anclado estrictamente arriba a la izquierda
        self.content = ft.Column([
            self.barra_tabs,
            ft.Divider(color="#E2E8F0", height=8),
            self.contenedor_cuerpo
        ], alignment=ft.MainAxisAlignment.START, horizontal_alignment=ft.CrossAxisAlignment.START, spacing=6, tight=True)

    def iniciar(self):
        """Inicializa fecha, hora, usuario y refresca el estado."""
        self.input_fecha_doc.value = str(fecha_local())
        self.input_hora_doc.value = hora_local().strftime("%H:%M:%S")
        usr = getattr(self.page, 'nombre_usuario', None) or getattr(self.page, 'rol_usuario', None) or "ADMIN"
        self.input_usuario_doc.value = str(usr).strip().upper()
        if self.modo_pestana == "historial":
            self.cargar_registro_ingresos()
        self.page.update()

    def cambiar_pestana(self, pestana):
        self.modo_pestana = pestana
        if pestana == "nuevo":
            self.btn_tab_nuevo.style.bgcolor = "#2563EB"
            self.btn_tab_nuevo.style.color = ft.colors.WHITE
            self.btn_tab_historial.style.bgcolor = None
            self.btn_tab_historial.style.color = "#475569"
            self.contenedor_cuerpo.content = self.contenedor_nuevo_ingreso
        else:
            self.btn_tab_nuevo.style.bgcolor = None
            self.btn_tab_nuevo.style.color = "#475569"
            self.btn_tab_historial.style.bgcolor = "#2563EB"
            self.btn_tab_historial.style.color = ft.colors.WHITE
            self.contenedor_cuerpo.content = self.contenedor_historial
            self.cargar_registro_ingresos()
        self.page.update()

    # ── BÚSQUEDA Y SELECCIÓN ─────────────────────────────────────────────────
    def limpiar_busqueda(self, e=None):
        self.input_buscar.value = ""
        self.lista_resultados.controls.clear()
        self.lista_resultados.visible = False
        self.page.update()

    def buscar_dinamico(self, e):
        texto = (self.input_buscar.value or "").strip()
        if len(texto) < 2:
            if self.timer_buscar: self.timer_buscar.cancel()
            self.lista_resultados.controls.clear()
            self.lista_resultados.visible = False
            self.page.update()
            return
        if self.timer_buscar: self.timer_buscar.cancel()
        self.timer_buscar = threading.Timer(0.3, lambda: self.ejecutar_busqueda(texto))
        self.timer_buscar.start()

    def ejecutar_busqueda(self, texto):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT id_producto, nombre, presentacion, stock, costo_uni_pen, precio_uni_pen, COALESCE(codigo_barras, '')
                    FROM productos
                    WHERE nombre LIKE %s OR codigo_barras = %s OR id_producto = %s OR codigo_producto LIKE %s
                    ORDER BY orden ASC
                    LIMIT 20
                """, (f"%{texto}%", texto, texto if texto.isdigit() else -1, f"%{texto}%"))
                filas = cursor.fetchall()

            if (self.input_buscar.value or "").strip() != texto:
                return

            self.lista_resultados.controls.clear()
            if filas:
                self.lista_resultados.visible = True
                for f in filas:
                    id_p, nom, pres, st, c_pen, p_pen, cb = f
                    c_val = float(c_pen or 0.0)
                    p_val = float(p_pen or 0.0)
                    sub = f"Pres: {pres} | Stock: {st} | Costo Uni: S/ {c_val:.2f} | P. Uni: S/ {p_val:.2f}"
                    if cb:
                        sub += f" | CB: {cb}"
                    self.lista_resultados.controls.append(
                        ft.ListTile(
                            leading=ft.Icon(ft.icons.INVENTORY_2, color="#2563EB", size=20),
                            title=ft.Text(f"{nom}", weight=ft.FontWeight.BOLD, size=13),
                            subtitle=ft.Text(sub, size=11, color="#64748B"),
                            on_click=lambda _, pid=id_p: self.abrir_ventana_emergente_ingreso(pid)
                        )
                    )
            else:
                self.lista_resultados.visible = False
            self.page.update()
        except Exception as ex:
            print(f"Error búsqueda ingresos: {ex}")

    def buscar_y_abrir_emergente_inmediato(self, e):
        texto = (self.input_buscar.value or "").strip()
        if not texto:
            return
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT id_producto FROM productos
                    WHERE codigo_barras = %s OR id_producto = %s
                    LIMIT 1
                """, (texto, texto if texto.isdigit() else -1))
                prod = cursor.fetchone()

            if prod:
                self.abrir_ventana_emergente_ingreso(prod[0])
                self.input_buscar.value = ""
                self.lista_resultados.visible = False
                self.page.update()
            else:
                self.buscar_dinamico(e)
        except Exception as ex:
            print(f"Error buscar directo: {ex}")

    # ── VENTANA EMERGENTE PARA COMPLETAR COSTOS Y PRECIOS (UNIDAD, SIX, ETC.) ─
    def abrir_ventana_emergente_ingreso(self, id_producto, foco_seccion=None):
        """Abre el diálogo modal emergente donde se completan todos los costos y precios del producto."""
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT id_producto, nombre, presentacion, stock, COALESCE(codigo_barras, ''),
                           costo_uni_pen, costo_uni_usd, costo_pack4_pen, costo_pack4_usd,
                           costo_six_pen, costo_six_usd, costo_caja_pen, costo_caja_usd,
                           costo_pack15_pen, costo_pack15_usd, costo_plancha_pen, costo_plancha_usd,
                           precio_uni_pen, precio_uni_usd, precio_pack4_pen, precio_pack4_usd,
                           precio_six_pen, precio_six_usd, precio_caja_pen, precio_caja_usd,
                           precio_pack15_pen, precio_pack15_usd, precio_plancha_pen, precio_plancha_usd
                    FROM productos WHERE id_producto = %s
                """, (id_producto,))
                datos = cursor.fetchone()

            if not datos:
                self.page.open(ft.SnackBar(ft.Text("Producto no encontrado en base de datos."), bgcolor=ft.colors.RED))
                return

            (id_p, nom, pres, stock_actual, cod_barras,
             c_u_pen, c_u_usd, c_p4_pen, c_p4_usd, c_s_pen, c_s_usd, c_c_pen, c_c_usd, c_p15_pen, c_p15_usd, c_pl_pen, c_pl_usd,
             p_u_pen, p_u_usd, p_p4_pen, p_p4_usd, p_s_pen, p_s_usd, p_c_pen, p_c_usd, p_p15_pen, p_p15_usd, p_pl_pen, p_pl_usd) = datos

        except Exception as ex:
            self.page.open(ft.SnackBar(ft.Text(f"Error consultando producto: {ex}"), bgcolor=ft.colors.RED))
            return

        # Si el producto ya está en el carrito, cargar los valores que ya tenía editados en memoria
        item_existente = next((it for it in self.carrito_items if it["id_producto"] == id_p), None)
        cant_inicial = "1"
        if item_existente:
            cant_inicial = str(item_existente["cantidad_val"])
            valores_costo = item_existente["costos"]
            valores_precio = item_existente["precios"]
        else:
            valores_costo = {
                "c_u_pen": float(c_u_pen or 0.0), "c_u_usd": float(c_u_usd or 0.0),
                "c_s_pen": float(c_s_pen or 0.0), "c_s_usd": float(c_s_usd or 0.0),
                "c_c_pen": float(c_c_pen or 0.0), "c_c_usd": float(c_c_usd or 0.0),
                "c_p4_pen": float(c_p4_pen or 0.0), "c_p4_usd": float(c_p4_usd or 0.0),
                "c_p15_pen": float(c_p15_pen or 0.0), "c_p15_usd": float(c_p15_usd or 0.0),
                "c_pl_pen": float(c_pl_pen or 0.0), "c_pl_usd": float(c_pl_usd or 0.0),
            }
            valores_precio = {
                "p_u_pen": float(p_u_pen or 0.0), "p_u_usd": float(p_u_usd or 0.0),
                "p_s_pen": float(p_s_pen or 0.0), "p_s_usd": float(p_s_usd or 0.0),
                "p_c_pen": float(p_c_pen or 0.0), "p_c_usd": float(p_c_usd or 0.0),
                "p_p4_pen": float(p_p4_pen or 0.0), "p_p4_usd": float(p_p4_usd or 0.0),
                "p_p15_pen": float(p_p15_pen or 0.0), "p_p15_usd": float(p_p15_usd or 0.0),
                "p_pl_pen": float(p_pl_pen or 0.0), "p_pl_usd": float(p_pl_usd or 0.0),
            }

        # Controles editables del diálogo
        input_cant_ing = ft.TextField(
            label="Cantidad a Ingresar (Stock Ingresado)",
            value=cant_inicial,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_size=14,
            height=42,
            dense=True,
            border_color="#2563EB",
            col={"sm": 12, "md": 6}
        )

        def campo_num(label, val, col_md=2):
            return ft.TextField(
                label=label,
                value=f"{val:.2f}",
                keyboard_type=ft.KeyboardType.NUMBER,
                text_size=12,
                height=38,
                dense=True,
                border_color="#CBD5E1",
                col={"sm": 6, "md": col_md}
            )

        # Campos de Costos
        ctrl_c_u_pen = campo_num("C. Unid (S/)", valores_costo["c_u_pen"])
        ctrl_c_u_usd = campo_num("C. Unid ($)", valores_costo["c_u_usd"])
        ctrl_c_s_pen = campo_num("C. Six (S/)", valores_costo["c_s_pen"])
        ctrl_c_s_usd = campo_num("C. Six ($)", valores_costo["c_s_usd"])
        ctrl_c_c_pen = campo_num("C. Caja (S/)", valores_costo["c_c_pen"])
        ctrl_c_c_usd = campo_num("C. Caja ($)", valores_costo["c_c_usd"])

        ctrl_c_p4_pen = campo_num("C. Pck4 (S/)", valores_costo["c_p4_pen"])
        ctrl_c_p4_usd = campo_num("C. Pck4 ($)", valores_costo["c_p4_usd"])
        ctrl_c_p15_pen = campo_num("C. Pck15 (S/)", valores_costo["c_p15_pen"])
        ctrl_c_p15_usd = campo_num("C. Pck15 ($)", valores_costo["c_p15_usd"])
        ctrl_c_pl_pen = campo_num("C. Plan (S/)", valores_costo["c_pl_pen"])
        ctrl_c_pl_usd = campo_num("C. Plan ($)", valores_costo["c_pl_usd"])

        # Campos de Precios de Venta
        ctrl_p_u_pen = campo_num("P. Unid (S/)", valores_precio["p_u_pen"])
        ctrl_p_u_usd = campo_num("P. Unid ($)", valores_precio["p_u_usd"])
        ctrl_p_s_pen = campo_num("P. Six (S/)", valores_precio["p_s_pen"])
        ctrl_p_s_usd = campo_num("P. Six ($)", valores_precio["p_s_usd"])
        ctrl_p_c_pen = campo_num("P. Caja (S/)", valores_precio["p_c_pen"])
        ctrl_p_c_usd = campo_num("P. Caja ($)", valores_precio["p_c_usd"])

        ctrl_p_p4_pen = campo_num("P. Pck4 (S/)", valores_precio["p_p4_pen"])
        ctrl_p_p4_usd = campo_num("P. Pck4 ($)", valores_precio["p_p4_usd"])
        ctrl_p_p15_pen = campo_num("P. Pck15 (S/)", valores_precio["p_p15_pen"])
        ctrl_p_p15_usd = campo_num("P. Pck15 ($)", valores_precio["p_p15_usd"])
        ctrl_p_pl_pen = campo_num("P. Plan (S/)", valores_precio["p_pl_pen"])
        ctrl_p_pl_usd = campo_num("P. Plan ($)", valores_precio["p_pl_usd"])

        def to_float(ctrl):
            try:
                return max(0.0, float(ctrl.value or 0.0))
            except Exception:
                return 0.0

        def guardar_desde_emergente(e):
            try:
                cant_val = int(input_cant_ing.value or 1)
                if cant_val <= 0:
                    self.page.open(ft.SnackBar(ft.Text("La cantidad a ingresar debe ser mayor a 0."), bgcolor=ft.colors.RED))
                    return
            except Exception:
                self.page.open(ft.SnackBar(ft.Text("Ingresa una cantidad numérica válida."), bgcolor=ft.colors.RED))
                return

            costos_dict = {
                "c_u_pen": to_float(ctrl_c_u_pen), "c_u_usd": to_float(ctrl_c_u_usd),
                "c_s_pen": to_float(ctrl_c_s_pen), "c_s_usd": to_float(ctrl_c_s_usd),
                "c_c_pen": to_float(ctrl_c_c_pen), "c_c_usd": to_float(ctrl_c_c_usd),
                "c_p4_pen": to_float(ctrl_c_p4_pen), "c_p4_usd": to_float(ctrl_c_p4_usd),
                "c_p15_pen": to_float(ctrl_c_p15_pen), "c_p15_usd": to_float(ctrl_c_p15_usd),
                "c_pl_pen": to_float(ctrl_c_pl_pen), "c_pl_usd": to_float(ctrl_c_pl_usd),
            }

            precios_dict = {
                "p_u_pen": to_float(ctrl_p_u_pen), "p_u_usd": to_float(ctrl_p_u_usd),
                "p_s_pen": to_float(ctrl_p_s_pen), "p_s_usd": to_float(ctrl_p_s_usd),
                "p_c_pen": to_float(ctrl_p_c_pen), "p_c_usd": to_float(ctrl_p_c_usd),
                "p_p4_pen": to_float(ctrl_p_p4_pen), "p_p4_usd": to_float(ctrl_p_p4_usd),
                "p_p15_pen": to_float(ctrl_p_p15_pen), "p_p15_usd": to_float(ctrl_p_p15_usd),
                "p_pl_pen": to_float(ctrl_p_pl_pen), "p_pl_usd": to_float(ctrl_p_pl_usd),
            }

            self.agregar_o_actualizar_carrito(
                id_prod=id_p,
                nombre=nom,
                presentacion=pres,
                stock_act=stock_actual,
                cantidad=cant_val,
                costos=costos_dict,
                precios=precios_dict
            )
            self.page.close(dlg_emergente)
            self.limpiar_busqueda()

        dlg_emergente = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.icons.TUNE, color="#2563EB", size=24),
                ft.Text(f"Ingreso y Precios: {nom}", weight=ft.FontWeight.BOLD, size=16),
            ], spacing=8),
            content=ft.Container(
                width=880,
                content=ft.Column([
                    ft.Container(
                        bgcolor="#F1F5F9",
                        padding=10,
                        border_radius=8,
                        content=ft.ResponsiveRow([
                            ft.Text(f"ID: #{id_p} | Pres: {pres} | Stock Actual: {stock_actual} uds", size=13, weight=ft.FontWeight.BOLD, color="#334155", col={"sm": 12, "md": 6}),
                            input_cant_ing
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
                    ),
                    ft.Divider(height=10),
                    # Sección Costos de Compra
                    ft.Row([
                        ft.Icon(ft.icons.PAYMENTS, color=ft.colors.RED_700, size=18),
                        ft.Text("COSTOS DE COMPRA (Inversión / Lote)", weight=ft.FontWeight.BOLD, color=ft.colors.RED_700, size=13),
                    ], spacing=6),
                    ft.Text("Ingresa los costos de compra actualizados para unidad, six, caja y demás presentaciones:", size=11, color="#64748B"),
                    ft.ResponsiveRow([ctrl_c_u_pen, ctrl_c_u_usd, ctrl_c_s_pen, ctrl_c_s_usd, ctrl_c_c_pen, ctrl_c_c_usd]),
                    ft.ResponsiveRow([ctrl_c_p4_pen, ctrl_c_p4_usd, ctrl_c_p15_pen, ctrl_c_p15_usd, ctrl_c_pl_pen, ctrl_c_pl_usd]),
                    ft.Divider(height=10),
                    # Sección Precios de Venta
                    ft.Row([
                        ft.Icon(ft.icons.SELL, color=ft.colors.GREEN_700, size=18),
                        ft.Text("PRECIOS DE VENTA (Público)", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_700, size=13),
                    ], spacing=6),
                    ft.Text("Fija o actualiza los precios de venta al cliente para unidad, six, caja y demás presentaciones:", size=11, color="#64748B"),
                    ft.ResponsiveRow([ctrl_p_u_pen, ctrl_p_u_usd, ctrl_p_s_pen, ctrl_p_s_usd, ctrl_p_c_pen, ctrl_p_c_usd]),
                    ft.ResponsiveRow([ctrl_p_p4_pen, ctrl_p_p4_usd, ctrl_p_p15_pen, ctrl_p_p15_usd, ctrl_p_pl_pen, ctrl_p_pl_usd]),
                ], scroll=ft.ScrollMode.AUTO, tight=True, spacing=6)
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.close(dlg_emergente)),
                ft.ElevatedButton(
                    "Guardar en Ingreso",
                    icon=ft.icons.CHECK,
                    bgcolor="#10B981",
                    color=ft.colors.WHITE,
                    on_click=guardar_desde_emergente
                )
            ]
        )
        self.page.open(dlg_emergente)

    # ── AGREGAR O ACTUALIZAR EN LA TABLA PRINCIPAL DEL CARRITO ───────────────
    def agregar_o_actualizar_carrito(self, id_prod, nombre, presentacion, stock_act, cantidad, costos, precios):
        existente = next((it for it in self.carrito_items if it["id_producto"] == id_prod), None)
        if existente:
            existente["cantidad_val"] = cantidad
            existente["costos"] = costos
            existente["precios"] = precios
            existente["input_cant"].value = str(cantidad)
            self.actualizar_celdas_item(existente)
        else:
            nuevo_item = {
                "id_producto": id_prod,
                "nombre": nombre,
                "presentacion": presentacion,
                "stock_actual": stock_act,
                "cantidad_val": cantidad,
                "costos": costos,
                "precios": precios
            }

            # Controles en fila de la tabla
            input_cant = ft.TextField(
                value=str(cantidad), width=50, height=34, text_size=12, dense=True,
                text_align=ft.TextAlign.CENTER, keyboard_type=ft.KeyboardType.NUMBER
            )
            nuevo_item["input_cant"] = input_cant

            btn_menos = ft.IconButton(
                icon=ft.icons.REMOVE, icon_size=12, width=22, height=22,
                style=ft.ButtonStyle(padding=0), icon_color=ft.colors.RED_700,
                tooltip="Restar 1", on_click=lambda _, it=nuevo_item: self.cambiar_cant(it, -1)
            )
            btn_mas = ft.IconButton(
                icon=ft.icons.ADD, icon_size=12, width=22, height=22,
                style=ft.ButtonStyle(padding=0), icon_color=ft.colors.GREEN_700,
                tooltip="Sumar 1", on_click=lambda _, it=nuevo_item: self.cambiar_cant(it, 1)
            )
            celda_cant = ft.Row([btn_menos, input_cant, btn_mas], spacing=2, alignment=ft.MainAxisAlignment.CENTER)

            # Evento al tipear directamente en el input de cantidad
            def on_change_cant(e, it=nuevo_item):
                try:
                    v = int(it["input_cant"].value or 1)
                    it["cantidad_val"] = max(1, v)
                except Exception:
                    it["cantidad_val"] = 1
                self.actualizar_celdas_item(it)
                self.recalcular_totales()
            input_cant.on_change = on_change_cant

            # Controles para Precios y Costos en la tabla
            lbl_costo_uni = ft.Text(f"S/ {costos['c_u_pen']:.2f}", size=12, weight=ft.FontWeight.BOLD, color=ft.colors.RED_700)
            btn_costos_popup = ft.IconButton(
                icon=ft.icons.TUNE, icon_size=15, width=24, height=24, icon_color="#64748B",
                tooltip=f"Ver/Editar Costos (Six: S/{costos['c_s_pen']:.2f}, Caja: S/{costos['c_c_pen']:.2f}...)",
                on_click=lambda _, pid=id_prod: self.abrir_ventana_emergente_ingreso(pid)
            )
            celda_costo = ft.Row([lbl_costo_uni, btn_costos_popup], spacing=2)

            lbl_precio_uni = ft.Text(f"S/ {precios['p_u_pen']:.2f}", size=12, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_700)
            btn_precios_popup = ft.IconButton(
                icon=ft.icons.SELL, icon_size=15, width=24, height=24, icon_color="#64748B",
                tooltip=f"Ver/Editar Precios (Six: S/{precios['p_s_pen']:.2f}, Caja: S/{precios['p_c_pen']:.2f}...)",
                on_click=lambda _, pid=id_prod: self.abrir_ventana_emergente_ingreso(pid)
            )
            celda_precio = ft.Row([lbl_precio_uni, btn_precios_popup], spacing=2)

            sub_val = cantidad * costos["c_u_pen"]
            lbl_subtotal = ft.Text(f"S/ {sub_val:.2f}", size=12, weight=ft.FontWeight.BOLD, color="#1E293B")

            btn_editar_completo = ft.IconButton(
                icon=ft.icons.EDIT_NOTE, icon_size=18, icon_color="#2563EB",
                tooltip="Abrir Ventana Emergente Completa",
                on_click=lambda _, pid=id_prod: self.abrir_ventana_emergente_ingreso(pid)
            )
            btn_eliminar = ft.IconButton(
                icon=ft.icons.DELETE_OUTLINE, icon_size=18, icon_color=ft.colors.RED_600,
                tooltip="Quitar del ingreso",
                on_click=lambda _, it=nuevo_item: self.quitar_item(it)
            )
            celda_acciones = ft.Row([btn_editar_completo, btn_eliminar], spacing=0)

            nuevo_item["lbl_costo_uni"] = lbl_costo_uni
            nuevo_item["btn_costos_popup"] = btn_costos_popup
            nuevo_item["lbl_precio_uni"] = lbl_precio_uni
            nuevo_item["btn_precios_popup"] = btn_precios_popup
            nuevo_item["lbl_subtotal"] = lbl_subtotal

            fila_tabla = ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(id_prod), size=12)),
                ft.DataCell(ft.Column([
                    ft.Text(nombre, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, size=12, weight=ft.FontWeight.BOLD),
                    ft.Text(f"{presentacion} | Stock: {stock_act}", size=10, color="#64748B")
                ], spacing=1, alignment=ft.MainAxisAlignment.CENTER)),
                ft.DataCell(celda_cant),
                ft.DataCell(celda_costo),
                ft.DataCell(celda_precio),
                ft.DataCell(lbl_subtotal),
                ft.DataCell(celda_acciones)
            ])

            nuevo_item["fila_tabla"] = fila_tabla
            self.carrito_items.append(nuevo_item)
            self.tabla_carrito.rows.append(fila_tabla)

        self.recalcular_totales()
        self.page.update()

    def actualizar_celdas_item(self, item):
        costos = item["costos"]
        precios = item["precios"]
        cant = item["cantidad_val"]
        item["lbl_costo_uni"].value = f"S/ {costos['c_u_pen']:.2f}"
        item["btn_costos_popup"].tooltip = f"Costos: Unid S/{costos['c_u_pen']:.2f} | Six S/{costos['c_s_pen']:.2f} | Caja S/{costos['c_c_pen']:.2f}"
        item["lbl_precio_uni"].value = f"S/ {precios['p_u_pen']:.2f}"
        item["btn_precios_popup"].tooltip = f"Precios: Unid S/{precios['p_u_pen']:.2f} | Six S/{precios['p_s_pen']:.2f} | Caja S/{precios['p_c_pen']:.2f}"
        sub = cant * costos["c_u_pen"]
        item["lbl_subtotal"].value = f"S/ {sub:.2f}"

    def cambiar_cant(self, item, delta):
        item["cantidad_val"] = max(1, item["cantidad_val"] + delta)
        item["input_cant"].value = str(item["cantidad_val"])
        self.actualizar_celdas_item(item)
        self.recalcular_totales()
        self.page.update()

    def quitar_item(self, item):
        if item in self.carrito_items:
            self.carrito_items.remove(item)
            if item["fila_tabla"] in self.tabla_carrito.rows:
                self.tabla_carrito.rows.remove(item["fila_tabla"])
            self.recalcular_totales()
            self.page.update()

    def vaciar_carrito(self, e=None):
        self.carrito_items.clear()
        self.tabla_carrito.rows.clear()
        self.recalcular_totales()
        self.page.update()

    def recalcular_totales(self):
        total_items = len(self.carrito_items)
        total_unidades = sum(it["cantidad_val"] for it in self.carrito_items)
        total_costo = sum(it["cantidad_val"] * it["costos"]["c_u_pen"] for it in self.carrito_items)

        self.banner_vacio.visible = (total_items == 0)
        self.tabla_carrito.visible = (total_items > 0)

        self.lbl_resumen_items.value = str(total_items)
        self.lbl_resumen_unidades.value = f"{total_unidades} uds"
        self.lbl_resumen_total_costo.value = f"S/ {total_costo:.2f}"
        self.page.update()

    # ── LÓGICA TRANSACCIONAL DE INGRESO ──────────────────────────────────────
    def confirmar_ingreso_click(self, e):
        if not self.tiene_permiso():
            return
        if not self.carrito_items:
            self.page.open(ft.SnackBar(ft.Text("⚠️ El carrito de compras está vacío. Agrega al menos un producto."), bgcolor=ft.colors.ORANGE_800))
            return

        if self.fn_solicitar_password:
            self.fn_solicitar_password(self.ejecutar_transaccion_ingreso)
        else:
            self.ejecutar_transaccion_ingreso()

    def ejecutar_transaccion_ingreso(self):
        boton = self.btn_confirmar_ingreso
        boton.disabled = True
        boton.text = "Guardando ingreso..."
        self.page.update()

        f_doc = fecha_local()
        h_doc = hora_local().strftime("%H:%M:%S")
        usr = getattr(self.page, 'nombre_usuario', None) or getattr(self.page, 'rol_usuario', None) or "ADMIN"
        comentarios = (self.input_comentarios_doc.value or "").strip()
        ts_local_str = ahora_local().strftime("%Y-%m-%d %H:%M:%S")

        total_lineas = len(self.carrito_items)
        total_uds = sum(it["cantidad_val"] for it in self.carrito_items)
        costo_total_doc = sum(it["cantidad_val"] * it["costos"]["c_u_pen"] for it in self.carrito_items)

        try:
            with obtener_cursor(commit=True) as cursor:
                # 1. Insertar Cabecera de Ingreso
                cursor.execute("""
                    INSERT INTO ingresos_cabecera (fecha, hora, usuario, comentarios, total_articulos, costo_total)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (f_doc, h_doc, str(usr).upper(), comentarios, total_lineas, costo_total_doc))
                id_ingreso = cursor.lastrowid

                # 2. Iterar items para detalle, bloqueo FOR UPDATE y actualización completa de productos
                for it in self.carrito_items:
                    id_prod = it["id_producto"]
                    cant = it["cantidad_val"]
                    costos = it["costos"]
                    precios = it["precios"]
                    sub_costo = cant * costos["c_u_pen"]

                    # Snapshot JSON de todos los precios fijados para auditoría
                    snapshot_precios = json.dumps({
                        "costos": costos,
                        "precios": precios
                    })

                    # Bloqueo pesimista para evitar condiciones de carrera concurrentes
                    cursor.execute("""
                        SELECT stock, nombre FROM productos WHERE id_producto = %s FOR UPDATE
                    """, (id_prod,))
                    fila_bd = cursor.fetchone()
                    if not fila_bd:
                        raise ValueError(f"El producto ID {id_prod} no existe en la base de datos.")

                    # Insertar Detalle de Ingreso
                    cursor.execute("""
                        INSERT INTO ingresos_detalle (
                            id_ingreso, id_producto, cantidad, costo_unitario, precio_actualizado, subtotal_costo, detalles_precios
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (id_ingreso, id_prod, cant, costos["c_u_pen"], precios["p_u_pen"], sub_costo, snapshot_precios))

                    # Actualizar Stock y TODOS los costos y precios de venta en la tabla productos
                    cursor.execute("""
                        UPDATE productos
                        SET stock = stock + %s,
                            costo_uni_pen = %s, costo_uni_usd = %s,
                            costo_pack4_pen = %s, costo_pack4_usd = %s,
                            costo_six_pen = %s, costo_six_usd = %s,
                            costo_caja_pen = %s, costo_caja_usd = %s,
                            costo_pack15_pen = %s, costo_pack15_usd = %s,
                            costo_plancha_pen = %s, costo_plancha_usd = %s,
                            precio_uni_pen = %s, precio_uni_usd = %s,
                            precio_pack4_pen = %s, precio_pack4_usd = %s,
                            precio_six_pen = %s, precio_six_usd = %s,
                            precio_caja_pen = %s, precio_caja_usd = %s,
                            precio_pack15_pen = %s, precio_pack15_usd = %s,
                            precio_plancha_pen = %s, precio_plancha_usd = %s
                        WHERE id_producto = %s
                    """, (
                        cant,
                        costos["c_u_pen"], costos["c_u_usd"],
                        costos["c_p4_pen"], costos["c_p4_usd"],
                        costos["c_s_pen"], costos["c_s_usd"],
                        costos["c_c_pen"], costos["c_c_usd"],
                        costos["c_p15_pen"], costos["c_p15_usd"],
                        costos["c_pl_pen"], costos["c_pl_usd"],
                        precios["p_u_pen"], precios["p_u_usd"],
                        precios["p_p4_pen"], precios["p_p4_usd"],
                        precios["p_s_pen"], precios["p_s_usd"],
                        precios["p_c_pen"], precios["p_c_usd"],
                        precios["p_p15_pen"], precios["p_p15_usd"],
                        precios["p_pl_pen"], precios["p_pl_usd"],
                        id_prod
                    ))

                    # Kardex histórico sincronizado
                    cursor.execute("""
                        INSERT INTO historial_ingresos (id_producto, cantidad, destino, comentarios, fecha_ingreso)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (id_prod, cant, "INVENTARIO TIENDA (Lote de Ingreso)", f"Ingreso Doc #ING-{id_ingreso:05d}: {comentarios}", ts_local_str))

            # Transacción completada con éxito
            self.vaciar_carrito()
            self.input_comentarios_doc.value = ""

            if self.fn_recargar_inventario:
                try:
                    self.fn_recargar_inventario()
                except Exception:
                    pass

            self.page.open(ft.SnackBar(
                ft.Text(f"✅ Lote de ingreso #ING-{id_ingreso:05d} registrado exitosamente ({total_uds} unidades ingresadas).", color=ft.colors.WHITE),
                bgcolor=ft.colors.GREEN,
                duration=4000
            ))

        except Exception as ex:
            print(f"Error transaccional en ingreso de mercadería: {ex}")
            self.page.open(ft.SnackBar(
                ft.Text(f"❌ Error al registrar ingreso: {ex}", color=ft.colors.WHITE),
                bgcolor=ft.colors.RED,
                duration=5000
            ))
        finally:
            boton.disabled = False
            boton.text = "Confirmar Ingreso de Stock"
            self.page.update()

    # ── REGISTRO DE INGRESOS (HISTORIAL INMUTABLE - SOLO LECTURA) ─────────────
    def cargar_registro_ingresos(self):
        """Carga los documentos registrados en ingresos_cabecera para visualización únicamente."""
        self.tabla_historial_ingresos.rows.clear()
        filtro = (self.input_buscar_historial.value or "").strip()

        try:
            query = """
                SELECT id_ingreso, fecha, hora, usuario, COALESCE(comentarios, ''), total_articulos, costo_total
                FROM ingresos_cabecera
                WHERE 1=1
            """
            params = []
            if filtro:
                query += " AND (id_ingreso = %s OR usuario LIKE %s OR comentarios LIKE %s)"
                params.extend([filtro if filtro.isdigit() else -1, f"%{filtro}%", f"%{filtro}%"])

            query += " ORDER BY id_ingreso DESC LIMIT 100"

            with obtener_cursor() as cursor:
                cursor.execute(query, tuple(params))
                filas = cursor.fetchall()

            for f in filas:
                id_ing, fec, hor, usr, com, tot_art, c_tot = f
                c_tot_val = float(c_tot or 0.0)

                btn_ver_detalle = ft.IconButton(
                    icon=ft.icons.VISIBILITY,
                    icon_color="#2563EB",
                    tooltip="Ver Detalle del Documento (Solo Lectura)",
                    on_click=lambda _, i=id_ing: self.abrir_visualizador_detalle_ingreso(i)
                )

                self.tabla_historial_ingresos.rows.append(
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(f"#ING-{id_ing:05d}", weight=ft.FontWeight.BOLD, color="#2563EB")),
                        ft.DataCell(ft.Text(str(fec))),
                        ft.DataCell(ft.Text(str(hor)[:8])),
                        ft.DataCell(ft.Text(str(usr))),
                        ft.DataCell(ft.Text(com or "Sin comentarios", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)),
                        ft.DataCell(ft.Text(f"{tot_art} ítems")),
                        ft.DataCell(ft.Text(f"S/ {c_tot_val:.2f}", weight=ft.FontWeight.BOLD, color="#10B981")),
                        ft.DataCell(btn_ver_detalle)
                    ])
                )
            self.page.update()
        except Exception as ex:
            print(f"Error cargando registro de ingresos: {ex}")
            self.page.open(ft.SnackBar(ft.Text(f"Error al cargar registro de ingresos: {ex}"), bgcolor=ft.colors.RED))

    def abrir_visualizador_detalle_ingreso(self, id_ingreso):
        """Ventana emergente de SOLO LECTURA para visualizar el desglose del documento de ingreso."""
        try:
            with obtener_cursor() as cursor:
                # Cabecera
                cursor.execute("""
                    SELECT id_ingreso, fecha, hora, usuario, COALESCE(comentarios, ''), total_articulos, costo_total
                    FROM ingresos_cabecera WHERE id_ingreso = %s
                """, (id_ingreso,))
                cab = cursor.fetchone()

                if not cab:
                    self.page.open(ft.SnackBar(ft.Text("Documento no encontrado."), bgcolor=ft.colors.RED))
                    return

                # Detalle
                cursor.execute("""
                    SELECT d.id_producto, p.nombre, p.presentacion, d.cantidad, d.costo_unitario, d.precio_actualizado, d.subtotal_costo, d.detalles_precios
                    FROM ingresos_detalle d
                    JOIN productos p ON d.id_producto = p.id_producto
                    WHERE d.id_ingreso = %s
                    ORDER BY d.id_detalle ASC
                """, (id_ingreso,))
                detalles = cursor.fetchall()

            id_ing, fec, hor, usr, com, tot_art, c_tot = cab
            c_tot_val = float(c_tot or 0.0)

            filas_detalle = []
            correlativo = 1
            for d in detalles:
                id_p, p_nom, p_pres, d_cant, d_costo, d_precio, d_sub, d_json = d
                costo_u = float(d_costo or 0.0)
                precio_u = float(d_precio or 0.0)
                sub_u = float(d_sub or 0.0)

                # Tooltip con desglose adicional si existe snapshot
                tip_precios = f"Unid: S/ {precio_u:.2f}"
                if d_json:
                    try:
                        snap = json.loads(d_json)
                        p_snap = snap.get("precios", {})
                        tip_precios = f"Unid S/{p_snap.get('p_u_pen',0):.2f} | Six S/{p_snap.get('p_s_pen',0):.2f} | Caja S/{p_snap.get('p_c_pen',0):.2f}"
                    except Exception:
                        pass

                filas_detalle.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(correlativo))),
                    ft.DataCell(ft.Text(p_nom, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)),
                    ft.DataCell(ft.Text(str(p_pres))),
                    ft.DataCell(ft.Text(f"{d_cant} uds", weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(f"S/ {costo_u:.2f}", color=ft.colors.RED_700)),
                    ft.DataCell(ft.Text(f"S/ {precio_u:.2f}", color=ft.colors.GREEN_700, tooltip=tip_precios)),
                    ft.DataCell(ft.Text(f"S/ {sub_u:.2f}", weight=ft.FontWeight.BOLD))
                ]))
                correlativo += 1

            tabla_dlg = ft.DataTable(
                heading_row_color="#F1F5F9",
                border=ft.border.all(1, "#E2E8F0"),
                border_radius=8,
                column_spacing=12,
                columns=[
                    ft.DataColumn(ft.Text("#", weight=ft.FontWeight.BOLD)),
                    ft.DataColumn(ft.Text("Prod.", weight=ft.FontWeight.BOLD)),
                    ft.DataColumn(ft.Text("Pres.", weight=ft.FontWeight.BOLD)),
                    ft.DataColumn(ft.Text("Cant. Ing.", weight=ft.FontWeight.BOLD)),
                    ft.DataColumn(ft.Text("C. Unid (S/)", weight=ft.FontWeight.BOLD)),
                    ft.DataColumn(ft.Text("P. Venta (S/)", weight=ft.FontWeight.BOLD)),
                    ft.DataColumn(ft.Text("Subtotal", weight=ft.FontWeight.BOLD)),
                ],
                rows=filas_detalle
            )

            dlg_visor = ft.AlertDialog(
                title=ft.Row([
                    ft.Icon(ft.icons.RECEIPT_LONG, color="#2563EB", size=24),
                    ft.Text(f"Documento de Ingreso #ING-{id_ing:05d} (Solo Lectura)", weight=ft.FontWeight.BOLD, size=16),
                ], spacing=8),
                content=ft.Container(
                    width=850,
                    content=ft.Column([
                        ft.Container(
                            bgcolor="#F8FAFC",
                            padding=12,
                            border_radius=8,
                            border=ft.border.all(1, "#E2E8F0"),
                            content=ft.ResponsiveRow([
                                ft.Text(f"Fecha: {fec}   Hora: {str(hor)[:8]}", weight=ft.FontWeight.BOLD, color="#1E293B", col={"sm": 12, "md": 6}),
                                ft.Text(f"Registrado por: {usr}", weight=ft.FontWeight.BOLD, color="#1E293B", col={"sm": 12, "md": 6}),
                                ft.Text(f"Comentarios / Guía: {com or 'Ninguno'}", color="#64748B", col={"sm": 12}),
                                ft.Text(f"Inversión Total: S/ {c_tot_val:.2f} ({tot_art} líneas registradas)", weight=ft.FontWeight.BOLD, color="#10B981", col={"sm": 12}),
                            ])
                        ),
                        ft.Divider(height=10),
                        ft.Text("Desglose de Mercadería Ingresada:", size=13, weight=ft.FontWeight.BOLD, color="#334155"),
                        ft.Column([tabla_dlg], scroll=ft.ScrollMode.AUTO, height=320)
                    ], scroll=ft.ScrollMode.AUTO, tight=True, spacing=8)
                ),
                actions=[
                    ft.ElevatedButton(
                        "Cerrar",
                        bgcolor="#1E293B",
                        color=ft.colors.WHITE,
                        on_click=lambda _: self.page.close(dlg_visor)
                    )
                ]
            )
            self.page.open(dlg_visor)
        except Exception as ex:
            print(f"Error abriendo visor de ingreso: {ex}")
            self.page.open(ft.SnackBar(ft.Text(f"Error: {ex}"), bgcolor=ft.colors.RED))
