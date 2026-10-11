import hashlib
import os
import time
import flet as ft

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import inicializar_tablas, obtener_cursor
from views import PosView, InventarioView, ReportesView, CajasView, ConfigView, IngresosView


def main(page: ft.Page):
    # Obtener nombre comercial desde la base de datos (con fallback)
    nombre_tienda = "LIKIO STORE"
    try:
        with obtener_cursor() as cursor:
            cursor.execute("SELECT nombre_negocio FROM configuracion LIMIT 1")
            row = cursor.fetchone()
            if row and row[0] and row[0].strip():
                nombre_tienda = row[0].strip().upper()
    except Exception:
        pass

    # Configuración base de la página
    page.rol_usuario = None  
    page.nombre_usuario = None
    page.id_usuario = None
    page.title = f"{nombre_tienda} - Sistema de Gestión"
    page.fonts = {
        "Inter": "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
    }
    page.theme = ft.Theme(font_family="Inter")
    page.theme_mode = ft.ThemeMode.LIGHT 
    page.padding = 0 
    page.bgcolor = "#F8FAFC"

    # -------------------------------------------------------------
    # 1. DIÁLOGO DE SEGURIDAD (Autorización de Administrador)
    # -------------------------------------------------------------
    accion_guardada = {"fn": None} 
    
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
                cursor.execute(
                    "SELECT id FROM usuarios WHERE TRIM(LOWER(rol)) = 'admin' AND password_hash = %s",
                    (hash_ingresado,)
                )
                es_admin = cursor.fetchone()
        except Exception as ex:
            print(f"Error técnico en seguridad: {ex}")
            es_admin = False
    
        if es_admin:
            page.close(dialogo_seguridad)
            input_pass_seguridad.value = ""
            fn_a_ejecutar = accion_guardada["fn"]
            accion_guardada["fn"] = None
            page.update()
            if fn_a_ejecutar:
                fn_a_ejecutar() 
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
        accion_guardada["fn"] = accion
        input_pass_seguridad.value = ""
        page.open(dialogo_seguridad)

    # -------------------------------------------------------------
    # 2. INSTANCIAS DE LAS VISTAS MODULARES
    # -------------------------------------------------------------
    vista_pos = PosView(page)
    vista_cajas = CajasView(page, fn_solicitar_password=solicitar_password)
    vista_inventario = InventarioView(page, solicitar_password)
    vista_ingresos = IngresosView(
        page,
        fn_solicitar_password=solicitar_password,
        fn_recargar_inventario=lambda: vista_inventario.cargar_datos_inventario()
    )
    vista_reportes = ReportesView(
        page,
        fn_ver_nota_venta=lambda id_v, cod: vista_pos.ver_nota_venta(id_v, cod),
        fn_solicitar_password=solicitar_password,
        fn_cargar_inventario=lambda: vista_inventario.cargar_datos_inventario()
    )
    vista_config = ConfigView(page)

    # Mapa de enrutamiento de vistas
    vistas = {
        "Ventas": vista_pos,
        "Cajas": vista_cajas,
        "Inventario": vista_inventario,
        "Ingresos": vista_ingresos,
        "Reportes": vista_reportes,
        "Configuración": vista_config
    }

    # -------------------------------------------------------------
    # 3. ENRUTADOR Y CONTROL DE NAVEGACIÓN
    # -------------------------------------------------------------
    def cambiar_vista(e):
        nombre_boton = e.control.data
        
        # Iterar sobre las vistas: ocultar todas y encender únicamente la elegida
        for nombre, vista in vistas.items():
            vista.visible = (nombre == nombre_boton)
        
        # Disparar actualización inicial según la vista seleccionada
        if nombre_boton == "Inventario":
            vista_inventario.cargar_datos_inventario()
        elif nombre_boton == "Ingresos":
            vista_ingresos.iniciar()
        elif nombre_boton == "Reportes":
            vista_reportes.refrescar_datos()
        elif nombre_boton == "Cajas":
            vista_cajas.refrescar_datos()
        elif nombre_boton == "Configuración":
            vista_config.iniciar()
            
        page.update()

    def aplicar_permisos_usuario():
        es_admin = (str(page.rol_usuario).strip().lower() == "admin") if getattr(page, 'rol_usuario', None) else False
        for boton in menu_lateral.content.controls:
            if hasattr(boton, 'data') and boton.data in ["Inventario", "Ingresos", "Reportes", "Cajas", "Configuración"]:
                boton.visible = es_admin

        if not es_admin:
            for nombre, vista in vistas.items():
                vista.visible = (nombre == "Ventas")
        page.update()

    # -------------------------------------------------------------
    # 4. MENÚ LATERAL Y NAVEGACIÓN
    # -------------------------------------------------------------
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
                    ft.Text(nombre_tienda, color="#F8FAFC", weight=ft.FontWeight.BOLD, size=20)
                ]),
                margin=ft.margin.only(bottom=10)
            ),
            ft.Divider(color="#334155", height=20),
            
            crear_boton_menu("Ventas", ft.icons.POINT_OF_SALE_ROUNDED, cambiar_vista),
            crear_boton_menu("Cajas", ft.icons.ACCOUNT_BALANCE_WALLET_ROUNDED, cambiar_vista),
            crear_boton_menu("Inventario", ft.icons.INVENTORY_2_ROUNDED, cambiar_vista),
            crear_boton_menu("Ingresos", ft.icons.LOCAL_SHIPPING, cambiar_vista),
            crear_boton_menu("Reportes", ft.icons.INSERT_CHART_ROUNDED, cambiar_vista),
            crear_boton_menu("Configuración", ft.icons.SETTINGS_ROUNDED, cambiar_vista),
            
            ft.Divider(color="#334155", height=20),
            crear_boton_menu("Cerrar Sesión", ft.icons.EXIT_TO_APP_ROUNDED, lambda e: cerrar_sesion(e), es_peligro=True)
        ], spacing=5)
    )

    boton_hamburguesa = ft.IconButton(icon=ft.icons.MENU, icon_size=30, on_click=toggle_menu)

    # -------------------------------------------------------------
    # 5. LAYOUT PRINCIPAL (DASHBOARD)
    # -------------------------------------------------------------
    area_derecha = ft.Column([
        ft.Row([boton_hamburguesa]),
        vista_pos,
        vista_cajas,
        vista_inventario,
        vista_ingresos,
        vista_reportes,
        vista_config
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=0, tight=True)

    vista_dashboard = ft.Row(
        [menu_lateral, area_derecha],
        visible=False,
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START
    )

    # -------------------------------------------------------------
    # 6. GESTIÓN DE SESIÓN Y LOGIN
    # -------------------------------------------------------------
    def cerrar_sesion(e):
        page.client_storage.remove("rol_usuario")
        page.client_storage.remove("nombre_usuario")
        page.client_storage.remove("id_usuario")

        page.rol_usuario = None 
        page.nombre_usuario = None
        page.id_usuario = None
        input_usuario.value = ""
        input_password.value = ""
        
        vista_dashboard.visible = False 
        vista_login.visible = True
        page.update()

    estilo_input_login = {
        "border_color": "#CBD5E1",
        "focused_border_color": "#2563EB",
        "border_radius": 8,
        "width": 320
    }

    input_usuario = ft.TextField(
        label="Correo electrónico",
        prefix_icon=ft.icons.EMAIL_OUTLINED,
        **estilo_input_login
    )
    input_password = ft.TextField(
        label="Contraseña",
        password=True,
        can_reveal_password=True,
        prefix_icon=ft.icons.LOCK_OUTLINE,
        on_submit=lambda e: iniciar_sesion(e),
        **estilo_input_login
    )

    def iniciar_sesion(e):
        btn_login.disabled = True
        btn_login.text = "Iniciando..."
        page.update()

        usuario_email = (input_usuario.value or "").strip()
        password = input_password.value or ""
        hash_ingresado = hashlib.sha256(password.encode()).hexdigest()

        try:
            with obtener_cursor() as cursor:
                cursor.execute(
                    "SELECT id, nombre, rol, password_hash FROM usuarios WHERE email = %s",
                    (usuario_email,)
                )
                datos_usuario = cursor.fetchone()
        except Exception as ex:
            page.open(ft.SnackBar(ft.Text(f"Error de conexión a BD: {ex}", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            btn_login.disabled = False
            btn_login.text = "Iniciar Sesión"
            page.update()
            return

        if not datos_usuario or hash_ingresado != datos_usuario[3]:
            page.open(ft.SnackBar(ft.Text("Credenciales incorrectas", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            btn_login.disabled = False
            btn_login.text = "Iniciar Sesión"
            page.update()
            return

        page.id_usuario = datos_usuario[0]
        page.nombre_usuario = datos_usuario[1]
        page.rol_usuario = datos_usuario[2]
        page.client_storage.set("id_usuario", page.id_usuario)
        page.client_storage.set("nombre_usuario", page.nombre_usuario)
        page.client_storage.set("rol_usuario", page.rol_usuario)
        
        btn_login.disabled = False
        btn_login.text = "Iniciar Sesión"
        vista_login.visible = False
        vista_dashboard.visible = True
        aplicar_permisos_usuario()

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
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=30,
            color=ft.colors.with_opacity(0.06, ft.colors.BLACK),
            offset=ft.Offset(0, 15)
        ),
        content=ft.Column([
            ft.Icon(ft.icons.LOCAL_BAR, size=60, color="#38BDF8"),
            ft.Text(nombre_tienda, size=26, weight=ft.FontWeight.W_800, color="#1E293B"),
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

    # -------------------------------------------------------------
    # 7. VERIFICACIÓN DE SESIÓN PERSISTENTE Y MONTAJE FINAL
    # -------------------------------------------------------------
    rol_guardado = page.client_storage.get("rol_usuario")
    nombre_guardado = page.client_storage.get("nombre_usuario")
    id_guardado = page.client_storage.get("id_usuario")
    
    if rol_guardado:
        page.rol_usuario = rol_guardado
        page.nombre_usuario = nombre_guardado or "USUARIO"
        page.id_usuario = id_guardado
        vista_login.visible = False
        vista_dashboard.visible = True
        aplicar_permisos_usuario()
    else:
        vista_login.visible = True
        vista_dashboard.visible = False

    # Montaje de las interfaces raíz
    page.add(vista_login, vista_dashboard)


def limpiar_assets_antiguos(directorio, dias=30):
    try:
        if not os.path.exists(directorio):
            return
        limite = time.time() - (dias * 86400)
        for archivo in os.listdir(directorio):
            if archivo.endswith(".pdf") or archivo.endswith(".xlsx"):
                ruta = os.path.join(directorio, archivo)
                if os.path.isfile(ruta) and os.path.getmtime(ruta) < limite:
                    try:
                        os.remove(ruta)
                    except Exception:
                        pass
    except Exception as ex:
        print(f"Error limpiando assets antiguos: {ex}")


directorio_base = os.path.dirname(os.path.abspath(__file__))
directorio_assets = os.path.join(directorio_base, "assets")
os.makedirs(directorio_assets, exist_ok=True)
limpiar_assets_antiguos(directorio_assets, dias=30)

# Inicialización única de tablas y esquemas al arrancar el servidor
inicializar_tablas()

ft.app(
    target=main,
    view=ft.WEB_BROWSER,
    assets_dir=directorio_assets,
    port=int(os.getenv("PORT", 8080))
)