import customtkinter as ctk
import mysql.connector
from tkinter import messagebox
import hashlib
from tkinter import ttk
import tkinter as tk

# Configuración visual de CustomTkinter
ctk.set_appearance_mode("Dark")  # Puedes cambiar a "Light" o "System"
ctk.set_default_color_theme("blue")

def conectar_db():
    return mysql.connector.connect(
        host='localhost',
        database='sistema_inventario',
        user='root',
        password='Cr1sth14n', # Cambia esto por tu contraseña
        port=3306
    )

def crear_usuario_admin_por_defecto():
    """Crea un usuario administrador la primera vez que se ejecuta el sistema"""
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE usuario = 'admin'")
        if not cursor.fetchone():
            # Contraseña por defecto: 1234 (encriptada por seguridad)
            hash_pw = hashlib.sha256(b"1234").hexdigest()
            cursor.execute("""
                INSERT INTO usuarios (nombre_completo, usuario, password_hash, rol) 
                VALUES ('Administrador General', 'admin', %s, 'Administrador')
            """, (hash_pw,))
            conn.commit()
            print("Usuario administrador creado con éxito.")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error comprobando usuarios: {e}")

class AplicacionPrincipal(ctk.CTk):
    def __init__(self, nombre_usuario, rol_usuario):
        super().__init__()
        self.title("Sistema de Punto de Venta e Inventario")
        self.geometry("1100x650")
        
        # Configurar la cuadrícula principal
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # --- MENÚ LATERAL (SIDEBAR) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Chocolatito", font=ctk.CTkFont(size=24, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20))
        
        self.lbl_usuario = ctk.CTkLabel(self.sidebar_frame, text=f"👤 {nombre_usuario}\n({rol_usuario})", font=ctk.CTkFont(size=14))
        self.lbl_usuario.grid(row=1, column=0, padx=20, pady=(0, 30))
        
        self.btn_pos = ctk.CTkButton(self.sidebar_frame, text="🛒 Punto de Venta", command=self.mostrar_pos)
        self.btn_pos.grid(row=2, column=0, padx=20, pady=10)
        
        self.btn_dashboard = ctk.CTkButton(self.sidebar_frame, text="📊 Dashboard", command=self.mostrar_dashboard)
        self.btn_dashboard.grid(row=3, column=0, padx=20, pady=10)

        self.btn_salir = ctk.CTkButton(self.sidebar_frame, text="Salir", fg_color="red", hover_color="darkred", command=self.destroy)
        self.btn_salir.grid(row=6, column=0, padx=20, pady=(150, 10))
        
        # --- ÁREA PRINCIPAL ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=15)
        self.main_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        
        # Iniciar mostrando el POS por defecto
        self.mostrar_pos()

    def limpiar_main_frame(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def mostrar_pos(self):
        self.limpiar_main_frame()
        
        # Título
        ctk.CTkLabel(self.main_frame, text="🛒 Registrar Nueva Venta", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(10, 5))
        
        # 1. Marco para datos del cliente (Incluye Dirección predeterminada)
        frame_cliente = ctk.CTkFrame(self.main_frame)
        frame_cliente.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(frame_cliente, text="DNI:").grid(row=0, column=0, padx=5, pady=5)
        self.entry_dni = ctk.CTkEntry(frame_cliente, placeholder_text="00000000", width=100)
        self.entry_dni.grid(row=0, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(frame_cliente, text="Cliente:").grid(row=0, column=2, padx=5, pady=5)
        self.entry_cliente = ctk.CTkEntry(frame_cliente, placeholder_text="Varios", width=180)
        self.entry_cliente.grid(row=0, column=3, padx=5, pady=5)

        ctk.CTkLabel(frame_cliente, text="Dirección:").grid(row=0, column=4, padx=5, pady=5)
        self.entry_direccion = ctk.CTkEntry(frame_cliente, width=180)
        self.entry_direccion.insert(0, "Tacna") # Campo predeterminado solicitado
        self.entry_direccion.grid(row=0, column=5, padx=5, pady=5)
        
        # 2 y 3. Búsqueda, Switch (Unidad/Caja) y Precio Manual (Descuento)
        frame_producto = ctk.CTkFrame(self.main_frame)
        frame_producto.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(frame_producto, text="Buscar:").grid(row=0, column=0, padx=5, pady=5)
        self.entry_buscar = ctk.CTkEntry(frame_producto, width=220, placeholder_text="Producto...")
        self.entry_buscar.grid(row=0, column=1, padx=5, pady=5)
        
        # Switch interactivo
        self.var_tipo_venta = ctk.StringVar(value="Unidad")
        self.switch_tipo = ctk.CTkSwitch(frame_producto, text="Vender por Caja ($)", variable=self.var_tipo_venta, onvalue="Caja", offvalue="Unidad")
        self.switch_tipo.grid(row=0, column=2, padx=15, pady=5)

        # Descuento manual
        ctk.CTkLabel(frame_producto, text="Precio modificado:").grid(row=0, column=3, padx=5, pady=5)
        self.entry_precio_manual = ctk.CTkEntry(frame_producto, width=90, placeholder_text="Opcional")
        self.entry_precio_manual.grid(row=0, column=4, padx=5, pady=5)

        self.btn_buscar = ctk.CTkButton(frame_producto, text="🔍 Agregar", width=80)
        self.btn_buscar.grid(row=0, column=5, padx=5, pady=5)
        
        # Lista flotante para el autocompletado (Se oculta al inicio)
        self.lista_autocompletar = tk.Listbox(self.main_frame, height=5, font=("Arial", 11))
        
        # 4. Tabla del carrito con nuevas columnas
        frame_tabla = ctk.CTkFrame(self.main_frame)
        frame_tabla.pack(fill="both", expand=True, padx=20, pady=5)
        
        columnas = ("id", "producto", "presentacion", "tipo", "cantidad", "precio", "sub_pen", "sub_usd")
        self.tabla_carrito = ttk.Treeview(frame_tabla, columns=columnas, show="headings", height=8)
        self.tabla_carrito.heading("id", text="ID")
        self.tabla_carrito.heading("producto", text="Descripción")
        self.tabla_carrito.heading("presentacion", text="Present.")
        self.tabla_carrito.heading("tipo", text="Tipo")
        self.tabla_carrito.heading("cantidad", text="Cant.")
        self.tabla_carrito.heading("precio", text="Precio U.")
        self.tabla_carrito.heading("sub_pen", text="Sub (S/)")
        self.tabla_carrito.heading("sub_usd", text="Sub ($)")
        
        self.tabla_carrito.column("id", width=40)
        self.tabla_carrito.column("producto", width=220)
        self.tabla_carrito.column("presentacion", width=80)
        self.tabla_carrito.column("tipo", width=70)
        self.tabla_carrito.column("cantidad", width=60, anchor="center")
        self.tabla_carrito.column("precio", width=80, anchor="e")
        self.tabla_carrito.column("sub_pen", width=90, anchor="e")
        self.tabla_carrito.column("sub_usd", width=90, anchor="e")
        self.tabla_carrito.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 5. Doble Totalizador
        frame_total = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        frame_total.pack(fill="x", padx=20, pady=5)
        
        self.lbl_total_pen = ctk.CTkLabel(frame_total, text="Total: S/ 0.00", font=ctk.CTkFont(size=22, weight="bold"), text_color="#2FA572")
        self.lbl_total_pen.pack(side="left", padx=10)

        self.lbl_total_usd = ctk.CTkLabel(frame_total, text="Total: $ 0.00", font=ctk.CTkFont(size=22, weight="bold"), text_color="#3498db")
        self.lbl_total_usd.pack(side="left", padx=20)

        self.btn_eliminar = ctk.CTkButton(frame_total, text="🗑️ Eliminar Selección", font=ctk.CTkFont(weight="bold"), fg_color="#E74C3C", hover_color="#C0392B", height=40, command=self.eliminar_del_carrito)
        self.btn_eliminar.pack(side="right", padx=10)
        
        self.btn_generar_venta = ctk.CTkButton(frame_total, text="📄 Generar Venta", font=ctk.CTkFont(weight="bold"), fg_color="#2FA572", hover_color="#238258", height=40)
        self.btn_generar_venta.pack(side="right", padx=10)
        
        # --- ESTAS 4 LÍNEAS ACTIVAN LA BÚSQUEDA ---
        self.btn_buscar.configure(command=self.buscar_y_agregar)
        self.entry_buscar.bind("<Return>", lambda e: self.buscar_y_agregar())
        self.entry_buscar.bind("<KeyRelease>", self.autocompletar_busqueda)
        self.lista_autocompletar.bind("<<ListboxSelect>>", self.seleccionar_autocompletado)

    def buscar_y_agregar(self):
        busqueda = self.entry_buscar.get().strip()
        if not busqueda:
            return
            
        tipo_venta = self.var_tipo_venta.get() # "Unidad" o "Caja"
        precio_manual = self.entry_precio_manual.get().strip()
        
        try:
            conn = conectar_db()
            cursor = conn.cursor()
            # EXTRAEMOS AMBOS PRECIOS DE CAJA (USD y PEN)
            query = "SELECT id_producto, nombre, presentacion, precio, precio_caja_usd, precio_caja_pen, stock FROM productos WHERE id_producto = %s OR nombre = %s LIMIT 1"
            id_prod = busqueda if busqueda.isdigit() else 0
            cursor.execute(query, (id_prod, busqueda))
            producto = cursor.fetchone()
            
            if producto:
                if producto[6] <= 0: # El stock ahora es el dato número 6
                    messagebox.showerror("Sin Stock", f"El producto '{producto[1]}' se quedó sin stock.")
                else:
                    self.agregar_al_carrito(producto, tipo_venta, precio_manual)
            else:
                messagebox.showinfo("No encontrado", "No se encontró el producto exacto.")
            
            cursor.close()
            conn.close()
        except Exception as e:
            messagebox.showerror("Error", f"Fallo al buscar: {e}")

    def agregar_al_carrito(self, producto, tipo_venta, precio_manual):
        id_prod, nombre, presentacion, precio_unitario, precio_caja_usd, precio_caja_pen, stock = producto
        
        # 1. Validar Moneda y Precio Base Automáticamente
        if tipo_venta == "Unidad":
            precio_base = precio_unitario
            moneda = "PEN"
        else: # Si el switch está en "Caja"
            if precio_caja_usd > 0:
                precio_base = precio_caja_usd
                moneda = "USD"
            elif precio_caja_pen > 0:
                precio_base = precio_caja_pen
                moneda = "PEN"
            else:
                messagebox.showwarning("Aviso", f"El producto '{nombre}' no tiene precio por caja registrado.")
                return
            
        # 2. Validar Descuento Manual
        if precio_manual:
            try:
                precio_final = float(precio_manual)
            except ValueError:
                messagebox.showerror("Error", "El precio modificado debe ser un número válido.")
                return
        else:
            precio_final = float(precio_base)
            
        # 3. Lógica de Subtotales
        sub_pen = precio_final * 1 if moneda == "PEN" else 0.00
        sub_usd = precio_final * 1 if moneda == "USD" else 0.00
        
        # 4. Agrupar si ya existe el producto CON EL MISMO TIPO de venta
        for item in self.tabla_carrito.get_children():
            valores = self.tabla_carrito.item(item, 'values')
            if int(valores[0]) == id_prod and valores[3] == tipo_venta:
                nueva_cantidad = int(valores[4]) + 1
                if nueva_cantidad > stock:
                    messagebox.showwarning("Stock Insuficiente", f"Solo tienes {stock} unidades.")
                    return
                    
                nuevo_sub_pen = float(valores[6]) + (precio_final if moneda == "PEN" else 0.00)
                nuevo_sub_usd = float(valores[7]) + (precio_final if moneda == "USD" else 0.00)
                
                self.tabla_carrito.item(item, values=(id_prod, nombre, presentacion, tipo_venta, nueva_cantidad, f"{precio_final:.2f}", f"{nuevo_sub_pen:.2f}", f"{nuevo_sub_usd:.2f}"))
                self.actualizar_total()
                self.limpiar_busqueda()
                return
        
        # 5. Insertar nueva fila
        self.tabla_carrito.insert("", "end", values=(id_prod, nombre, presentacion, tipo_venta, 1, f"{precio_final:.2f}", f"{sub_pen:.2f}", f"{sub_usd:.2f}"))
        self.actualizar_total()
        self.limpiar_busqueda()

    def limpiar_busqueda(self):
        self.entry_buscar.delete(0, 'end')
        self.entry_precio_manual.delete(0, 'end')
        self.lista_autocompletar.place_forget() 

    def actualizar_total(self):
        total_pen = 0.0
        total_usd = 0.0
        for item in self.tabla_carrito.get_children():
            valores = self.tabla_carrito.item(item, 'values')
            total_pen += float(valores[6])
            total_usd += float(valores[7])
            
        self.lbl_total_pen.configure(text=f"Total: S/ {total_pen:.2f}")
        self.lbl_total_usd.configure(text=f"Total: $ {total_usd:.2f}")

    def eliminar_del_carrito(self):
        seleccionados = self.tabla_carrito.selection() # Obtiene lo que el usuario marcó con el clic
        if not seleccionados:
            messagebox.showwarning("Aviso", "Selecciona al menos un producto de la tabla para eliminar.")
            return
        
        for item in seleccionados:
            self.tabla_carrito.delete(item)
            
        self.actualizar_total() # Recalcula la suma automáticamente al borrar

    def autocompletar_busqueda(self, event):
        # Ignorar flechas de navegación y Enter
        if event.keysym in ('Up', 'Down', 'Return'): return
            
        busqueda = self.entry_buscar.get().strip()
        self.lista_autocompletar.delete(0, tk.END)
        
        if len(busqueda) < 2:
            self.lista_autocompletar.place_forget()
            return
            
        try:
            conn = conectar_db()
            cursor = conn.cursor()
            # Aumentamos el límite de 5 a 25 resultados posibles
            cursor.execute("SELECT nombre FROM productos WHERE nombre LIKE %s LIMIT 25", (f"%{busqueda}%",))
            resultados = cursor.fetchall()
            
            if resultados:
                for fila in resultados:
                    self.lista_autocompletar.insert(tk.END, fila[0])
                
                # Altura dinámica: crece hasta 12 filas como máximo. Si hay más, activa un scroll interno.
                altura_dinamica = min(len(resultados), 12)
                self.lista_autocompletar.configure(height=altura_dinamica)
                
                # Posicionamiento exacto
                x = self.entry_buscar.winfo_rootx() - self.main_frame.winfo_rootx()
                y = self.entry_buscar.winfo_rooty() - self.main_frame.winfo_rooty() + 35
                
                # Ensanchamos la caja a 300 píxeles para nombres largos
                self.lista_autocompletar.place(x=x, y=y, width=300) 
            else:
                self.lista_autocompletar.place_forget()
                
            cursor.close()
            conn.close()
        except Exception:
            pass
            
    def seleccionar_autocompletado(self, event):
        if not self.lista_autocompletar.curselection(): return
        seleccion = self.lista_autocompletar.get(self.lista_autocompletar.curselection())
        self.entry_buscar.delete(0, 'end')
        self.entry_buscar.insert(0, seleccion)
        self.lista_autocompletar.place_forget() 

    def mostrar_dashboard(self):
        self.limpiar_main_frame()
        titulo = ctk.CTkLabel(self.main_frame, text="Dashboard e Inventario", font=ctk.CTkFont(size=28, weight="bold"))
        titulo.pack(pady=40)
        info = ctk.CTkLabel(self.main_frame, text="Aquí colocaremos los gráficos de barras y pastel de rotación.")
        info.pack()

class VentanaLogin(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Inicio de Sesión")
        self.geometry("400x450")
        self.resizable(False, False)
        
        # Centrar elementos
        self.frame_login = ctk.CTkFrame(self, corner_radius=15)
        self.frame_login.pack(pady=40, padx=40, fill="both", expand=True)
        
        self.label_titulo = ctk.CTkLabel(self.frame_login, text="Bienvenido", font=ctk.CTkFont(size=28, weight="bold"))
        self.label_titulo.pack(pady=(40, 30))
        
        self.entry_usuario = ctk.CTkEntry(self.frame_login, placeholder_text="Usuario", width=220)
        self.entry_usuario.pack(pady=10)
        
        self.entry_password = ctk.CTkEntry(self.frame_login, placeholder_text="Contraseña", show="*", width=220)
        self.entry_password.pack(pady=10)
        
        self.btn_ingresar = ctk.CTkButton(self.frame_login, text="Ingresar", width=220, command=self.verificar_login)
        self.btn_ingresar.pack(pady=30)

    def verificar_login(self):
        usuario_ingresado = self.entry_usuario.get()
        password_ingresado = self.entry_password.get()
        hash_pw = hashlib.sha256(password_ingresado.encode()).hexdigest()
        
        try:
            conn = conectar_db()
            cursor = conn.cursor()
            cursor.execute("SELECT nombre_completo, rol FROM usuarios WHERE usuario = %s AND password_hash = %s", 
                           (usuario_ingresado, hash_pw))
            resultado = cursor.fetchone()
            
            if resultado:
                nombre = resultado[0]
                rol = resultado[1]
                self.destroy() # Cierra el login
                app = AplicacionPrincipal(nombre, rol) # Abre el menú principal
                app.mainloop()
            else:
                messagebox.showerror("Error", "Usuario o contraseña incorrectos")
                
            cursor.close()
            conn.close()
        except Exception as e:
            messagebox.showerror("Error de Conexión", f"No se pudo conectar a la BD: {e}")

if __name__ == "__main__":
    crear_usuario_admin_por_defecto()
    app_login = VentanaLogin()
    app_login.mainloop()