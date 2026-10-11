import flet as ft
import hashlib
import pandas as pd
import os
import datetime
from database import obtener_cursor
from time_service import ahora_local

class ConfigView(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self.visible = False
        
        self.padding = 25
        self.bgcolor = ft.colors.WHITE
        self.border_radius = 16
        self.border = ft.border.all(1, "#E2E8F0")
        self.shadow = ft.BoxShadow(spread_radius=0, blur_radius=25, color=ft.colors.with_opacity(0.04, ft.colors.BLACK), offset=ft.Offset(0, 8))
        
        self.construir_interfaz()

    def tiene_permiso(self):    
        if getattr(self.page, 'rol_usuario', None) != "admin": 
            self.page.open(ft.SnackBar(ft.Text("Acceso denegado: Solo el administrador puede modificar.", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            return False
        return True

    def cargar_datos_negocio(self):
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT nombre_negocio, ruc, direccion, telefono, mensaje_ticket, COALESCE(referencia, '') FROM configuracion LIMIT 1")
                datos = cursor.fetchone()
                if datos:
                    self.input_conf_nombre.value = datos[0] or ""
                    self.input_conf_ruc.value = datos[1] or ""
                    self.input_conf_dir.value = datos[2] or ""
                    self.input_conf_tel.value = datos[3] or ""
                    self.input_conf_msg.value = datos[4] or ""
                    self.input_conf_ref.value = datos[5] or ""
            self.page.update()
        except Exception as ex: print(ex)

    def guardar_datos_negocio(self, e):
        try:
            with obtener_cursor(commit=True) as cursor:
                cursor.execute("""
                    UPDATE configuracion 
                    SET nombre_negocio=%s, ruc=%s, direccion=%s, referencia=%s, telefono=%s, mensaje_ticket=%s 
                    WHERE id=1
                """, (
                    self.input_conf_nombre.value,
                    self.input_conf_ruc.value,
                    self.input_conf_dir.value,
                    self.input_conf_ref.value,
                    self.input_conf_tel.value,
                    self.input_conf_msg.value
                ))
            self.page.open(ft.SnackBar(ft.Text("✅ Datos actualizados", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
        except Exception as ex:
            self.page.open(ft.SnackBar(ft.Text(f"❌ Error al guardar: {ex}", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def cargar_usuarios(self):
        self.tabla_usuarios.rows.clear()
        try:
            with obtener_cursor() as cursor:
                cursor.execute("SELECT id, nombre, email, rol FROM usuarios")
                for fila in cursor.fetchall():
                    id_u, nom, email, rol = fila
                    btn_borrar = ft.IconButton(ft.icons.DELETE, icon_color=ft.colors.RED, on_click=lambda e, i=id_u: self.borrar_usuario(i))
                    if rol == "admin": btn_borrar.disabled = True 
                    self.tabla_usuarios.rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text(nom)), ft.DataCell(ft.Text(email)), ft.DataCell(ft.Text(rol.upper())), ft.DataCell(btn_borrar)
                    ]))
            self.page.update()
        except Exception as ex: print(ex)

    def guardar_usuario(self, e):
        if not self.input_usr_nom.value or not self.input_usr_email.value or not self.input_usr_pass.value:
            self.page.open(ft.SnackBar(ft.Text("Campos obligatorios", color=ft.colors.WHITE), bgcolor=ft.colors.RED)); return
        try:
            hash_pass = hashlib.sha256(self.input_usr_pass.value.encode()).hexdigest()
            with obtener_cursor(commit=True) as cursor:
                cursor.execute("INSERT INTO usuarios (nombre, email, password_hash, rol) VALUES (%s, %s, %s, %s)", 
                               (self.input_usr_nom.value.strip(), self.input_usr_email.value.strip(), hash_pass, self.drop_usr_rol.value))
            self.page.open(ft.SnackBar(ft.Text("✅ Usuario registrado", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
            self.input_usr_nom.value = ""; self.input_usr_email.value = ""; self.input_usr_pass.value = ""
            self.cargar_usuarios()
        except Exception as ex:
            self.page.open(ft.SnackBar(ft.Text("❌ Error", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def borrar_usuario(self, id_u):
        try:
            with obtener_cursor(commit=True) as cursor: cursor.execute("DELETE FROM usuarios WHERE id=%s", (id_u,))
            self.page.open(ft.SnackBar(ft.Text("✅ Usuario eliminado", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
            self.cargar_usuarios()
        except: pass

    def cambiar_password_personal(self, e):
        if not self.input_pass_actual.value or not self.input_pass_nueva.value:
            self.page.open(ft.SnackBar(ft.Text("Rellene ambos campos", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            return
        hash_actual = hashlib.sha256(self.input_pass_actual.value.encode()).hexdigest()
        hash_nueva = hashlib.sha256(self.input_pass_nueva.value.encode()).hexdigest()
        try:
            with obtener_cursor(commit=True) as cursor:
                id_usr = getattr(self.page, 'id_usuario', None)
                if not id_usr:
                    self.page.open(ft.SnackBar(ft.Text("⚠️ Sesión no identificada. Cierre sesión e ingrese nuevamente.", color=ft.colors.WHITE), bgcolor=ft.colors.ORANGE_800))
                    return

                cursor.execute("SELECT id FROM usuarios WHERE id = %s AND password_hash = %s", (id_usr, hash_actual))
                if cursor.fetchone():
                    cursor.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s", (hash_nueva, id_usr))
                    self.page.open(ft.SnackBar(ft.Text("✅ Contraseña actualizada correctamente", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN))
                    self.input_pass_actual.value = ""
                    self.input_pass_nueva.value = ""
                else:
                    self.page.open(ft.SnackBar(ft.Text("❌ Contraseña actual incorrecta", color=ft.colors.WHITE), bgcolor=ft.colors.RED))
            self.page.update()
        except Exception as ex: print(ex)

    def generar_backup_completo(self, e):
        if not self.tiene_permiso(): return
        try:
            self.page.open(ft.SnackBar(ft.Text("⏳ Generando respaldo completo...", color=ft.colors.BLACK), bgcolor=ft.colors.YELLOW))
            tablas_a_respaldar = [
                ("productos", "SELECT * FROM productos ORDER BY id_producto ASC"),
                ("ventas", "SELECT * FROM ventas ORDER BY id_venta DESC"),
                ("detalles_venta", "SELECT * FROM detalles_venta ORDER BY id_detalle DESC"),
                ("historial_ingresos", "SELECT * FROM historial_ingresos ORDER BY id_ingreso DESC"),
                ("gastos", "SELECT * FROM gastos ORDER BY id_gasto DESC"),
                ("pagos_credito", "SELECT * FROM pagos_credito ORDER BY id_pago DESC"),
                ("configuracion", "SELECT * FROM configuracion"),
                ("usuarios", "SELECT id, nombre, email, rol FROM usuarios")
            ]
            os.makedirs("assets", exist_ok=True)
            timestamp = ahora_local().strftime("%Y%m%d_%H%M%S")
            nombre_archivo = f"Backup_LicorStore_{timestamp}.xlsx"
            ruta_archivo = os.path.join("assets", nombre_archivo)
            with pd.ExcelWriter(ruta_archivo, engine='openpyxl') as writer:
                with obtener_cursor() as cursor:
                    for nombre_tabla, query in tablas_a_respaldar:
                        try:
                            cursor.execute(query)
                            cols = [c[0] for c in cursor.description]
                            filas = cursor.fetchall()
                            df = pd.DataFrame(filas, columns=cols)
                            df.to_excel(writer, sheet_name=nombre_tabla[:31], index=False)
                        except Exception: pass
            self.page.launch_url(f"/{nombre_archivo}", web_window_name="_blank")
            self.page.open(ft.SnackBar(ft.Text(f"✅ ¡Copia descargada ({nombre_archivo})!", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN, duration=6000))
        except Exception as ex:
            self.page.open(ft.SnackBar(ft.Text(f"❌ Error al generar backup: {ex}", color=ft.colors.WHITE), bgcolor=ft.colors.RED))

    def cambiar_pestana_config(self, e):
        idx = self.tabs_config.selected_index
        self.tab_negocio.visible = (idx == 0)
        self.tab_usuarios.visible = (idx == 1)
        self.tab_backup.visible = (idx == 2)
        self.tab_perfil.visible = (idx == 3)
        self.page.update()

    def construir_interfaz(self):
        # Campos de configuración del negocio
        self.input_conf_nombre = ft.TextField(label="Nombre Comercial", height=42, dense=True, text_size=13, col={"sm": 12, "md": 6})
        self.input_conf_ruc = ft.TextField(label="RUC", height=42, dense=True, text_size=13, col={"sm": 12, "md": 6})
        self.input_conf_dir = ft.TextField(label="Dirección Principal", height=42, dense=True, text_size=13, col={"sm": 12, "md": 6})
        self.input_conf_ref = ft.TextField(label="Referencia (Ubicación)", hint_text="Ej: Frente a la plaza / Costado del Banco", height=42, dense=True, text_size=13, col={"sm": 12, "md": 6})
        self.input_conf_tel = ft.TextField(label="Teléfono", height=42, dense=True, text_size=13, col={"sm": 12, "md": 6})
        self.input_conf_msg = ft.TextField(label="Mensaje final del ticket", height=42, dense=True, text_size=13, col={"sm": 12, "md": 6})
        
        self.tab_negocio = ft.Container(
            padding=20,
            visible=True,
            content=ft.Column([
                ft.Text("Información para Tickets y Recibos", weight=ft.FontWeight.BOLD, size=16),
                ft.ResponsiveRow([self.input_conf_nombre, self.input_conf_ruc]),
                ft.ResponsiveRow([self.input_conf_dir, self.input_conf_ref]),
                ft.ResponsiveRow([self.input_conf_tel, self.input_conf_msg]),
                ft.ElevatedButton("Guardar Cambios", bgcolor=ft.colors.GREEN, color=ft.colors.WHITE, on_click=self.guardar_datos_negocio)
            ], spacing=15)
        )

        self.tabla_usuarios = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("Nombre")), ft.DataColumn(ft.Text("Correo")), ft.DataColumn(ft.Text("Rol")), ft.DataColumn(ft.Text("Acciones"))], rows=[]
        )
        self.input_usr_nom = ft.TextField(label="Nombre", height=42, dense=True, text_size=13, col={"sm": 12, "md": 6})
        self.input_usr_email = ft.TextField(label="Correo Electrónico", height=42, dense=True, text_size=13, col={"sm": 12, "md": 6})
        self.input_usr_pass = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, height=42, dense=True, text_size=13, col={"sm": 12, "md": 6})
        self.drop_usr_rol = ft.Dropdown(label="Rol", options=[ft.dropdown.Option("admin"), ft.dropdown.Option("vendedor")], value="vendedor", height=42, dense=True, text_size=13, col={"sm": 12, "md": 6})
        
        self.tab_usuarios = ft.Container(
            padding=20,
            visible=False,
            content=ft.Column([
                ft.Text("Registrar Nuevo Cajero/Admin", weight=ft.FontWeight.BOLD, size=16),
                ft.ResponsiveRow([self.input_usr_nom, self.input_usr_email]),
                ft.ResponsiveRow([self.input_usr_pass, self.drop_usr_rol]),
                ft.ElevatedButton("Crear Usuario", bgcolor=ft.colors.BLUE, color=ft.colors.WHITE, on_click=self.guardar_usuario),
                ft.Divider(),
                ft.Text("Usuarios Activos", weight=ft.FontWeight.BOLD, size=16),
                ft.Container(content=self.tabla_usuarios, border=ft.border.all(1, ft.colors.GREY_200), border_radius=8)
            ], scroll=ft.ScrollMode.AUTO, spacing=15)
        )

        self.tab_backup = ft.Container(
            padding=25,
            visible=False,
            content=ft.Column([
                ft.Text("Respaldo y Seguridad de Datos", weight=ft.FontWeight.BOLD, size=18),
                ft.Text("Descarga una copia completa en Excel (.xlsx).", size=13, color=ft.colors.GREY_700),
                ft.Divider(),
                ft.ElevatedButton("Descargar Copia de Seguridad", icon=ft.icons.CLOUD_DOWNLOAD, bgcolor=ft.colors.BLUE_800, color=ft.colors.WHITE, on_click=self.generar_backup_completo)
            ], tight=True, spacing=15)
        )

        self.input_pass_actual = ft.TextField(label="Contraseña Actual", password=True, can_reveal_password=True, height=42, dense=True, text_size=13, col={"sm": 12, "md": 4})
        self.input_pass_nueva = ft.TextField(label="Nueva Contraseña", password=True, can_reveal_password=True, height=42, dense=True, text_size=13, col={"sm": 12, "md": 4})
        
        self.tab_perfil = ft.Container(
            padding=20,
            visible=False,
            content=ft.Column([
                ft.Text("Cambiar mi contraseña", weight=ft.FontWeight.BOLD, size=16),
                ft.ResponsiveRow([self.input_pass_actual, self.input_pass_nueva]),
                ft.ElevatedButton("Actualizar Seguridad", bgcolor=ft.colors.BLUE_800, color=ft.colors.WHITE, on_click=self.cambiar_password_personal)
            ], spacing=15)
        )

        self.tabs_config = ft.Tabs(
            selected_index=0,
            animation_duration=200,
            tabs=[
                ft.Tab(text="Datos del Negocio", icon=ft.icons.STORE),
                ft.Tab(text="Gestión de Usuarios", icon=ft.icons.PEOPLE),
                ft.Tab(text="Copia de Seguridad", icon=ft.icons.BACKUP),
                ft.Tab(text="Mi Perfil", icon=ft.icons.LOCK_PERSON)
            ],
            on_change=self.cambiar_pestana_config
        )

        self.content = ft.Column([
            ft.Text("Configuración General", size=24, weight=ft.FontWeight.BOLD),
            self.tabs_config,
            self.tab_negocio,
            self.tab_usuarios,
            self.tab_backup,
            self.tab_perfil
        ], spacing=15)
        
    def iniciar(self):
        self.cargar_datos_negocio()
        self.cargar_usuarios()
        self.page.update()