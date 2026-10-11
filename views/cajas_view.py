import flet as ft
import datetime
from database import obtener_cursor
from pdf_generator import exportar_recibo_abono_pdf, exportar_cierre_turno_pdf
from time_service import ahora_local, fecha_local, hora_local

class CajasView(ft.Container):
    def __init__(self, page: ft.Page, fn_solicitar_password=None):
        super().__init__()
        self.page = page
        self.fn_solicitar_password = fn_solicitar_password
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

        # Variables de estado nativas OOP (reemplazan manejos frágiles [None])
        self.monto_efectivo_ventas = 0.0
        self.monto_cobranzas_efectivo = 0.0
        self.monto_gastos_dia = 0.0
        self.datos_credito_seleccionado = None
        self.totales_cierre_actual = {
            "ventas_efectivo": 0.0,
            "ventas_yape": 0.0,
            "ventas_transferencia": 0.0,
            "ventas_tarjeta": 0.0,
            "ventas_dolares": 0.0,
            "abonos_efectivo": 0.0,
            "gastos": 0.0
        }

        self.construir_interfaz()
        self.construir_dialogos()

    def crear_tarjeta_caja(self, titulo, label_valor, color_borde):
        return ft.Container(
            content=ft.Column([
                ft.Text(titulo, size=11, color=ft.colors.GREY_700, weight=ft.FontWeight.BOLD, no_wrap=True),
                label_valor
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=10, bgcolor=ft.colors.WHITE, border_radius=10, border=ft.border.all(2, color_borde), width=140
        )

    def construir_interfaz(self):
        # --- TARJETAS RESUMEN DE CAJA ---
        self.lbl_caja_efectivo = ft.Text("S/ 0.00", size=18, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN)
        self.lbl_caja_cobranzas = ft.Text("S/ 0.00", size=18, weight=ft.FontWeight.BOLD, color=ft.colors.TEAL_700)
        self.lbl_caja_yape = ft.Text("S/ 0.00", size=18, weight=ft.FontWeight.BOLD, color=ft.colors.PURPLE)
        self.lbl_caja_tarjeta = ft.Text("S/ 0.00", size=18, weight=ft.FontWeight.BOLD, color=ft.colors.ORANGE)
        self.lbl_caja_credito = ft.Text("S/ 0.00", size=18, weight=ft.FontWeight.BOLD, color=ft.colors.INDIGO_700)
        self.lbl_caja_gastos = ft.Text("S/ 0.00", size=18, weight=ft.FontWeight.BOLD, color=ft.colors.RED_700)
        self.lbl_caja_total = ft.Text("S/ 0.00", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.BLACK)
        self.lbl_caja_dolares = ft.Text("$ 0.00", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_800)

        # --- TAB 1: CONTROL DE CAJA Y ARQUEO ---
        self.date_picker_cajas = ft.DatePicker(
            on_change=self.cambiar_fecha_calendario,
            cancel_text="Cancelar",
            confirm_text="Seleccionar",
            help_text="SELECCIONE UNA FECHA",
            field_hint_text="dd/mm/aaaa",
            field_label_text="Ingrese una fecha",
            error_format_text="Formato inválido",
            error_invalid_text="Fecha fuera de rango"
        )
        self.page.overlay.append(self.date_picker_cajas)

        self.input_fecha_caja = ft.TextField(
            label="Fecha",
            value=str(fecha_local()),
            read_only=True,
            col={"sm": 8, "md": 3},
            height=42,
            text_size=13,
            dense=True
        )
        self.btn_calendario = ft.IconButton(
            icon=ft.icons.CALENDAR_MONTH,
            icon_color=ft.colors.BLUE,
            on_click=lambda _: self.page.open(self.date_picker_cajas),
            col={"sm": 4, "md": 1}
        )
        self.btn_buscar_caja = ft.ElevatedButton(
            "Consultar Día",
            icon=ft.icons.SEARCH,
            on_click=self.cargar_datos_cajas,
            bgcolor=ft.colors.BLUE_700,
            color=ft.colors.WHITE,
            col={"sm": 12, "md": 4},
            height=42
        )
        self.btn_arqueo = ft.ElevatedButton(
            "Arqueo de Caja",
            icon=ft.icons.ACCOUNT_BALANCE,
            on_click=self.abrir_arqueo,
            bgcolor=ft.colors.GREEN_700,
            color=ft.colors.WHITE,
            col={"sm": 12, "md": 4},
            height=42
        )

        self.tabla_cajas = ft.DataTable(
            heading_row_color=ft.colors.GREY_100,
            border_radius=8,
            border=ft.border.all(1, ft.colors.GREY_200),
            columns=[
                ft.DataColumn(ft.Text("Ticket", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Hora", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Condición", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("M. Principal", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Efectivo", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Yape", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Tarjeta", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Total (S/)", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Dólares ($)", weight=ft.FontWeight.BOLD))
            ],
            rows=[]
        )

        self.tab_caja_diaria = ft.Container(
            content=ft.Column([
                ft.ResponsiveRow([self.input_fecha_caja, self.btn_calendario, self.btn_buscar_caja, self.btn_arqueo]),
                ft.Divider(),
                ft.Row([
                    self.crear_tarjeta_caja("Efectivo Ventas", self.lbl_caja_efectivo, ft.colors.GREEN),
                    self.crear_tarjeta_caja("Cobranzas Crédito", self.lbl_caja_cobranzas, ft.colors.TEAL_700),
                    self.crear_tarjeta_caja("Yape", self.lbl_caja_yape, ft.colors.PURPLE),
                    self.crear_tarjeta_caja("Tarjeta", self.lbl_caja_tarjeta, ft.colors.ORANGE),
                    self.crear_tarjeta_caja("Créditos Emitidos", self.lbl_caja_credito, ft.colors.INDIGO_700),
                    self.crear_tarjeta_caja("Gastos del Día", self.lbl_caja_gastos, ft.colors.RED_700),
                    self.crear_tarjeta_caja("TOTAL VENTAS (S/)", self.lbl_caja_total, ft.colors.BLACK),
                    self.crear_tarjeta_caja("DÓLARES FÍSICOS", self.lbl_caja_dolares, ft.colors.GREEN_800)
                ], wrap=True, alignment=ft.MainAxisAlignment.SPACE_EVENLY),
                ft.Divider(),
                ft.Column([self.tabla_cajas], scroll=ft.ScrollMode.AUTO)
            ]),
            visible=True
        )

        # --- TAB 2: CUENTAS POR COBRAR (CRÉDITOS) ---
        self.lbl_total_por_cobrar = ft.Text("S/ 0.00", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.RED_700)
        self.card_total_por_cobrar = ft.Container(
            content=ft.Column([
                ft.Text("Total Deuda por Cobrar", size=12, color=ft.colors.GREY_700, weight=ft.FontWeight.BOLD),
                self.lbl_total_por_cobrar
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=12, bgcolor=ft.colors.WHITE, border_radius=10, border=ft.border.all(2, ft.colors.RED_400), width=220
        )

        self.input_buscar_credito = ft.TextField(
            label="Buscar Crédito",
            hint_text="Ticket o Cliente...",
            prefix_icon=ft.icons.SEARCH,
            on_change=lambda _: self.cargar_cuentas_cobrar(),
            col={"sm": 12, "md": 5},
            height=42,
            text_size=13,
            dense=True
        )
        self.check_solo_pendientes = ft.Checkbox(
            label="Solo créditos pendientes con deuda",
            value=True,
            on_change=lambda _: self.cargar_cuentas_cobrar(),
            col={"sm": 12, "md": 4}
        )
        self.btn_recargar_creditos = ft.ElevatedButton(
            "Actualizar",
            icon=ft.icons.REFRESH,
            on_click=lambda _: self.cargar_cuentas_cobrar(),
            bgcolor=ft.colors.BLUE_GREY_700,
            color=ft.colors.WHITE,
            col={"sm": 12, "md": 3},
            height=42
        )

        self.tabla_creditos = ft.DataTable(
            heading_row_color=ft.colors.GREY_100,
            border_radius=8,
            border=ft.border.all(1, ft.colors.GREY_200),
            columns=[
                ft.DataColumn(ft.Text("Ticket", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Fecha", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Cliente", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("DNI/RUC", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Total Venta (S/)", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Abonado (S/)", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Saldo Deuda (S/)", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Estado", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Acciones", weight=ft.FontWeight.BOLD))
            ],
            rows=[]
        )

        self.tab_cuentas_cobrar = ft.Container(
            content=ft.Column([
                ft.Row([
                    self.card_total_por_cobrar,
                    ft.Container(expand=True),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.ResponsiveRow([self.input_buscar_credito, self.check_solo_pendientes, self.btn_recargar_creditos]),
                ft.Divider(),
                ft.Column([self.tabla_creditos], scroll=ft.ScrollMode.AUTO)
            ]),
            visible=False
        )

        # --- TAB 3: GASTOS Y CAJA CHICA ---
        self.lbl_total_gastos_dia = ft.Text("S/ 0.00", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.RED_700)
        self.card_total_gastos = ft.Container(
            content=ft.Column([
                ft.Text("Total Egresos del Día", size=12, color=ft.colors.GREY_700, weight=ft.FontWeight.BOLD),
                self.lbl_total_gastos_dia
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=12, bgcolor=ft.colors.WHITE, border_radius=10, border=ft.border.all(2, ft.colors.RED_400), width=200
        )

        self.date_picker_gastos = ft.DatePicker(
            on_change=self.cambiar_fecha_gastos,
            cancel_text="Cancelar",
            confirm_text="Seleccionar",
            help_text="SELECCIONE UNA FECHA",
            field_hint_text="dd/mm/aaaa",
            field_label_text="Ingrese una fecha",
            error_format_text="Formato inválido",
            error_invalid_text="Fecha fuera de rango"
        )
        self.page.overlay.append(self.date_picker_gastos)

        self.input_fecha_gastos = ft.TextField(
            label="Fecha",
            value=str(fecha_local()),
            read_only=True,
            col={"sm": 8, "md": 3},
            height=42,
            text_size=13,
            dense=True
        )
        self.btn_cal_gastos = ft.IconButton(
            icon=ft.icons.CALENDAR_MONTH,
            icon_color=ft.colors.BLUE,
            on_click=lambda _: self.page.open(self.date_picker_gastos),
            col={"sm": 4, "md": 1}
        )
        self.btn_buscar_gastos = ft.ElevatedButton(
            "Consultar Día",
            icon=ft.icons.SEARCH,
            on_click=lambda _: self.cargar_gastos_dia(),
            bgcolor=ft.colors.BLUE_700,
            color=ft.colors.WHITE,
            col={"sm": 12, "md": 4},
            height=42
        )
        self.btn_nuevo_gasto = ft.ElevatedButton(
            "Registrar Egreso",
            icon=ft.icons.ADD_CARD,
            on_click=lambda _: self.abrir_nuevo_gasto(),
            bgcolor=ft.colors.RED_700,
            color=ft.colors.WHITE,
            col={"sm": 12, "md": 4},
            height=42
        )

        self.tabla_gastos = ft.DataTable(
            heading_row_color=ft.colors.GREY_100,
            border_radius=8,
            border=ft.border.all(1, ft.colors.GREY_200),
            columns=[
                ft.DataColumn(ft.Text("N°", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Hora", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Concepto / Motivo", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Categoría", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Monto (S/)", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Comprobante", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Usuario", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Acciones", weight=ft.FontWeight.BOLD))
            ],
            rows=[]
        )

        self.tab_gastos_caja = ft.Container(
            content=ft.Column([
                ft.Row([
                    self.card_total_gastos,
                    ft.Container(expand=True),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.ResponsiveRow([self.input_fecha_gastos, self.btn_cal_gastos, self.btn_buscar_gastos, self.btn_nuevo_gasto]),
                ft.Divider(),
                ft.Column([self.tabla_gastos], scroll=ft.ScrollMode.AUTO)
            ]),
            visible=False
        )

        # --- TAB 4: HISTORIAL DE CIERRES DE TURNO ---
        self.tabla_cierres_caja = ft.DataTable(
            heading_row_color=ft.colors.GREY_100,
            border_radius=8,
            border=ft.border.all(1, ft.colors.GREY_200),
            columns=[
                ft.DataColumn(ft.Text("Turno", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Fecha", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Hora", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Cajero", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Apertura (S/)", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Esperado (S/)", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Físico (S/)", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Diferencia (S/)", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Estado", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Acciones", weight=ft.FontWeight.BOLD))
            ],
            rows=[]
        )

        self.btn_recargar_cierres = ft.ElevatedButton(
            "Actualizar Historial",
            icon=ft.icons.REFRESH,
            on_click=self.cargar_historial_cierres,
            bgcolor=ft.colors.BLUE_GREY_700,
            color=ft.colors.WHITE,
            height=45
        )

        self.tab_historial_cierres = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("Historial de Cierres de Turno y Cuadres de Caja", size=16, weight=ft.FontWeight.BOLD, color="#1E293B"),
                    ft.Container(expand=True),
                    self.btn_recargar_cierres
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(),
                ft.Column([self.tabla_cierres_caja], scroll=ft.ScrollMode.AUTO)
            ]),
            visible=False
        )

        # --- NAVEGACIÓN POR PESTAÑAS ---
        self.tabs_cajas = ft.Tabs(
            selected_index=0,
            animation_duration=200,
            tabs=[
                ft.Tab(text="Control de Caja y Arqueo", icon=ft.icons.POINT_OF_SALE),
                ft.Tab(text="Cuentas por Cobrar (Créditos)", icon=ft.icons.ACCOUNT_BALANCE_WALLET),
                ft.Tab(text="Gastos y Caja Chica", icon=ft.icons.MONEY_OFF),
                ft.Tab(text="Historial de Cierres de Turno", icon=ft.icons.HISTORY)
            ],
            on_change=self.cambiar_pestana_cajas
        )

        # Montaje del contenedor principal
        self.content = ft.Column([
            ft.Text("Gestión Financiera y Cajas", size=24, weight=ft.FontWeight.BOLD),
            self.tabs_cajas,
            self.tab_caja_diaria,
            self.tab_cuentas_cobrar,
            self.tab_gastos_caja,
            self.tab_historial_cierres
        ], spacing=15)

    def construir_dialogos(self):
        # 1. Diálogo Arqueo
        self.inp_base_inicial = ft.TextField(label="Base Inicial de Apertura (S/)", value="0.00", keyboard_type=ft.KeyboardType.NUMBER, col={"sm": 12, "md": 6}, height=42, text_size=13, dense=True)
        self.inp_gastos_salidas = ft.TextField(label="Gastos / Salidas de Caja (S/)", value="0.00", read_only=True, helper_text="Calculado automáticamente desde gastos registrados", col={"sm": 12, "md": 6}, height=42, text_size=13, dense=True)
        self.inp_conteo_fisico = ft.TextField(label="Efectivo Físico Contado en Gaveta (S/)", value="0.00", keyboard_type=ft.KeyboardType.NUMBER, col={"sm": 12}, height=42, text_size=13, dense=True)
        self.inp_obs_cierre = ft.TextField(label="Observaciones del Cierre de Turno (Opcional)", multiline=True, min_lines=2, max_lines=3, col={"sm": 12}, text_size=13, dense=True)
        self.lbl_arq_ventas = ft.Text("Efectivo por Ventas del Día: S/ 0.00", size=13, weight=ft.FontWeight.BOLD)
        self.lbl_arq_cobranzas = ft.Text("Cobranzas Crédito en Efectivo: S/ 0.00", size=13, weight=ft.FontWeight.BOLD, color=ft.colors.TEAL_800)
        self.lbl_arq_esperado = ft.Text("Total Esperado en Caja: S/ 0.00", size=16, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_900)
        self.lbl_arq_resultado = ft.Text("Diferencia: S/ 0.00 (Cuadrada)", size=18, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN)

        self.inp_base_inicial.on_change = self.recalcular_arqueo
        self.inp_gastos_salidas.on_change = self.recalcular_arqueo
        self.inp_conteo_fisico.on_change = self.recalcular_arqueo

        self.dialogo_arqueo = ft.AlertDialog(
            title=ft.Text("Arqueo y Cuadre de Caja Diario", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=520,
                content=ft.Column([
                    ft.Text("Ingresa los montos para verificar si el efectivo físico coincide con el sistema:", size=13, color=ft.colors.GREY_700),
                    ft.Divider(),
                    ft.ResponsiveRow([self.inp_base_inicial, self.inp_gastos_salidas]),
                    self.lbl_arq_ventas,
                    self.lbl_arq_cobranzas,
                    ft.Divider(),
                    self.lbl_arq_esperado,
                    ft.Divider(),
                    ft.ResponsiveRow([self.inp_conteo_fisico]),
                    ft.Container(height=5),
                    self.lbl_arq_resultado,
                    ft.Divider(),
                    ft.ResponsiveRow([self.inp_obs_cierre])
                ], tight=True)
            ),
            actions=[
                ft.TextButton("Cerrar", on_click=self.cerrar_arqueo),
                ft.ElevatedButton("💾 Guardar y Cerrar Turno Formal", icon=ft.icons.LOCK_CLOCK, bgcolor=ft.colors.BLUE_800, color=ft.colors.WHITE, on_click=self.guardar_cierre_turno_formal)
            ]
        )

        # 2. Diálogo Abono de Crédito
        self.lbl_info_abono = ft.Text("", size=14)
        self.inp_monto_abono = ft.TextField(label="Monto a Abonar (S/)", keyboard_type=ft.KeyboardType.NUMBER, col={"sm": 12, "md": 6}, height=42, text_size=13, dense=True)
        self.drop_metodo_abono = ft.Dropdown(
            label="Método de Pago",
            options=[
                ft.dropdown.Option("Efectivo"),
                ft.dropdown.Option("Yape"),
                ft.dropdown.Option("Tarjeta"),
                ft.dropdown.Option("Transferencia")
            ],
            value="Efectivo", col={"sm": 12, "md": 6},
            height=42, text_size=13, dense=True
        )
        self.inp_obs_abono = ft.TextField(label="Observación / Nota del Abono (Opcional)", col={"sm": 12}, height=42, text_size=13, dense=True)

        self.dialogo_abono = ft.AlertDialog(
            title=ft.Text("Registrar Cobro / Abono de Crédito", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=500,
                content=ft.Column([
                    self.lbl_info_abono,
                    ft.Divider(),
                    ft.ResponsiveRow([self.inp_monto_abono, self.drop_metodo_abono]),
                    ft.ResponsiveRow([self.inp_obs_abono])
                ], tight=True)
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.close(self.dialogo_abono)),
                ft.ElevatedButton("Guardar Abono", bgcolor=ft.colors.GREEN_700, color=ft.colors.WHITE, on_click=self.guardar_cobro_credito)
            ]
        )

        # 3. Diálogo Historial de Abonos
        self.tabla_historial_abonos = ft.DataTable(
            heading_row_color=ft.colors.GREY_100,
            border_radius=6,
            border=ft.border.all(1, ft.colors.GREY_200),
            columns=[
                ft.DataColumn(ft.Text("Fecha", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Hora", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Monto (S/)", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Método", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Usuario", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Nota", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Recibo", weight=ft.FontWeight.BOLD))
            ],
            rows=[]
        )
        self.lbl_historial_titulo = ft.Text("", weight=ft.FontWeight.BOLD, size=14)

        self.dialogo_historial_abonos = ft.AlertDialog(
            title=ft.Text("Historial de Abonos del Crédito", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=720,
                content=ft.Column([
                    self.lbl_historial_titulo,
                    ft.Divider(),
                    ft.Container(content=ft.Column([self.tabla_historial_abonos], scroll=ft.ScrollMode.AUTO), height=300)
                ], tight=True)
            ),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda _: self.page.close(self.dialogo_historial_abonos))
            ]
        )

        # 4. Diálogo Nuevo Gasto
        self.inp_gasto_concepto = ft.TextField(label="Concepto / Detalle del Gasto", col={"sm": 12}, height=42, text_size=13, dense=True)
        self.inp_gasto_monto = ft.TextField(label="Monto en Soles (S/)", keyboard_type=ft.KeyboardType.NUMBER, col={"sm": 12, "md": 6}, height=42, text_size=13, dense=True)
        self.drop_gasto_cat = ft.Dropdown(
            label="Categoría",
            options=[
                ft.dropdown.Option("Suministros / Tienda"),
                ft.dropdown.Option("Servicios Básicos"),
                ft.dropdown.Option("Personal / Comida"),
                ft.dropdown.Option("Transporte / Delivery"),
                ft.dropdown.Option("Mantenimiento"),
                ft.dropdown.Option("Otro")
            ],
            value="Suministros / Tienda", col={"sm": 12, "md": 6},
            height=42, text_size=13, dense=True
        )
        self.inp_gasto_comp = ft.TextField(label="N° Comprobante / Recibo (Opcional)", col={"sm": 12}, height=42, text_size=13, dense=True)

        self.dialogo_nuevo_gasto = ft.AlertDialog(
            title=ft.Text("Registrar Egreso / Gasto de Caja Chica", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=500,
                content=ft.Column([
                    ft.Text("Registra una salida de dinero en efectivo de la gaveta:", size=13, color=ft.colors.GREY_700),
                    ft.Divider(),
                    ft.ResponsiveRow([self.inp_gasto_concepto]),
                    ft.ResponsiveRow([self.inp_gasto_monto, self.drop_gasto_cat]),
                    ft.ResponsiveRow([self.inp_gasto_comp])
                ], tight=True)
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.close(self.dialogo_nuevo_gasto)),
                ft.ElevatedButton("Guardar Egreso", bgcolor=ft.colors.RED_700, color=ft.colors.WHITE, on_click=self.guardar_gasto)
            ]
        )

    # --- CONTROLADORES DE FECHA Y PESTAÑAS ---
    def cambiar_fecha_calendario(self, e):
        if self.date_picker_cajas.value:
            self.input_fecha_caja.value = self.date_picker_cajas.value.strftime("%Y-%m-%d")
            self.cargar_datos_cajas()

    def cambiar_fecha_gastos(self, e):
        if self.date_picker_gastos.value:
            self.input_fecha_gastos.value = self.date_picker_gastos.value.strftime("%Y-%m-%d")
            self.cargar_gastos_dia()

    def cambiar_pestana_cajas(self, e):
        idx = self.tabs_cajas.selected_index
        self.tab_caja_diaria.visible = (idx == 0)
        self.tab_cuentas_cobrar.visible = (idx == 1)
        self.tab_gastos_caja.visible = (idx == 2)
        self.tab_historial_cierres.visible = (idx == 3)
        if idx == 0:
            self.cargar_datos_cajas()
        elif idx == 1:
            self.cargar_cuentas_cobrar()
        elif idx == 2:
            self.cargar_gastos_dia()
        elif idx == 3:
            self.cargar_historial_cierres()
        self.page.update()

    def refrescar_datos(self):
        hoy_str = str(fecha_local())
        self.input_fecha_caja.value = hoy_str
        self.input_fecha_gastos.value = hoy_str
        self.cargar_datos_cajas()
        self.cargar_cuentas_cobrar()
        self.cargar_gastos_dia()

    # --- LÓGICA DE CONTROL DE CAJA Y ARQUEO ---
    def cargar_datos_cajas(self, e=None):
        self.tabla_cajas.rows.clear()
        hoy = fecha_local()
        fecha_val = self.input_fecha_caja.value if self.input_fecha_caja.value else str(hoy)
        try:
            fecha_dt = datetime.datetime.strptime(str(fecha_val), "%Y-%m-%d").date()
            if fecha_dt > hoy:
                self.page.open(ft.SnackBar(ft.Text("⚠️ La fecha seleccionada es futura. Mostrando datos de hoy.", color=ft.colors.WHITE), bgcolor=ft.colors.ORANGE_800))
                self.input_fecha_caja.value = str(hoy)
                fecha_consulta = hoy
            else:
                fecha_consulta = fecha_dt
        except Exception:
            fecha_consulta = hoy

        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT codigo_ticket, hora_emision, metodo_pago, monto_efectivo, monto_yape, monto_plin, monto_tarjeta, total_pen, total_usd, vuelto, condicion_pago 
                    FROM ventas WHERE fecha_emision = %s AND estado != 'Anulada' ORDER BY hora_emision DESC
                """, (fecha_consulta,))
                filas = cursor.fetchall()

                tot_ef, tot_ya, tot_tr, tot_ta, tot_cred, tot_gral, tot_usd = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
                for fila in filas:
                    cod, hora, met, ef, ya, pl, ta, total, t_usd, vuelto, *resto = fila
                    cond = resto[0] if resto and resto[0] else "Contado"
                    ef_neto = float(ef) - float(vuelto) 
                    m_ya = float(ya)
                    m_tr = float(pl)
                    
                    if cond == "Crédito":
                        tot_cred += float(total)
                        color_cond = ft.colors.BLUE_700
                    else:
                        tot_ef += ef_neto
                        tot_ya += m_ya
                        tot_tr += m_tr
                        tot_ta += float(ta)
                        color_cond = ft.colors.GREEN_700
                        
                    tot_gral += float(total)
                    tot_usd += float(t_usd)
                    
                    self.tabla_cajas.rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text(cod)), ft.DataCell(ft.Text(str(hora))),
                        ft.DataCell(ft.Text(cond, color=color_cond, weight=ft.FontWeight.BOLD)),
                        ft.DataCell(ft.Text(met)),
                        ft.DataCell(ft.Text(f"{ef_neto:.2f}")), ft.DataCell(ft.Text(f"{m_ya:.2f}")), 
                        ft.DataCell(ft.Text(f"{float(ta):.2f}")), ft.DataCell(ft.Text(f"{float(total):.2f}", weight=ft.FontWeight.BOLD)),
                        ft.DataCell(ft.Text(f"{float(t_usd):.2f}", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_800))
                    ]))

                cursor.execute("SELECT COALESCE(SUM(monto), 0) FROM pagos_credito WHERE fecha = %s AND metodo_pago = 'Efectivo'", (fecha_consulta,))
                row_cob = cursor.fetchone()
                tot_cob_ef = float(row_cob[0]) if row_cob else 0.0

                cursor.execute("SELECT COALESCE(SUM(monto), 0) FROM gastos WHERE fecha = %s", (fecha_consulta,))
                row_gas = cursor.fetchone()
                tot_gas = float(row_gas[0]) if row_gas else 0.0
                
                self.monto_efectivo_ventas = tot_ef
                self.monto_cobranzas_efectivo = tot_cob_ef
                self.monto_gastos_dia = tot_gas

                self.totales_cierre_actual["ventas_efectivo"] = tot_ef
                self.totales_cierre_actual["ventas_yape"] = tot_ya
                self.totales_cierre_actual["ventas_transferencia"] = tot_tr
                self.totales_cierre_actual["ventas_tarjeta"] = tot_ta
                self.totales_cierre_actual["ventas_dolares"] = tot_usd
                self.totales_cierre_actual["abonos_efectivo"] = tot_cob_ef
                self.totales_cierre_actual["gastos"] = tot_gas

                self.lbl_caja_efectivo.value = f"S/ {tot_ef:.2f}"
                self.lbl_caja_cobranzas.value = f"S/ {tot_cob_ef:.2f}"
                self.lbl_caja_yape.value = f"S/ {tot_ya:.2f}"
                self.lbl_caja_tarjeta.value = f"S/ {tot_ta:.2f}"
                self.lbl_caja_credito.value = f"S/ {tot_cred:.2f}"
                self.lbl_caja_gastos.value = f"S/ {tot_gas:.2f}"
                self.lbl_caja_total.value = f"S/ {tot_gral:.2f}"
                self.lbl_caja_dolares.value = f"$ {tot_usd:.2f}"
            
            self.page.update()
        except Exception as ex:
            print(f"Error cajas: {ex}")

    def recalcular_arqueo(self, e=None):
        try:
            base = float(self.inp_base_inicial.value) if self.inp_base_inicial.value else 0.0
            gastos = float(self.inp_gastos_salidas.value) if self.inp_gastos_salidas.value else 0.0
            fisico = float(self.inp_conteo_fisico.value) if self.inp_conteo_fisico.value else 0.0
            ventas_ef = self.monto_efectivo_ventas
            cob_ef = self.monto_cobranzas_efectivo
            
            esperado = base + ventas_ef + cob_ef - gastos
            dif = fisico - esperado
            
            self.lbl_arq_ventas.value = f"Efectivo por Ventas del Día: S/ {ventas_ef:.2f}"
            self.lbl_arq_cobranzas.value = f"Cobranzas Crédito en Efectivo: S/ {cob_ef:.2f}"
            self.lbl_arq_esperado.value = f"Total Esperado en Caja: S/ {esperado:.2f}"
            
            if abs(dif) < 0.01:
                self.lbl_arq_resultado.value = "✅ Caja Cuadrada Exacta (S/ 0.00)"
                self.lbl_arq_resultado.color = ft.colors.GREEN
            elif dif > 0:
                self.lbl_arq_resultado.value = f"🔵 Sobrante en Caja: +S/ {dif:.2f}"
                self.lbl_arq_resultado.color = ft.colors.BLUE_700
            else:
                self.lbl_arq_resultado.value = f"❌ Faltante en Caja: -S/ {abs(dif):.2f}"
                self.lbl_arq_resultado.color = ft.colors.RED
            self.page.update()
        except ValueError:
            pass

    def cerrar_arqueo(self, e=None):
        self.page.close(self.dialogo_arqueo)

    def abrir_arqueo(self, e=None):
        self.inp_gastos_salidas.value = f"{self.monto_gastos_dia:.2f}"
        self.inp_obs_cierre.value = ""
        self.recalcular_arqueo()
        self.page.open(self.dialogo_arqueo)

    def guardar_cierre_turno_formal(self, e=None):
        boton = e.control if (e and hasattr(e, 'control') and e.control) else None
        if boton:
            boton.disabled = True
            self.page.update()
        try:
            base = float(self.inp_base_inicial.value) if self.inp_base_inicial.value else 0.0
            gastos = self.totales_cierre_actual.get("gastos", 0.0)
            fisico = float(self.inp_conteo_fisico.value) if self.inp_conteo_fisico.value else 0.0
            ventas_ef = self.totales_cierre_actual.get("ventas_efectivo", 0.0)
            cob_ef = self.totales_cierre_actual.get("abonos_efectivo", 0.0)
            
            esperado = base + ventas_ef + cob_ef - gastos
            dif = fisico - esperado
            
            if abs(dif) < 0.01:
                estado_cuadre = "CUADRADO"
            elif dif > 0:
                estado_cuadre = "SOBRANTE"
            else:
                estado_cuadre = "FALTANTE"

            ahora_pe = ahora_local()
            usr = self.page.nombre_usuario if hasattr(self.page, 'nombre_usuario') and self.page.nombre_usuario else "Admin"
            obs = self.inp_obs_cierre.value.strip()

            with obtener_cursor(commit=True) as cursor:
                cursor.execute("""
                    INSERT INTO cierres_caja (
                        fecha, hora, usuario, monto_apertura,
                        total_ventas_efectivo, total_ventas_yape, total_ventas_transferencia, total_ventas_tarjeta, total_ventas_dolares,
                        total_abonos_cobrados, total_gastos,
                        efectivo_esperado, efectivo_real_conteo, diferencia, estado_cuadre, observaciones
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    ahora_pe.date(), ahora_pe.time(), usr, base,
                    ventas_ef, self.totales_cierre_actual.get("ventas_yape", 0.0), self.totales_cierre_actual.get("ventas_transferencia", 0.0), self.totales_cierre_actual.get("ventas_tarjeta", 0.0), self.totales_cierre_actual.get("ventas_dolares", 0.0),
                    cob_ef, gastos,
                    esperado, fisico, dif, estado_cuadre, obs
                ))
                id_nuevo_cierre = cursor.lastrowid

            self.page.close(self.dialogo_arqueo)
            self.page.open(ft.SnackBar(ft.Text(f"✅ Turno cerrado formalmente (N° CC-{id_nuevo_cierre:05d}).", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
            exportar_cierre_turno_pdf(self.page, id_nuevo_cierre)
            self.cargar_historial_cierres()
        except Exception as ex:
            print(f"Error al guardar cierre de turno: {ex}")
            self.page.open(ft.SnackBar(ft.Text(f"❌ Error al guardar cierre: {ex}"), bgcolor=ft.colors.RED))
        finally:
            if boton:
                boton.disabled = False
                self.page.update()

    # --- LÓGICA DE CUENTAS POR COBRAR (CRÉDITOS) ---
    def abrir_cobro_credito(self, id_v, cod, cli, saldo):
        self.datos_credito_seleccionado = (id_v, cod, cli, saldo)
        self.lbl_info_abono.value = f"Ticket: {cod} | Cliente: {cli}\nSaldo pendiente actual: S/ {saldo:.2f}"
        self.inp_monto_abono.value = f"{saldo:.2f}"
        self.drop_metodo_abono.value = "Efectivo"
        self.inp_obs_abono.value = ""
        self.page.open(self.dialogo_abono)

    def guardar_cobro_credito(self, e=None):
        info = self.datos_credito_seleccionado
        if not info:
            return
        id_v, cod, cli, saldo_act = info
        try:
            monto = float(self.inp_monto_abono.value)
            if monto <= 0:
                self.page.open(ft.SnackBar(ft.Text("El monto del abono debe ser mayor a 0."), bgcolor=ft.colors.RED))
                return
            if monto > (saldo_act + 0.01):
                self.page.open(ft.SnackBar(ft.Text(f"El abono no puede superar la deuda (S/ {saldo_act:.2f})."), bgcolor=ft.colors.RED))
                return
        except ValueError:
            self.page.open(ft.SnackBar(ft.Text("Monto inválido."), bgcolor=ft.colors.RED))
            return

        ahora_pe = ahora_local()
        usr = self.page.nombre_usuario if hasattr(self.page, 'nombre_usuario') and self.page.nombre_usuario else "Admin"

        try:
            with obtener_cursor(commit=True) as cursor:
                cursor.execute("""
                    INSERT INTO pagos_credito (id_venta, fecha, hora, monto, metodo_pago, usuario, observaciones)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (id_v, ahora_pe.date(), ahora_pe.time(), monto, self.drop_metodo_abono.value, usr, self.inp_obs_abono.value.strip()))
                id_nuevo_pago = cursor.lastrowid

                nuevo_saldo = saldo_act - monto
                if nuevo_saldo <= 0.01:
                    cursor.execute("UPDATE ventas SET estado = 'Pagada' WHERE id_venta = %s", (id_v,))

            self.page.close(self.dialogo_abono)
            self.cargar_cuentas_cobrar()
            self.cargar_datos_cajas()

            def imprimir_recibo_accion(ev):
                self.page.close(dialogo_abono_exito)
                exportar_recibo_abono_pdf(self.page, id_nuevo_pago)

            dialogo_abono_exito = ft.AlertDialog(
                title=ft.Row([ft.Icon(ft.icons.CHECK_CIRCLE, color=ft.colors.GREEN), ft.Text("Abono Registrado", weight=ft.FontWeight.BOLD)]),
                content=ft.Text(f"Se registró correctamente el abono de S/ {monto:.2f} para el ticket {cod}.\n\n¿Desea imprimir el recibo de abono en PDF térmico?"),
                actions=[
                    ft.TextButton("No, Cerrar", on_click=lambda _: self.page.close(dialogo_abono_exito)),
                    ft.ElevatedButton("Imprimir Recibo", icon=ft.icons.PRINT, bgcolor=ft.colors.BLUE_700, color=ft.colors.WHITE, on_click=imprimir_recibo_accion)
                ]
            )
            self.page.open(dialogo_abono_exito)
        except Exception as ex:
            print(f"Error registrando abono: {ex}")
            self.page.open(ft.SnackBar(ft.Text(f"❌ Error al registrar abono: {ex}"), bgcolor=ft.colors.RED))

    def abrir_historial_credito(self, id_v, cod, cli):
        self.tabla_historial_abonos.rows.clear()
        self.lbl_historial_titulo.value = f"Abonos registrados para Ticket: {cod} ({cli})"
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT id_pago, fecha, hora, monto, metodo_pago, usuario, observaciones
                    FROM pagos_credito WHERE id_venta = %s ORDER BY fecha DESC, hora DESC
                """, (id_v,))
                filas = cursor.fetchall()
                if filas:
                    for f in filas:
                        id_p_hist = f[0]
                        btn_recibo = ft.IconButton(
                            icon=ft.icons.PRINT, icon_color=ft.colors.BLUE_700, tooltip="Reimprimir Recibo",
                            on_click=lambda ev, ip=id_p_hist: exportar_recibo_abono_pdf(self.page, ip)
                        )
                        self.tabla_historial_abonos.rows.append(ft.DataRow(cells=[
                            ft.DataCell(ft.Text(str(f[1]))),
                            ft.DataCell(ft.Text(str(f[2]))),
                            ft.DataCell(ft.Text(f"{float(f[3]):.2f}", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_800)),
                            ft.DataCell(ft.Text(str(f[4]))),
                            ft.DataCell(ft.Text(str(f[5]))),
                            ft.DataCell(ft.Text(str(f[6] or "-"))),
                            ft.DataCell(btn_recibo)
                        ]))
                else:
                    self.tabla_historial_abonos.rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text("Sin abonos registrados aún.")),
                        ft.DataCell(ft.Text("")), ft.DataCell(ft.Text("")),
                        ft.DataCell(ft.Text("")), ft.DataCell(ft.Text("")), ft.DataCell(ft.Text("")),
                        ft.DataCell(ft.Text(""))
                    ]))
            self.page.open(self.dialogo_historial_abonos)
        except Exception as ex:
            print(f"Error historial abonos: {ex}")

    def cargar_cuentas_cobrar(self, e=None):
        self.tabla_creditos.rows.clear()
        busqueda = (self.input_buscar_credito.value or "").strip().lower()
        solo_pend = self.check_solo_pendientes.value

        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT v.id_venta, v.codigo_ticket, v.fecha_emision, v.cliente_nombre, v.cliente_dni, v.total_pen, v.estado,
                           COALESCE((SELECT SUM(p.monto) FROM pagos_credito p WHERE p.id_venta = v.id_venta), 0) AS total_abonado
                    FROM ventas v
                    WHERE v.condicion_pago = 'Crédito' AND v.estado != 'Anulada'
                    ORDER BY v.fecha_emision DESC, v.hora_emision DESC
                """)
                filas = cursor.fetchall()

            total_deuda_global = 0.0
            for f in filas:
                id_v, cod, fec, cli, dni, total_venta, est, abonado = f
                tot_v = float(total_venta or 0.0)
                tot_ab = float(abonado or 0.0)
                saldo = max(0.0, tot_v - tot_ab)

                cli_str = str(cli or "VARIOS")
                dni_str = str(dni or "-")
                cod_str = str(cod or "")

                if busqueda:
                    if busqueda not in cli_str.lower() and busqueda not in dni_str.lower() and busqueda not in cod_str.lower():
                        continue

                es_liquidado = saldo <= 0.001
                if solo_pend and es_liquidado:
                    continue

                if not es_liquidado:
                    total_deuda_global += saldo

                badge_estado = ft.Container(
                    content=ft.Text("LIQUIDADO" if es_liquidado else "PENDIENTE", size=11, weight=ft.FontWeight.BOLD, color=ft.colors.WHITE),
                    bgcolor=ft.colors.GREEN_700 if es_liquidado else ft.colors.ORANGE_800,
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    border_radius=6
                )

                btn_abono = ft.IconButton(
                    icon=ft.icons.PAYMENTS, icon_color=ft.colors.GREEN_700, tooltip="Abonar / Cobrar",
                    disabled=es_liquidado,
                    on_click=lambda ev, iv=id_v, c=cod_str, cl=cli_str, s=saldo: self.abrir_cobro_credito(iv, c, cl, s)
                )
                btn_hist = ft.IconButton(
                    icon=ft.icons.RECEIPT_LONG, icon_color=ft.colors.BLUE_700, tooltip="Ver Pagos",
                    on_click=lambda ev, iv=id_v, c=cod_str, cl=cli_str: self.abrir_historial_credito(iv, c, cl)
                )

                self.tabla_creditos.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(cod_str, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(str(fec))),
                    ft.DataCell(ft.Text(cli_str)),
                    ft.DataCell(ft.Text(dni_str)),
                    ft.DataCell(ft.Text(f"{tot_v:.2f}")),
                    ft.DataCell(ft.Text(f"{tot_ab:.2f}", color=ft.colors.GREEN_800, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(f"{saldo:.2f}", color=ft.colors.RED_700 if saldo > 0 else ft.colors.BLACK, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(badge_estado),
                    ft.DataCell(ft.Row([btn_abono, btn_hist], spacing=0))
                ]))

            self.lbl_total_por_cobrar.value = f"S/ {total_deuda_global:.2f}"
            self.page.update()
        except Exception as ex:
            print(f"Error cargando creditos: {ex}")

    # --- LÓGICA DE GASTOS Y CAJA CHICA ---
    def abrir_nuevo_gasto(self, e=None):
        self.inp_gasto_concepto.value = ""
        self.inp_gasto_monto.value = ""
        self.inp_gasto_comp.value = ""
        self.drop_gasto_cat.value = "Suministros / Tienda"
        self.page.open(self.dialogo_nuevo_gasto)

    def guardar_gasto(self, e=None):
        con = (self.inp_gasto_concepto.value or "").strip()
        if not con:
            self.page.open(ft.SnackBar(ft.Text("Debe ingresar el concepto o motivo del gasto."), bgcolor=ft.colors.RED))
            return
        try:
            m = float(self.inp_gasto_monto.value)
            if m <= 0:
                self.page.open(ft.SnackBar(ft.Text("El monto debe ser mayor a 0."), bgcolor=ft.colors.RED))
                return
        except ValueError:
            self.page.open(ft.SnackBar(ft.Text("Monto inválido."), bgcolor=ft.colors.RED))
            return

        ahora_pe = ahora_local()
        fecha_g = self.input_fecha_gastos.value if self.input_fecha_gastos.value else ahora_pe.date()
        usr = self.page.nombre_usuario if hasattr(self.page, 'nombre_usuario') and self.page.nombre_usuario else "Admin"

        try:
            with obtener_cursor(commit=True) as cursor:
                cursor.execute("""
                    INSERT INTO gastos (fecha, hora, concepto, monto, categoria, usuario, comprobante)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (fecha_g, ahora_pe.time(), con, m, self.drop_gasto_cat.value, usr, self.inp_gasto_comp.value.strip()))

            self.page.close(self.dialogo_nuevo_gasto)
            self.cargar_gastos_dia()
            self.cargar_datos_cajas()
            self.page.open(ft.SnackBar(ft.Text(f"✅ Gasto de S/ {m:.2f} registrado correctamente."), bgcolor=ft.colors.GREEN))
        except Exception as ex:
            print(f"Error guardando gasto: {ex}")
            self.page.open(ft.SnackBar(ft.Text(f"❌ Error al guardar gasto: {ex}"), bgcolor=ft.colors.RED))

    def _eliminar_gasto_bd_confirmado(self, id_g):
        try:
            with obtener_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM gastos WHERE id_gasto = %s", (id_g,))
            self.cargar_gastos_dia()
            self.cargar_datos_cajas()
            self.page.open(ft.SnackBar(ft.Text("✅ Gasto eliminado correctamente."), bgcolor=ft.colors.GREEN))
        except Exception as ex:
            print(f"Error eliminando gasto: {ex}")
            self.page.open(ft.SnackBar(ft.Text(f"❌ Error al eliminar gasto: {ex}"), bgcolor=ft.colors.RED))

    def eliminar_gasto_bd(self, id_g):
        if self.fn_solicitar_password:
            self.fn_solicitar_password(lambda: self._eliminar_gasto_bd_confirmado(id_g))
        else:
            self._eliminar_gasto_bd_confirmado(id_g)

    def cargar_gastos_dia(self, e=None):
        self.tabla_gastos.rows.clear()
        fecha_g = self.input_fecha_gastos.value if self.input_fecha_gastos.value else fecha_local()

        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT id_gasto, hora, concepto, categoria, monto, comprobante, usuario
                    FROM gastos WHERE fecha = %s ORDER BY hora DESC
                """, (fecha_g,))
                filas = cursor.fetchall()

            total_gas = 0.0
            for idx, f in enumerate(filas, 1):
                id_g, hora, con, cat, mon, comp, usr = f
                m_fl = float(mon or 0.0)
                total_gas += m_fl

                badge_cat = ft.Container(
                    content=ft.Text(str(cat or "General"), size=11, color=ft.colors.BLUE_900),
                    bgcolor=ft.colors.BLUE_50,
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    border_radius=6, border=ft.border.all(1, ft.colors.BLUE_200)
                )

                btn_borrar = ft.IconButton(
                    icon=ft.icons.DELETE_OUTLINE, icon_color=ft.colors.RED_600, tooltip="Eliminar Gasto",
                    on_click=lambda ev, ig=id_g: self.eliminar_gasto_bd(ig)
                )

                self.tabla_gastos.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(idx))),
                    ft.DataCell(ft.Text(str(hora))),
                    ft.DataCell(ft.Text(str(con))),
                    ft.DataCell(badge_cat),
                    ft.DataCell(ft.Text(f"{m_fl:.2f}", weight=ft.FontWeight.BOLD, color=ft.colors.RED_700)),
                    ft.DataCell(ft.Text(str(comp or "-"))),
                    ft.DataCell(ft.Text(str(usr or "Admin"))),
                    ft.DataCell(btn_borrar)
                ]))

            self.lbl_total_gastos_dia.value = f"S/ {total_gas:.2f}"
            self.page.update()
        except Exception as ex:
            print(f"Error cargando gastos: {ex}")

    # --- LÓGICA DE HISTORIAL DE CIERRES DE TURNO ---
    def cargar_historial_cierres(self, e=None):
        self.tabla_cierres_caja.rows.clear()
        try:
            with obtener_cursor() as cursor:
                cursor.execute("""
                    SELECT id_cierre, fecha, hora, usuario, monto_apertura, efectivo_esperado, efectivo_real_conteo, diferencia, estado_cuadre
                    FROM cierres_caja ORDER BY id_cierre DESC LIMIT 50
                """)
                filas = cursor.fetchall()
                if filas:
                    for f in filas:
                        cid, cfe, cho, cusr, cape, cesp, cfis, cdif, cest = f
                        color_est = ft.colors.GREEN_700 if cest == "CUADRADO" else (ft.colors.BLUE_700 if cest == "SOBRANTE" else ft.colors.RED_700)
                        badge_est = ft.Container(
                            content=ft.Text(str(cest), size=11, weight=ft.FontWeight.BOLD, color=ft.colors.WHITE),
                            bgcolor=color_est,
                            padding=ft.padding.symmetric(horizontal=8, vertical=4),
                            border_radius=6
                        )
                        btn_reimprimir = ft.IconButton(
                            icon=ft.icons.PRINT, icon_color=ft.colors.BLUE_700, tooltip="Reimprimir Ticket de Cierre",
                            on_click=lambda ev, ic=cid: exportar_cierre_turno_pdf(self.page, ic)
                        )
                        self.tabla_cierres_caja.rows.append(ft.DataRow(cells=[
                            ft.DataCell(ft.Text(f"CC-{cid:05d}", weight=ft.FontWeight.BOLD)),
                            ft.DataCell(ft.Text(str(cfe))),
                            ft.DataCell(ft.Text(str(cho)[:8])),
                            ft.DataCell(ft.Text(str(cusr).upper())),
                            ft.DataCell(ft.Text(f"{float(cape):.2f}")),
                            ft.DataCell(ft.Text(f"{float(cesp):.2f}")),
                            ft.DataCell(ft.Text(f"{float(cfis):.2f}", weight=ft.FontWeight.BOLD)),
                            ft.DataCell(ft.Text(f"{float(cdif):+.2f}", weight=ft.FontWeight.BOLD, color=color_est)),
                            ft.DataCell(badge_est),
                            ft.DataCell(btn_reimprimir)
                        ]))
                else:
                    self.tabla_cierres_caja.rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text("No hay cierres de turno registrados aún.")),
                        ft.DataCell(ft.Text("")), ft.DataCell(ft.Text("")), ft.DataCell(ft.Text("")),
                        ft.DataCell(ft.Text("")), ft.DataCell(ft.Text("")), ft.DataCell(ft.Text("")),
                        ft.DataCell(ft.Text("")), ft.DataCell(ft.Text("")), ft.DataCell(ft.Text(""))
                    ]))
            self.page.update()
        except Exception as ex:
            print(f"Error cargando historial cierres: {ex}")

