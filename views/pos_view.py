import flet as ft
import textwrap
import datetime
import threading
from num2words import num2words
from database import obtener_cursor
from pdf_generator import exportar_ticket_pdf
from time_service import ahora_local, fecha_local, hora_local

# Factores de conversión de empaque a unidades físicas
MULT_MAP = {
    "Unidad": 1,
    "Pack-4": 4,
    "Six-pack": 6,
    "Caja": 12,
    "Pack-15": 15,
    "Plancha": 24,
    "Mix Six": 1,
    "Mix Caj": 1,
    "Mix Pla": 1
}

class PosView(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self.visible = True
        self.padding = 20

        # Estado nativo OOP (reemplaza [None] y variables globales)
        self.timer_cliente = None
        self.timer_buscar_pos = None
        self.condicion_cobro_estado = "Contado"
        
        self.surtidor_items = []
        self.surtidor_estado = {
            "requeridas": 0,
            "seleccionadas": 0,
            "precio_u_pen": 0.0,
            "precio_u_usd": 0.0,
            "empaque_base": ""
        }

        # Estilos visuales
        self.estilo_tarjeta = {
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
        self.estilo_input = {
            "border_color": "#CBD5E1",
            "focused_border_color": "#2563EB",
            "border_radius": 8,
            "dense": True,
            "height": 42,
            "text_size": 13
        }

        self.construir_interfaz()

    def construir_interfaz(self):
        # 1. Inputs de Cliente
        self.input_dni = ft.TextField(
            label="DNI/RUC", hint_text="00000000",
            col={"sm": 12, "md": 4, "lg": 3},
            on_change=self.buscar_cliente_historial,
            **self.estilo_input
        )
        self.input_cliente = ft.TextField(
            label="Cliente", hint_text="",
            col={"sm": 12, "md": 8, "lg": 5},
            **self.estilo_input
        )
        self.input_direccion = ft.TextField(
            label="Dirección", value="Tacna",
            col={"sm": 12, "md": 12, "lg": 4},
            **self.estilo_input
        )

        # 2. Controles de Producto
        self.dropdown_empaque = ft.Dropdown(
            label="Empaque",
            options=[
                ft.dropdown.Option("Unidad"), 
                ft.dropdown.Option("Pack-4"), 
                ft.dropdown.Option("Six-pack"), 
                ft.dropdown.Option("Caja"), 
                ft.dropdown.Option("Pack-15"), 
                ft.dropdown.Option("Plancha")
            ],
            value="Unidad",
            col={"sm": 6, "md": 3, "lg": 2},
            **self.estilo_input
        )

        self.btn_cant_menos = ft.IconButton(
            icon=ft.icons.REMOVE, icon_size=16, width=28, height=28,
            style=ft.ButtonStyle(padding=0), icon_color=ft.colors.RED_700,
            tooltip="Restar 1", on_click=self.restar_cant
        )
        self.btn_cant_mas = ft.IconButton(
            icon=ft.icons.ADD, icon_size=16, width=28, height=28,
            style=ft.ButtonStyle(padding=0), icon_color=ft.colors.GREEN_700,
            tooltip="Sumar 1", on_click=self.sumar_cant
        )

        self.input_cantidad = ft.TextField(
            label="Cant.", value="1", keyboard_type=ft.KeyboardType.NUMBER, text_align=ft.TextAlign.CENTER,
            prefix=self.btn_cant_menos,
            suffix=self.btn_cant_mas,
            on_submit=self.agregar_producto,
            col={"sm": 6, "md": 3, "lg": 3},
            **self.estilo_input
        )

        self.input_precio_esp = ft.TextField(
            label="P. Esp.", hint_text="Opcional", keyboard_type=ft.KeyboardType.NUMBER,
            col={"sm": 6, "md": 2, "lg": 2}, on_submit=self.agregar_producto,
            **self.estilo_input
        )
        self.dropdown_moneda = ft.Dropdown(
            label="Moneda",
            options=[ft.dropdown.Option("PEN"), ft.dropdown.Option("USD")],
            value="PEN", col={"sm": 6, "md": 2, "lg": 2},
            **self.estilo_input
        )

        self.btn_agregar = ft.ElevatedButton(
            "Agregar", icon=ft.icons.ADD_SHOPPING_CART,
            style=ft.ButtonStyle(color=ft.colors.WHITE, bgcolor="#10B981", shape=ft.RoundedRectangleBorder(radius=8)),
            height=42, on_click=self.agregar_producto, col={"sm": 12, "md": 2, "lg": 3}
        )

        self.input_observacion = ft.TextField(
            label="Comentarios de la venta (Opcional)", col={"sm": 12},
            **self.estilo_input
        )

        # 3. Búsqueda y Escáner
        self.btn_limpiar_buscar = ft.IconButton(
            icon=ft.icons.CLEAR, icon_size=16, width=26, height=26,
            style=ft.ButtonStyle(padding=0), tooltip="Limpiar",
            on_click=self.limpiar_busqueda
        )
        self.input_buscar = ft.TextField(
            label="Buscar Producto", hint_text="Nombre o ID... [F2: Buscar | F4: Cobrar]",
            on_change=self.buscar_dinamico, on_submit=self.agregar_producto,
            col={"sm": 12, "md": 12, "lg": 12}, prefix_icon=ft.icons.SEARCH,
            suffix=self.btn_limpiar_buscar,
            **self.estilo_input
        )
        self.lista_resultados = ft.ListView(spacing=2, padding=5, visible=False, height=150)

        self.switch_escaner = ft.Switch(
            label="⚡ Modo Escáner Rápido",
            value=False,
            active_color=ft.colors.GREEN_700,
            on_change=self.toggle_escaner,
            tooltip="Agrega productos al instante con lector de código de barras sin tocar el ratón"
        )

        # 4. Carrito y Totales
        self.lbl_total_pen = ft.Text("S/ 0.00", size=32, weight=ft.FontWeight.W_800, color="#059669")
        self.lbl_total_usd = ft.Text("$ 0.00", size=24, weight=ft.FontWeight.BOLD, color="#64748B")

        self.tabla_carrito = ft.DataTable(
            column_spacing=18,
            heading_row_color="#F1F5F9",
            border_radius=8,
            border=ft.border.all(1, "#E2E8F0"),
            data_row_min_height=38,
            data_row_max_height=42,
            columns=[
                ft.DataColumn(ft.Container(ft.Text("ID", color="#475569"), width=30)),
                ft.DataColumn(ft.Container(ft.Text("Descripción", color="#475569"), width=150)),
                ft.DataColumn(ft.Text("Pres.", color="#475569")),
                ft.DataColumn(ft.Text("Tipo", color="#475569")),
                ft.DataColumn(ft.Text("Cant.", color="#475569")),
                ft.DataColumn(ft.Text("P. Unit", color="#475569")),
                ft.DataColumn(ft.Text("Sub (S/)", color="#475569")),
                ft.DataColumn(ft.Text("Sub ($)", color="#475569")),
                ft.DataColumn(ft.Container(ft.Text("Acciones", color="#475569"), width=95)),
            ],
            rows=[]
        )

        # 5. Diálogo Surtidor
        self.lbl_contador_surtidor = ft.Text("Seleccionadas: 0 / 0", size=18, weight=ft.FontWeight.BOLD)
        self.lista_surtidor_ui = ft.Column(scroll=ft.ScrollMode.AUTO, height=250)
        self.btn_confirmar_surtidor = ft.ElevatedButton(
            "Confirmar Combo", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE,
            on_click=self.confirmar_surtidor
        )
        self.dialogo_surtidor = ft.AlertDialog(
            title=ft.Text("Armar Combo Surtido", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=450,
                content=ft.Column([
                    ft.Text("Selecciona los sabores para completar el empaque:", size=13, color=ft.colors.GREY_700),
                    self.lbl_contador_surtidor,
                    ft.Divider(),
                    self.lista_surtidor_ui
                ], tight=True)
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dialogo_surtidor)),
                self.btn_confirmar_surtidor
            ]
        )

        # 6. Diálogo de Cobro y Métodos de Pago
        self.card_cond_contado = ft.Container(
            content=ft.Row([
                ft.Icon(ft.icons.CHECK_CIRCLE, size=18, color="#059669"),
                ft.Text("VENTA AL CONTADO", weight=ft.FontWeight.BOLD, size=12, color="#065F46")
            ], alignment=ft.MainAxisAlignment.CENTER),
            padding=10, border_radius=8, border=ft.border.all(2, "#10B981"),
            bgcolor="#ECFDF5", ink=True,
            on_click=lambda _: self.seleccionar_condicion("Contado"),
            col={"sm": 6, "md": 6}
        )

        self.card_cond_credito = ft.Container(
            content=ft.Row([
                ft.Icon(ft.icons.CREDIT_SCORE, size=18, color="#64748B"),
                ft.Text("VENTA A CRÉDITO", weight=ft.FontWeight.BOLD, size=12, color="#64748B")
            ], alignment=ft.MainAxisAlignment.CENTER),
            padding=10, border_radius=8, border=ft.border.all(1, "#E2E8F0"),
            bgcolor=ft.colors.WHITE, ink=True,
            on_click=lambda _: self.seleccionar_condicion("Crédito"),
            col={"sm": 6, "md": 6}
        )

        self.lbl_resumen_cobro = ft.Text("Total a cobrar: S/ 0.00", size=18, weight=ft.FontWeight.BOLD, color="#065F46")
        self.lbl_vuelto = ft.Text("Faltante: S/ 0.00", size=16, weight=ft.FontWeight.BOLD, color=ft.colors.RED_700)

        self.input_pago_efectivo = ft.TextField(hint_text="0.00", keyboard_type=ft.KeyboardType.NUMBER)
        self.input_pago_yape = ft.TextField(hint_text="0.00", keyboard_type=ft.KeyboardType.NUMBER)
        self.input_pago_transferencia = ft.TextField(hint_text="0.00", keyboard_type=ft.KeyboardType.NUMBER)
        self.input_pago_tarjeta = ft.TextField(hint_text="0.00", keyboard_type=ft.KeyboardType.NUMBER)
        self.input_pago_dolares = ft.TextField(hint_text="0.00", keyboard_type=ft.KeyboardType.NUMBER)

        self.card_pago_efectivo = self.crear_tarjeta_metodo("Efectivo (S/)", ft.icons.PAYMENTS, "#10B981", "#ECFDF5", self.input_pago_efectivo, col_spec={"sm": 12, "md": 4})
        self.card_pago_yape = self.crear_tarjeta_metodo("Yape (S/)", ft.icons.PHONE_ANDROID, "#8B5CF6", "#F5F3FF", self.input_pago_yape, col_spec={"sm": 12, "md": 4})
        self.card_pago_transferencia = self.crear_tarjeta_metodo("Transferencia (S/)", ft.icons.ACCOUNT_BALANCE, "#2563EB", "#EFF6FF", self.input_pago_transferencia, col_spec={"sm": 12, "md": 4})
        self.card_pago_tarjeta = self.crear_tarjeta_metodo("Tarjeta (S/)", ft.icons.CREDIT_CARD, "#F59E0B", "#FFFBEB", self.input_pago_tarjeta, col_spec={"sm": 12, "md": 6})
        self.card_pago_dolares = self.crear_tarjeta_metodo("Dólares ($)", ft.icons.MONETIZATION_ON, "#0D9488", "#F0FDFA", self.input_pago_dolares, col_spec={"sm": 12, "md": 6}, es_dolares=True)

        self.input_pago_efectivo.on_change = self.calcular_vuelto
        self.input_pago_yape.on_change = self.calcular_vuelto
        self.input_pago_transferencia.on_change = self.calcular_vuelto
        self.input_pago_tarjeta.on_change = self.calcular_vuelto
        self.input_pago_dolares.on_change = self.calcular_vuelto

        self.dialogo_cobro = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.icons.POINT_OF_SALE, color="#1E293B", size=24),
                ft.Text("Procesar Cobro de Venta", weight=ft.FontWeight.BOLD, size=18)
            ], spacing=10),
            content=ft.Container(
                width=620,
                content=ft.Column([
                    ft.Container(
                        content=self.lbl_resumen_cobro,
                        padding=10,
                        bgcolor="#F8FAFC",
                        border=ft.border.all(1, "#E2E8F0"),
                        border_radius=8,
                        alignment=ft.alignment.center
                    ),
                    ft.Divider(height=12),
                    ft.Text("1. Condición de Venta:", size=12, weight=ft.FontWeight.BOLD, color=ft.colors.GREY_700),
                    ft.ResponsiveRow([self.card_cond_contado, self.card_cond_credito]),
                    ft.Divider(height=12),
                    ft.Text("2. Métodos de Pago y Montos Recibidos:", size=12, weight=ft.FontWeight.BOLD, color=ft.colors.GREY_700),
                    ft.ResponsiveRow([self.card_pago_efectivo, self.card_pago_yape, self.card_pago_transferencia]),
                    ft.ResponsiveRow([self.card_pago_tarjeta, self.card_pago_dolares]),
                    ft.Divider(height=12),
                    ft.Container(
                        content=self.lbl_vuelto,
                        padding=10,
                        bgcolor="#F8FAFC",
                        border=ft.border.all(1, "#E2E8F0"),
                        border_radius=8,
                        alignment=ft.alignment.center
                    )
                ], tight=True, scroll=ft.ScrollMode.AUTO)
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dialogo_cobro)),
                ft.ElevatedButton("Confirmar Venta", icon=ft.icons.CHECK, bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=self.confirmar_y_guardar_venta)
            ]
        )

        # 7. Construcción de Paneles Izquierdo y Derecho
        self.panel_izquierdo = ft.Container(
            **self.estilo_tarjeta,
            content=ft.Column([
                ft.Row([
                    ft.Text("Terminal de Ventas", size=22, weight=ft.FontWeight.W_700, color="#1E293B"),
                    ft.Container(expand=True),
                    self.switch_escaner
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(color="#E2E8F0", height=20),
                ft.ResponsiveRow([self.input_dni, self.input_cliente, self.input_direccion]),
                ft.Divider(color="#E2E8F0", height=20),
                ft.ResponsiveRow([self.input_buscar]),
                self.lista_resultados,
                ft.ResponsiveRow([self.dropdown_empaque, self.input_cantidad, self.input_precio_esp, self.dropdown_moneda, self.btn_agregar], alignment=ft.MainAxisAlignment.START),
                ft.Container(content=ft.Column([self.tabla_carrito], scroll=ft.ScrollMode.AUTO)),
                ft.ResponsiveRow([self.input_observacion])
            ])
        )

        self.panel_derecho = ft.Container(
            **self.estilo_tarjeta,
            content=ft.Column([
                ft.Text("Resumen", size=18, weight=ft.FontWeight.W_700, color="#1E293B"),
                ft.Divider(color="#E2E8F0"),
                ft.Text("Subtotal (S/):", size=13, color="#64748B"),
                self.lbl_total_pen,
                ft.Container(height=10),
                ft.Text("Subtotal ($):", size=13, color="#64748B"),
                self.lbl_total_usd,
                ft.Divider(color="#E2E8F0"),
                ft.ElevatedButton(
                    "Cobrar Ticket", icon=ft.icons.PAYMENTS,
                    style=ft.ButtonStyle(bgcolor="#3B82F6", color=ft.colors.WHITE, shape=ft.RoundedRectangleBorder(radius=10)),
                    width=float('inf'), height=55, on_click=self.procesar_venta
                )
            ], spacing=5)
        )

        self.content = ft.ResponsiveRow([
            ft.Column([self.panel_izquierdo], col={"sm": 12, "md": 12, "lg": 8, "xl": 9}),
            ft.Column([self.panel_derecho], col={"sm": 12, "md": 12, "lg": 4, "xl": 3})
        ])

    # --- LÓGICA DE CLIENTES ---
    def buscar_cliente_historial(self, e):
        dni = self.input_dni.value.strip()
        if len(dni) >= 8:
            if self.timer_cliente:
                self.timer_cliente.cancel()
            self.timer_cliente = threading.Timer(0.35, lambda: self.ejecutar_buscar_cliente(dni))
            self.timer_cliente.start()

    def ejecutar_buscar_cliente(self, dni):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT cliente_nombre, cliente_direccion FROM ventas WHERE cliente_dni = %s AND cliente_nombre != 'VARIOS' AND cliente_nombre != '' ORDER BY id_venta DESC LIMIT 1", (dni,))
                cliente = cursor.fetchone()
                if cliente:
                    self.input_cliente.value = cliente[0]
                    self.input_direccion.value = cliente[1]
                    self.page.update()
        except Exception as ex:
            print(f"Error cliente: {ex}")

    # --- LÓGICA DE BÚSQUEDA Y ESCÁNER ---
    def limpiar_busqueda(self, e):
        self.input_buscar.value = ""
        self.lista_resultados.visible = False
        self.page.update()

    def toggle_escaner(self, e):
        if self.switch_escaner.value:
            self.input_buscar.focus()
            self.page.open(ft.SnackBar(ft.Text("⚡ Modo Escáner Rápido activado. Escanea códigos continuamente."), bgcolor=ft.colors.BLUE_700, duration=2000))
        self.page.update()

    def seleccionar_autocompletado(self, nombre):
        self.input_buscar.value = nombre
        self.lista_resultados.visible = False
        self.page.update()

    def buscar_dinamico(self, e):
        busqueda = self.input_buscar.value.strip()
        if len(busqueda) < 2:
            if self.timer_buscar_pos:
                self.timer_buscar_pos.cancel()
            self.lista_resultados.controls.clear()
            self.lista_resultados.visible = False
            self.page.update()
            return

        if self.timer_buscar_pos:
            self.timer_buscar_pos.cancel()
        self.timer_buscar_pos = threading.Timer(0.3, lambda: self.ejecutar_busqueda_dinamica(busqueda))
        self.timer_buscar_pos.start()

    def ejecutar_busqueda_dinamica(self, busqueda):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT id_producto, nombre, presentacion, stock, precio_uni_pen 
                    FROM productos 
                    WHERE nombre LIKE %s OR id_producto = %s OR codigo_barras = %s
                    ORDER BY (stock > 0) DESC, nombre ASC LIMIT 30
                """, (f"%{busqueda}%", busqueda if busqueda.isdigit() else -1, busqueda))
                resultados = cursor.fetchall()  
            if self.input_buscar.value.strip() != busqueda:
                return
            self.lista_resultados.controls.clear()
            if resultados:
                self.lista_resultados.visible = True
                for fila in resultados:
                    p_id, p_nom, p_pres, p_stock, p_pen = fila
                    p_stock = int(p_stock) if p_stock is not None else 0
                    p_pen = float(p_pen) if p_pen is not None else 0.0
                    nom_limpio = str(p_nom).strip()
                    color_chip = ft.colors.GREEN_700 if p_stock > 10 else (ft.colors.ORANGE_800 if p_stock > 0 else ft.colors.RED_700)
                    
                    self.lista_resultados.controls.append(
                        ft.ListTile(
                            leading=ft.Icon(ft.icons.LOCAL_BAR, size=20, color=color_chip),
                            title=ft.Text(f"{nom_limpio} ({p_pres})", weight=ft.FontWeight.W_500, size=13),
                            subtitle=ft.Text(f"ID: {p_id} | S/ {p_pen:.2f}", size=11, color="#64748B"),
                            trailing=ft.Container(
                                content=ft.Text(f"Stock: {p_stock}", size=11, weight=ft.FontWeight.BOLD, color=ft.colors.WHITE),
                                bgcolor=color_chip,
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                border_radius=12
                            ),
                            on_click=lambda e, n=nom_limpio: self.seleccionar_autocompletado(n)
                        )
                    )
            else:
                self.lista_resultados.visible = False
            self.page.update()
        except Exception as ex:
            print(f"Error en búsqueda dinámica: {ex}")

    # --- LÓGICA DE CARRITO ---
    def restar_cant(self, e):
        val = int(self.input_cantidad.value) if self.input_cantidad.value and self.input_cantidad.value.isdigit() else 1
        if val > 1:
            self.input_cantidad.value = str(val - 1)
            self.page.update()

    def sumar_cant(self, e):
        val = int(self.input_cantidad.value) if self.input_cantidad.value and self.input_cantidad.value.isdigit() else 1
        self.input_cantidad.value = str(val + 1)
        self.page.update()

    def actualizar_totales(self):
        t_pen = sum(float(row.cells[6].content.value) for row in self.tabla_carrito.rows)
        t_usd = sum(float(row.cells[7].content.value) for row in self.tabla_carrito.rows)
        self.lbl_total_pen.value = f"S/ {t_pen:.2f}"
        self.lbl_total_usd.value = f"$ {t_usd:.2f}"
        self.page.update()

    def eliminar_fila(self, fila_a_borrar):
        if fila_a_borrar in self.tabla_carrito.rows:
            self.tabla_carrito.rows.remove(fila_a_borrar)
            self.tabla_carrito.update()
            self.actualizar_totales()

    def cambiar_cant_carrito(self, fila, delta):
        try:
            id_f = int(fila.cells[0].content.content.value)
            emp_f = fila.cells[3].content.value
            cant_actual = int(fila.cells[4].content.value)
            p_u = float(fila.cells[5].content.value)
            es_pen = float(fila.cells[6].content.value) > 0 or float(fila.cells[7].content.value) == 0
            nueva_cant = cant_actual + delta

            if nueva_cant <= 0:
                if fila in self.tabla_carrito.rows:
                    self.tabla_carrito.rows.remove(fila)
                    self.tabla_carrito.update()
                    self.actualizar_totales()
                return

            factor_f = MULT_MAP.get(emp_f, 1)

            if delta > 0:
                with obtener_cursor() as cur:
                    cur.execute("SELECT stock, nombre FROM productos WHERE id_producto = %s", (id_f,))
                    res = cur.fetchone()
                    if res:
                        st_bd = int(res[0])
                        tot_en_carrito = sum(MULT_MAP.get(r.cells[3].content.value, 1) * int(r.cells[4].content.value) for r in self.tabla_carrito.rows if int(r.cells[0].content.content.value) == id_f)
                        if (tot_en_carrito + factor_f) > st_bd:
                            self.page.open(ft.SnackBar(ft.Text(f"⚠️ Stock insuficiente. Solo quedan {st_bd} unidades en inventario."), bgcolor=ft.colors.RED))
                            return

            fila.cells[4].content.value = str(nueva_cant)
            fila.cells[6].content.value = f"{p_u * nueva_cant:.2f}" if es_pen else "0.00"
            fila.cells[7].content.value = f"{p_u * nueva_cant:.2f}" if not es_pen else "0.00"
            self.tabla_carrito.update()
            self.actualizar_totales()
        except Exception as ex:
            print(f"Error modificando cantidad: {ex}")

    def agregar_producto(self, e=None):
        busqueda = self.input_buscar.value.strip()
        if not busqueda:
            return
        
        cant_ingresada = int(self.input_cantidad.value) if self.input_cantidad.value and self.input_cantidad.value.isdigit() else 1
        if cant_ingresada <= 0:
            cant_ingresada = 1
        
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT id_producto, nombre, presentacion, 
                           precio_uni_pen, precio_uni_usd, precio_six_pen, precio_six_usd, 
                           precio_caja_pen, precio_caja_usd, precio_plancha_pen, precio_plancha_usd,
                           grupo_surtido, precio_pack4_pen, precio_pack4_usd, precio_pack15_pen, precio_pack15_usd,
                           stock
                    FROM productos WHERE id_producto = %s OR nombre = %s OR codigo_barras = %s LIMIT 1
                """, (busqueda if busqueda.isdigit() else 0, busqueda, busqueda))
                producto = cursor.fetchone()

            if producto:
                (id_prod, nombre, pres, p_uni_pen, p_uni_usd, p_six_pen, p_six_usd, p_caja_pen, p_caja_usd, p_plan_pen, p_plan_usd, grupo_sur, p_p4_pen, p_p4_usd, p_p15_pen, p_p15_usd, stock_prod) = producto
                stock_prod = int(stock_prod) if stock_prod is not None else 0
                
                moneda = self.dropdown_moneda.value
                empaque = self.dropdown_empaque.value

                # LÓGICA COMBO SURTIDO
                if grupo_sur and empaque != "Unidad":
                    multiplicadores = {"Pack-4": 4, "Six-pack": 6, "Caja": 12, "Pack-15": 15, "Plancha": 24}
                    unidades_requeridas = multiplicadores.get(empaque, 1) * cant_ingresada
                    
                    if empaque == "Pack-4": p_t_pen = p_p4_pen * cant_ingresada; p_t_usd = p_p4_usd * cant_ingresada
                    elif empaque == "Six-pack": p_t_pen = p_six_pen * cant_ingresada; p_t_usd = p_six_usd * cant_ingresada
                    elif empaque == "Caja": p_t_pen = p_caja_pen * cant_ingresada; p_t_usd = p_caja_usd * cant_ingresada
                    elif empaque == "Pack-15": p_t_pen = p_p15_pen * cant_ingresada; p_t_usd = p_p15_usd * cant_ingresada
                    else: p_t_pen = p_plan_pen * cant_ingresada; p_t_usd = p_plan_usd * cant_ingresada
                    
                    if self.input_precio_esp.value:
                        try:
                            p_t_pen = float(self.input_precio_esp.value) * cant_ingresada
                            p_t_usd = float(self.input_precio_esp.value) * cant_ingresada
                        except ValueError:
                            pass

                    self.surtidor_estado["requeridas"] = unidades_requeridas
                    self.surtidor_estado["seleccionadas"] = 0
                    self.surtidor_estado["precio_u_pen"] = p_t_pen / unidades_requeridas if moneda == "PEN" else 0.00
                    self.surtidor_estado["precio_u_usd"] = p_t_usd / unidades_requeridas if moneda == "USD" else 0.00
                    self.surtidor_estado["empaque_base"] = empaque
                    
                    with obtener_cursor() as cursor2:
                        cursor2.execute("SELECT id_producto, nombre, presentacion, stock FROM productos WHERE grupo_surtido = %s", (grupo_sur,))
                        hermanos = cursor2.fetchall()
                        
                    self.surtidor_items.clear()
                    self.lista_surtidor_ui.controls.clear()

                    for h in hermanos:
                        item_dict = {"id": h[0], "nombre": h[1], "pres": h[2], "stock": int(h[3]), "cant": 0, "text_cant": ft.Text("0", size=16, weight=ft.FontWeight.BOLD)}
                        self.surtidor_items.append(item_dict)
                        btn_menos = ft.IconButton(ft.icons.REMOVE_CIRCLE, icon_size=18, width=28, height=28, style=ft.ButtonStyle(padding=0), icon_color=ft.colors.RED, on_click=lambda ev, i=item_dict: self.cambiar_cant_surtidor(i, -1))
                        btn_mas = ft.IconButton(ft.icons.ADD_CIRCLE, icon_size=18, width=28, height=28, style=ft.ButtonStyle(padding=0), icon_color=ft.colors.GREEN, on_click=lambda ev, i=item_dict: self.cambiar_cant_surtidor(i, 1))
                        btn_llenar = ft.IconButton(ft.icons.DOUBLE_ARROW, icon_size=18, width=28, height=28, style=ft.ButtonStyle(padding=0), icon_color=ft.colors.BLUE, tooltip="Llenar todo con este", on_click=lambda ev, i=item_dict: self.llenar_cant_surtidor(i))
                        fila_ui = ft.Row([
                            ft.Container(content=ft.Text(f"{h[1]} ({h[2]})\nStock: {h[3]}", size=12), width=200),
                            ft.Row([btn_menos, item_dict["text_cant"], btn_mas, btn_llenar], spacing=0)
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                        
                        self.lista_surtidor_ui.controls.append(fila_ui)
                    
                    self.actualizar_contador_surtidor()
                    self.page.open(self.dialogo_surtidor)
                    self.input_buscar.value = ""; self.input_cantidad.value = "1"; self.input_precio_esp.value = ""; self.lista_resultados.visible = False
                    return

                precio_final = 0.00
                if empaque == "Unidad": precio_final = p_uni_pen if moneda == "PEN" else p_uni_usd
                elif empaque == "Pack-4": precio_final = p_p4_pen if moneda == "PEN" else p_p4_usd
                elif empaque == "Six-pack": precio_final = p_six_pen if moneda == "PEN" else p_six_usd
                elif empaque == "Caja": precio_final = p_caja_pen if moneda == "PEN" else p_caja_usd
                elif empaque == "Pack-15": precio_final = p_p15_pen if moneda == "PEN" else p_p15_usd
                elif empaque == "Plancha": precio_final = p_plan_pen if moneda == "PEN" else p_plan_usd
                
                if self.input_precio_esp.value:
                    try:
                        precio_final = float(self.input_precio_esp.value)
                    except ValueError:
                        pass
                
                # Validación de stock
                unidades_solicitadas = MULT_MAP.get(empaque, 1) * cant_ingresada
                unidades_en_carrito = sum(MULT_MAP.get(r.cells[3].content.value, 1) * int(r.cells[4].content.value) for r in self.tabla_carrito.rows if int(r.cells[0].content.content.value) == id_prod)

                if (unidades_en_carrito + unidades_solicitadas) > stock_prod:
                    self.page.open(ft.SnackBar(
                        ft.Text(f"⚠️ Stock insuficiente para '{nombre}'. Disponible: {stock_prod}, en carrito: {unidades_en_carrito}, solicitado: {unidades_solicitadas}"),
                        bgcolor=ft.colors.RED,
                        duration=4000
                    ))
                    return

                # Si ya existe en carrito con mismo empaque y precio, se suma
                fila_existente = None
                for r in self.tabla_carrito.rows:
                    try:
                        if int(r.cells[0].content.content.value) == id_prod and r.cells[3].content.value == empaque:
                            p_actual = float(r.cells[5].content.value)
                            if abs(p_actual - precio_final) < 0.001:
                                fila_existente = r
                                break
                    except Exception:
                        pass

                if fila_existente:
                    cant_total = int(fila_existente.cells[4].content.value) + cant_ingresada
                    fila_existente.cells[4].content.value = str(cant_total)
                    sub_pen = (precio_final * cant_total) if moneda == "PEN" else 0.00
                    sub_usd = (precio_final * cant_total) if moneda == "USD" else 0.00
                    fila_existente.cells[6].content.value = f"{sub_pen:.2f}"
                    fila_existente.cells[7].content.value = f"{sub_usd:.2f}"
                    self.tabla_carrito.update()
                    self.actualizar_totales()
                    self.input_buscar.value = ""; self.input_cantidad.value = "1"; self.input_precio_esp.value = ""; self.lista_resultados.visible = False
                    if self.switch_escaner.value:
                        self.page.open(ft.SnackBar(ft.Text(f"⚡ Escaneado: {nombre}", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN_800, duration=1200))
                        self.input_buscar.focus()
                    return

                sub_pen = (precio_final * cant_ingresada) if moneda == "PEN" else 0.00
                sub_usd = (precio_final * cant_ingresada) if moneda == "USD" else 0.00
                
                id_formateado = str(id_prod).zfill(3)
                nueva_fila = ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(id_formateado), width=30)),
                    ft.DataCell(ft.Container(content=ft.Text(str(nombre), size=12, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS), width=170)),
                    ft.DataCell(ft.Text(str(pres))), ft.DataCell(ft.Text(empaque)), ft.DataCell(ft.Text(str(cant_ingresada))),
                    ft.DataCell(ft.Text(f"{precio_final:.2f}")), ft.DataCell(ft.Text(f"{sub_pen:.2f}")), ft.DataCell(ft.Text(f"{sub_usd:.2f}"))
                ])

                btn_menos = ft.IconButton(icon=ft.icons.REMOVE_CIRCLE_OUTLINE, icon_size=16, width=26, height=26, style=ft.ButtonStyle(padding=0), icon_color=ft.colors.ORANGE_800, tooltip="Restar 1", data=nueva_fila, on_click=lambda ev: self.cambiar_cant_carrito(ev.control.data, -1))
                btn_mas = ft.IconButton(icon=ft.icons.ADD_CIRCLE_OUTLINE, icon_size=16, width=26, height=26, style=ft.ButtonStyle(padding=0), icon_color=ft.colors.GREEN_800, tooltip="Sumar 1", data=nueva_fila, on_click=lambda ev: self.cambiar_cant_carrito(ev.control.data, 1))
                btn_eliminar = ft.IconButton(icon=ft.icons.DELETE_OUTLINE, icon_size=16, width=26, height=26, style=ft.ButtonStyle(padding=0), icon_color=ft.colors.RED_600, tooltip="Eliminar", data=nueva_fila, on_click=lambda ev: self.eliminar_fila(ev.control.data))
                nueva_fila.cells.append(ft.DataCell(ft.Row([btn_menos, btn_mas, btn_eliminar], spacing=2)))
                self.tabla_carrito.rows.append(nueva_fila)
                self.tabla_carrito.update()
                
                self.input_buscar.value = ""; self.input_cantidad.value = "1"; self.input_precio_esp.value = ""; self.lista_resultados.visible = False; self.actualizar_totales()
                if self.switch_escaner.value:
                    self.page.open(ft.SnackBar(ft.Text(f"⚡ Escaneado: {nombre}", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN_800, duration=1200))
                    self.input_buscar.focus()
            else:
                self.page.open(ft.SnackBar(ft.Text(f"❌ Código o producto '{busqueda}' no encontrado.", color=ft.colors.WHITE), bgcolor=ft.colors.RED_700, duration=2000))
                if self.switch_escaner.value:
                    self.input_buscar.value = ""
                    self.input_buscar.focus()
        except Exception as ex:
            print(f"Error al agregar al carrito: {ex}")
            self.page.open(ft.SnackBar(ft.Text("Error al agregar el producto.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    # --- LÓGICA DE DIÁLOGO DE SURTIDOR ---
    def actualizar_contador_surtidor(self):
        total = sum(item["cant"] for item in self.surtidor_items)
        self.surtidor_estado["seleccionadas"] = total
        self.lbl_contador_surtidor.value = f"Seleccionadas: {total} / {self.surtidor_estado['requeridas']}"
        self.lbl_contador_surtidor.color = ft.colors.GREEN if total == self.surtidor_estado["requeridas"] else ft.colors.RED
        self.btn_confirmar_surtidor.disabled = (total != self.surtidor_estado["requeridas"])
        self.page.update()

    def cambiar_cant_surtidor(self, item, delta):
        nueva_cant = item["cant"] + delta
        if 0 <= nueva_cant <= item["stock"]:
            if delta > 0 and self.surtidor_estado["seleccionadas"] >= self.surtidor_estado["requeridas"]:
                return
            item["cant"] = nueva_cant
            item["text_cant"].value = str(nueva_cant)
            self.actualizar_contador_surtidor()

    def llenar_cant_surtidor(self, item):
        faltante = self.surtidor_estado["requeridas"] - self.surtidor_estado["seleccionadas"]
        if faltante > 0:
            posible = min(faltante, item["stock"] - item["cant"])
            if posible > 0:
                item["cant"] += posible
                item["text_cant"].value = str(item["cant"])
                self.actualizar_contador_surtidor()

    def confirmar_surtidor(self, e):
        for item in self.surtidor_items:
            if item["cant"] > 0:
                sub_pen = item["cant"] * self.surtidor_estado["precio_u_pen"]
                sub_usd = item["cant"] * self.surtidor_estado["precio_u_usd"]
                
                id_formateado = str(item["id"]).zfill(3)
                emp_mix = f"Mix {self.surtidor_estado['empaque_base'][:3]}"
                
                nueva_fila = ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(id_formateado), width=30)),
                    ft.DataCell(ft.Container(content=ft.Text(str(item["nombre"]), size=12, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS), width=170)),
                    ft.DataCell(ft.Text(str(item["pres"]))),
                    ft.DataCell(ft.Text(emp_mix)),
                    ft.DataCell(ft.Text(str(item["cant"]))),
                    ft.DataCell(ft.Text(f"{self.surtidor_estado['precio_u_pen']:.2f}")),
                    ft.DataCell(ft.Text(f"{sub_pen:.2f}")),
                    ft.DataCell(ft.Text(f"{sub_usd:.2f}"))
                ])
                
                btn_eliminar = ft.IconButton(
                    icon=ft.icons.DELETE_OUTLINE, icon_size=18, icon_color=ft.colors.RED_600,
                    tooltip="Eliminar", data=nueva_fila,
                    on_click=lambda ev: self.eliminar_fila(ev.control.data)
                )
                nueva_fila.cells.append(ft.DataCell(btn_eliminar))
                self.tabla_carrito.rows.append(nueva_fila)
                
        self.tabla_carrito.update()
        self.actualizar_totales()
        self.page.close(self.dialogo_surtidor)

    # --- LÓGICA DE COBRO Y MÉTODOS DE PAGO ---
    def seleccionar_condicion(self, cond):
        self.condicion_cobro_estado = cond
        self.actualizar_estilo_condicion()
        self.calcular_vuelto()
        self.page.update()

    def actualizar_estilo_condicion(self):
        if self.condicion_cobro_estado == "Contado":
            self.card_cond_contado.border = ft.border.all(2, "#10B981")
            self.card_cond_contado.bgcolor = "#ECFDF5"
            self.card_cond_contado.content.controls[0].color = "#059669"
            self.card_cond_contado.content.controls[1].color = "#065F46"
            
            self.card_cond_credito.border = ft.border.all(1, "#E2E8F0")
            self.card_cond_credito.bgcolor = ft.colors.WHITE
            self.card_cond_credito.content.controls[0].color = "#64748B"
            self.card_cond_credito.content.controls[1].color = "#64748B"
        else:
            self.card_cond_credito.border = ft.border.all(2, "#2563EB")
            self.card_cond_credito.bgcolor = "#EFF6FF"
            self.card_cond_credito.content.controls[0].color = "#2563EB"
            self.card_cond_credito.content.controls[1].color = "#1E40AF"
            
            self.card_cond_contado.border = ft.border.all(1, "#E2E8F0")
            self.card_cond_contado.bgcolor = ft.colors.WHITE
            self.card_cond_contado.content.controls[0].color = "#64748B"
            self.card_cond_contado.content.controls[1].color = "#64748B"

    def limpiar_metodo(self, inp):
        inp.value = ""
        self.calcular_vuelto()
        self.page.update()

    def autollenar_metodo(self, inp, es_dolares=False):
        try:
            t_pen = sum(float(row.cells[6].content.value) for row in self.tabla_carrito.rows)
            t_usd = sum(float(row.cells[7].content.value) for row in self.tabla_carrito.rows)
            if es_dolares:
                inp.value = f"{t_usd:.2f}" if t_usd > 0 else ""
            else:
                otros = 0.0
                for otro_inp in [self.input_pago_efectivo, self.input_pago_yape, self.input_pago_transferencia, self.input_pago_tarjeta]:
                    if otro_inp != inp and otro_inp.value and otro_inp.value.strip():
                        try:
                            otros += float(otro_inp.value)
                        except ValueError:
                            pass
                faltante = max(0.0, t_pen - otros)
                inp.value = f"{faltante:.2f}"
            self.calcular_vuelto()
            self.page.update()
        except Exception:
            pass

    def crear_tarjeta_metodo(self, titulo, icono, color_primario, color_fondo, input_ctrl, col_spec={"sm": 12, "md": 4}, es_dolares=False):
        btn_x = ft.IconButton(
            icon=ft.icons.CLEAR,
            icon_size=15,
            width=24,
            height=24,
            style=ft.ButtonStyle(padding=0),
            tooltip="Limpiar",
            on_click=lambda _: self.limpiar_metodo(input_ctrl)
        )
        input_ctrl.suffix = btn_x
        input_ctrl.dense = True
        input_ctrl.height = 42
        input_ctrl.text_size = 13
        input_ctrl.border_color = color_primario
        input_ctrl.focused_border_color = color_primario
        input_ctrl.bgcolor = ft.colors.WHITE

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Row([
                        ft.Icon(icono, size=16, color=color_primario),
                        ft.Text(titulo, size=12, weight=ft.FontWeight.BOLD, color=color_primario),
                    ], spacing=5),
                    ft.TextButton(
                        "Todo",
                        style=ft.ButtonStyle(
                            color=color_primario,
                            padding=ft.padding.symmetric(horizontal=4, vertical=0)
                        ),
                        on_click=lambda _: self.autollenar_metodo(input_ctrl, es_dolares=es_dolares)
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                input_ctrl
            ], spacing=4),
            padding=8,
            border_radius=8,
            bgcolor=color_fondo,
            border=ft.border.all(1.5, color_primario),
            col=col_spec
        )

    def calcular_vuelto(self, e=None):
        try:
            t_pen = sum(float(row.cells[6].content.value) for row in self.tabla_carrito.rows)
            t_usd = sum(float(row.cells[7].content.value) for row in self.tabla_carrito.rows)
            
            ef = float(self.input_pago_efectivo.value) if self.input_pago_efectivo.value and self.input_pago_efectivo.value.strip() else 0.0
            yp = float(self.input_pago_yape.value) if self.input_pago_yape.value and self.input_pago_yape.value.strip() else 0.0
            tr = float(self.input_pago_transferencia.value) if self.input_pago_transferencia.value and self.input_pago_transferencia.value.strip() else 0.0
            ta = float(self.input_pago_tarjeta.value) if self.input_pago_tarjeta.value and self.input_pago_tarjeta.value.strip() else 0.0
            dl = float(self.input_pago_dolares.value) if self.input_pago_dolares.value and self.input_pago_dolares.value.strip() else 0.0
            
            condicion = self.condicion_cobro_estado
            total_pagado_pen = ef + yp + tr + ta
            diferencia_pen = total_pagado_pen - t_pen
            
            if condicion == "Crédito":
                if total_pagado_pen == 0:
                    self.lbl_vuelto.value = f"📌 Venta a Crédito Total: S/ {t_pen:.2f}"
                    self.lbl_vuelto.color = "#2563EB"
                else:
                    saldo = max(0.0, t_pen - total_pagado_pen)
                    self.lbl_vuelto.value = f"📌 Abono Inicial: S/ {total_pagado_pen:.2f} | Saldo a Crédito: S/ {saldo:.2f}"
                    self.lbl_vuelto.color = "#2563EB"
            else:
                if diferencia_pen < -0.001:
                    self.lbl_vuelto.value = f"❌ Faltante: S/ {abs(diferencia_pen):.2f}"
                    self.lbl_vuelto.color = ft.colors.RED_700
                elif abs(diferencia_pen) < 0.001:
                    self.lbl_vuelto.value = "✅ Pago Completo Exacto"
                    self.lbl_vuelto.color = "#059669"
                else:
                    self.lbl_vuelto.value = f"💵 Vuelto a entregar: S/ {diferencia_pen:.2f}"
                    self.lbl_vuelto.color = "#059669"
                    
            if dl > 0:
                self.lbl_vuelto.value += f" (Dólares recibidos: $ {dl:.2f})"
                
            self.page.update()
        except ValueError:
            pass

    def procesar_venta(self, e):
        if not self.tabla_carrito.rows:
            self.page.open(ft.SnackBar(ft.Text("⛔ El carrito está vacío.", color=ft.colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.colors.RED))
            return
        t_pen = sum(float(row.cells[6].content.value) for row in self.tabla_carrito.rows)
        t_usd = sum(float(row.cells[7].content.value) for row in self.tabla_carrito.rows)
        
        txt_resumen = f"Total a cobrar: S/ {t_pen:.2f}"
        if t_usd > 0:
            txt_resumen += f" | $ {t_usd:.2f}"
        self.lbl_resumen_cobro.value = txt_resumen
        
        self.condicion_cobro_estado = "Contado"
        self.actualizar_estilo_condicion()
        
        # TODOS LOS CAMPOS APARECEN EN BLANCO PARA RELLENAR MANUALMENTE:
        self.input_pago_efectivo.value = ""
        self.input_pago_yape.value = ""
        self.input_pago_transferencia.value = ""
        self.input_pago_tarjeta.value = ""
        self.input_pago_dolares.value = ""
        
        self.calcular_vuelto()
        self.page.open(self.dialogo_cobro)

    def confirmar_y_guardar_venta(self, e):
        e.control.disabled = True
        e.control.text = "Procesando..."
        self.page.update()

        codigo_ticket = None
        id_venta = None

        try:
            # ── 1. Extracción de montos de pago ──────────────────────────────────
            t_pen = sum(float(row.cells[6].content.value) for row in self.tabla_carrito.rows)
            t_usd = sum(float(row.cells[7].content.value) for row in self.tabla_carrito.rows)

            ef = float(self.input_pago_efectivo.value)       if self.input_pago_efectivo.value       and self.input_pago_efectivo.value.strip()       else 0.0
            yp = float(self.input_pago_yape.value)           if self.input_pago_yape.value           and self.input_pago_yape.value.strip()           else 0.0
            tr = float(self.input_pago_transferencia.value)  if self.input_pago_transferencia.value  and self.input_pago_transferencia.value.strip()  else 0.0
            ta = float(self.input_pago_tarjeta.value)        if self.input_pago_tarjeta.value        and self.input_pago_tarjeta.value.strip()        else 0.0
            dl = float(self.input_pago_dolares.value)        if self.input_pago_dolares.value        and self.input_pago_dolares.value.strip()        else 0.0
            condicion = self.condicion_cobro_estado

            # ── 2. Validaciones de pago (sin acceso a BD) ────────────────────────
            total_pagado = ef + yp + tr + ta
            if condicion == "Contado" and total_pagado < t_pen and dl == 0:
                raise ValueError("❌ Pago insuficiente para venta al Contado.")

            if (yp + tr + ta) > t_pen and t_pen > 0:
                raise ValueError("❌ Medios digitales (Yape, Transferencia, Tarjeta) no pueden exceder el total.")

            vuelto = (total_pagado - t_pen) if ef > 0 and (total_pagado > t_pen) else 0.0
            pagos = {"Efectivo": ef, "Yape": yp, "Transferencia": tr, "Tarjeta": ta, "Dólares": dl}
            activos = [k for k, v in pagos.items() if v > 0]
            metodo_principal = "Crédito" if condicion == "Crédito" else ("Mixto" if len(activos) > 1 else (activos[0] if activos else "Efectivo"))

            # ── 3. Datos complementarios (sin BD) ────────────────────────────────
            dt_operacion = ahora_local()

            if hasattr(self.page, 'nombre_usuario') and self.page.nombre_usuario:
                vendedor_actual = str(self.page.nombre_usuario).strip().upper()
            elif hasattr(self.page, 'rol_usuario') and self.page.rol_usuario:
                vendedor_actual = str(self.page.rol_usuario).strip().upper()
            else:
                vendedor_actual = "ADMIN"

            obs = self.input_observacion.value.strip() if self.input_observacion.value else ""
            t_usd_final = t_usd if t_usd > 0 else dl

            # ── 4. Transacción atómica en BD (pool + commit/rollback automático) ─
            items = []
            costo_total_ticket_pen = 0.0
            costo_total_ticket_usd = 0.0

            with obtener_cursor(commit=True) as cursor:

                # 4a. Validar stock y calcular costos con bloqueo de fila (FOR UPDATE)
                for row in self.tabla_carrito.rows:
                    id_prod        = int(row.cells[0].content.content.value)
                    empaque        = row.cells[3].content.value
                    cant           = int(row.cells[4].content.value)
                    p_unit         = float(row.cells[5].content.value)
                    sub_pen        = float(row.cells[6].content.value)
                    sub_usd        = float(row.cells[7].content.value)
                    descuento_stock = MULT_MAP.get(empaque, 1) * cant

                    cursor.execute("""
                        SELECT nombre, stock,
                               costo_uni_pen,   costo_uni_usd,
                               costo_pack4_pen, costo_pack4_usd,
                               costo_six_pen,   costo_six_usd,
                               costo_caja_pen,  costo_caja_usd,
                               costo_pack15_pen, costo_pack15_usd,
                               costo_plancha_pen, costo_plancha_usd
                        FROM productos WHERE id_producto = %s FOR UPDATE
                    """, (id_prod,))
                    resultado = cursor.fetchone()

                    # Stock insuficiente → ValueError desencadena rollback automático
                    if not resultado or resultado[1] < descuento_stock:
                        nombre_prod = resultado[0] if resultado else f"ID {id_prod}"
                        raise ValueError(
                            f"⛔ Stock insuficiente para '{nombre_prod}'. "
                            f"Disponible: {resultado[1] if resultado else 0}, solicitado: {descuento_stock}."
                        )

                    # Calcular costo según tipo de empaque
                    if   empaque == "Pack-4":   c_u_pen, c_u_usd = float(resultado[4]),  float(resultado[5])
                    elif empaque == "Six-pack":  c_u_pen, c_u_usd = float(resultado[6]),  float(resultado[7])
                    elif empaque == "Mix Six":
                        c_u_pen = (float(resultado[6]) / 6)  if float(resultado[6]) > 0 else float(resultado[2])
                        c_u_usd = (float(resultado[7]) / 6)  if float(resultado[7]) > 0 else float(resultado[3])
                    elif empaque == "Caja":      c_u_pen, c_u_usd = float(resultado[8]),  float(resultado[9])
                    elif empaque == "Mix Caj":
                        c_u_pen = (float(resultado[8]) / 12) if float(resultado[8]) > 0 else float(resultado[2])
                        c_u_usd = (float(resultado[9]) / 12) if float(resultado[9]) > 0 else float(resultado[3])
                    elif empaque == "Pack-15":   c_u_pen, c_u_usd = float(resultado[10]), float(resultado[11])
                    elif empaque == "Plancha":   c_u_pen, c_u_usd = float(resultado[12]), float(resultado[13])
                    elif empaque == "Mix Pla":
                        c_u_pen = (float(resultado[12]) / 24) if float(resultado[12]) > 0 else float(resultado[2])
                        c_u_usd = (float(resultado[13]) / 24) if float(resultado[13]) > 0 else float(resultado[3])
                    else:
                        c_u_pen, c_u_usd = float(resultado[2]), float(resultado[3])

                    costo_total_ticket_pen += c_u_pen * cant
                    costo_total_ticket_usd += c_u_usd * cant
                    items.append((id_prod, empaque, cant, p_unit, sub_pen, sub_usd, descuento_stock, c_u_pen, c_u_usd))

                # 4b. Generar número de ticket (dentro de la misma transacción)
                cursor.execute("SELECT COALESCE(MAX(id_venta), 0) FROM ventas")
                siguiente_id = cursor.fetchone()[0] + 1
                codigo_ticket = f"NV-{siguiente_id:08d}"

                utilidad_neta_pen = t_pen - costo_total_ticket_pen
                utilidad_neta_usd = t_usd_final - costo_total_ticket_usd

                # 4c. Insertar cabecera de venta
                cursor.execute("""
                    INSERT INTO ventas (
                        codigo_ticket, fecha_emision, hora_emision, vendedor,
                        cliente_nombre, cliente_dni, cliente_direccion,
                        total_pen, total_usd, observaciones, condicion_pago, metodo_pago,
                        monto_efectivo, monto_yape,
                        monto_plin,          -- columna de transferencia bancaria
                        monto_tarjeta,
                        monto_transferencia, -- columna nueva → siempre 0.00 (evita duplicado)
                        monto_dolares, vuelto, utilidad_pen, utilidad_usd
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    codigo_ticket, dt_operacion.date(), dt_operacion.time().strftime("%H:%M:%S"), vendedor_actual,
                    self.input_cliente.value, self.input_dni.value, self.input_direccion.value,
                    t_pen, t_usd_final, obs, condicion, metodo_principal,
                    ef, yp,
                    tr,    # transferencia bancaria
                    ta,
                    0.00,  # monto_transferencia (evita duplicado)
                    dl, vuelto, utilidad_neta_pen, utilidad_neta_usd
                ))
                id_venta = cursor.lastrowid

                # 4d. Insertar detalle de cada ítem y descontar stock
                for id_prod, empaque, cant, p_unit, sub_pen, sub_usd, desc_stock, c_pen, c_usd in items:
                    cursor.execute(
                        """INSERT INTO detalles_venta
                           (id_venta, id_producto, tipo_empaque, cantidad, precio_unitario,
                            subtotal_pen, subtotal_usd, costo_unitario_pen, costo_unitario_usd)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (id_venta, id_prod, empaque, cant, p_unit, sub_pen, sub_usd, c_pen, c_usd)
                    )
                    cursor.execute(
                        "UPDATE productos SET stock = stock - %s WHERE id_producto = %s",
                        (desc_stock, id_prod)
                    )
                # ── Commit automático al salir del bloque `with` ────────────

            # ── 5. Limpieza de UI (solo si la transacción fue exitosa) ────────────
            self.tabla_carrito.rows.clear()
            self.input_dni.value         = ""
            self.input_cliente.value     = ""
            self.input_direccion.value   = "Tacna"  # restaura valor por defecto
            self.input_observacion.value = ""
            self.actualizar_totales()
            self.page.close(self.dialogo_cobro)

            # ── 6. Diálogo de éxito ───────────────────────────────────────────────
            def cerrar_alerta_venta(ev):
                self.page.close(alerta_venta)

            alerta_venta = ft.AlertDialog(
                title=ft.Text("¡Venta Realizada!", color=ft.colors.GREEN, weight=ft.FontWeight.BOLD),
                content=ft.Text(f"Ticket: {codigo_ticket}\nStock descontado y Utilidad Neta calculada.", size=16),
                actions=[
                    ft.TextButton("Ver Nota de Venta", on_click=lambda ev, id_v=id_venta, cod=codigo_ticket: self.ver_nota_venta(id_v, cod)),
                    ft.ElevatedButton("Aceptar", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=cerrar_alerta_venta)
                ]
            )
            self.page.open(alerta_venta)

        except ValueError as ve:
            # Error controlado: validación de pago o stock insuficiente
            # El rollback ya fue ejecutado automáticamente por obtener_cursor
            self.page.open(ft.SnackBar(
                ft.Text(str(ve), color=ft.colors.WHITE, weight=ft.FontWeight.BOLD),
                bgcolor=ft.colors.RED, duration=4000
            ))
        except Exception as ex:
            # Error inesperado: fallo de BD u otro
            # El rollback ya fue ejecutado automáticamente por obtener_cursor
            print(f"Error procesando venta: {ex}")
            self.page.open(ft.SnackBar(
                ft.Text("❌ Error de base de datos. La venta NO fue registrada.", color=ft.colors.WHITE),
                bgcolor=ft.colors.RED, duration=4000
            ))
        finally:
            # Siempre restaurar el botón, independientemente del resultado
            e.control.disabled = False
            e.control.text = "Confirmar Venta"
            self.page.update()


    # --- LÓGICA DE NOTA DE VENTA / TICKET ---
    def ver_nota_venta(self, id_venta_reciente, codigo_ticket):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT nombre_negocio FROM configuracion LIMIT 1")
                conf = cursor.fetchone()
                c_nom_emp = conf[0] if conf else "LICOR STORE"

                cursor.execute("SELECT fecha_emision, hora_emision, vendedor, cliente_nombre, cliente_dni, cliente_direccion, total_pen, total_usd, metodo_pago, monto_efectivo, monto_yape, monto_plin, monto_tarjeta, vuelto, condicion_pago FROM ventas WHERE id_venta = %s", (id_venta_reciente,))
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

            f_emision, h_emision, vendedor, c_nombre, c_dni, c_dir, t_pen, t_usd, m_pago, m_efec, m_yape, m_transf, m_tarj, vuelto, *resto = cabecera
            cond_pago = resto[0] if resto and resto[0] else "Contado"
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
                elementos_finales.append(ft.Row([ft.Text("Condición:", size=11, weight=ft.FontWeight.BOLD), ft.Text(str(cond_pago), size=11, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_800 if cond_pago == 'Crédito' else ft.colors.BLACK)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
                elementos_finales.append(ft.Row([ft.Text("Método de Pago:", size=11, weight=ft.FontWeight.BOLD), ft.Text(str(m_pago), size=11)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
            
                if m_efec > 0: elementos_finales.append(ft.Row([ft.Text("Efectivo:", size=11), ft.Text(f"S/ {m_efec:.2f}", size=11)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
                if m_yape > 0: elementos_finales.append(ft.Row([ft.Text("Yape:", size=11), ft.Text(f"S/ {m_yape:.2f}", size=11)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
                if m_transf > 0: elementos_finales.append(ft.Row([ft.Text("Transferencia:", size=11), ft.Text(f"S/ {m_transf:.2f}", size=11)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
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

            def cerrar_ticket(ev):
                self.page.close(dialogo_ticket)

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
                    ft.ElevatedButton("Imprimir", icon=ft.icons.PRINT, bgcolor=ft.colors.BLUE, color=ft.colors.WHITE, on_click=lambda ev, iv=id_venta_reciente, ct=codigo_ticket: exportar_ticket_pdf(self.page, iv, ct)),
                    ft.ElevatedButton("Cerrar Ticket", bgcolor=ft.colors.BLACK, color=ft.colors.WHITE, on_click=cerrar_ticket)
                ]
            )
                
            self.page.open(dialogo_ticket)

        except Exception as ex:
            print(f"Error generando ticket: {ex}")
            self.page.open(ft.SnackBar(ft.Text("No se pudo generar la nota de venta.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

