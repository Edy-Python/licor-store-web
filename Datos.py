import tkinter as tk
from tkinter import ttk, messagebox
import csv
import os

class SistemaRegistroDatos:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Registro y Búsqueda de Datos")
        self.root.geometry("920x550")
        
        # Color de fondo principal (Verde Bosque Oscuro)
        self.color_fondo_principal = "#127e36"
        self.root.configure(bg=self.color_fondo_principal) 

        # Base de datos en memoria
        self.datos_registrados = []

        # Configuración de estilos para la paleta Verde
        self.estilos = ttk.Style()
        self.estilos.theme_use("clam")
        
        # Color verde claro para los paneles internos
        color_paneles = "#adf7b2" 
        
        self.estilos.configure("TFrame", background=color_paneles)
        self.estilos.configure("TLabel", background=color_paneles, font=("Segoe UI", 10), foreground="#000000")
        
        # Botones en tono verde esmeralda
        self.estilos.configure("TButton", font=("Segoe UI", 10, "bold"), 
                               background="#27ae60", foreground="white", focuscolor="none")
        self.estilos.map("TButton", background=[("active", "#2ecc71")])
        
        # Estilo de la tabla
        self.estilos.configure("Treeview", font=("Segoe UI", 9), rowheight=25, 
                               background="white", fieldbackground="white")
        # Cabecera de la tabla en verde oscuro
        self.estilos.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), 
                               background="#196f3d", foreground="white")

        self.construir_interfaz()

    def construir_interfaz(self):
        # PANEL SUPERIOR: TÍTULO DE LA APLICACIÓN
        panel_titulo = tk.Frame(self.root, bg="#143621", pady=15)
        panel_titulo.pack(side=tk.TOP, fill=tk.X)
        lbl_titulo = tk.Label(panel_titulo, text="Gestor de Datos", 
                              bg="#143621", fg="white", font=("Segoe UI", 18, "bold"))
        lbl_titulo.pack()

        # Contenedor Principal
        panel_principal = tk.Frame(self.root, bg=self.color_fondo_principal, padx=15, pady=15)
        panel_principal.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # PANEL IZQUIERDO: FORMULARIO DE REGISTRO
        panel_izquierdo = ttk.Frame(panel_principal, padding="20")
        panel_izquierdo.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 15))

        ttk.Label(panel_izquierdo, text="Formulario de Registro", 
                  font=("Segoe UI", 12, "bold"), foreground="#196f3d").grid(row=0, column=0, columnspan=2, pady=(0, 20))

        ttk.Label(panel_izquierdo, text="Código ID:").grid(row=1, column=0, sticky="w", pady=8)
        self.entry_id = ttk.Entry(panel_izquierdo, width=28)
        self.entry_id.grid(row=1, column=1, pady=8)

        ttk.Label(panel_izquierdo, text="Nombres y Apellidos:").grid(row=2, column=0, sticky="w", pady=8)
        self.entry_nombre = ttk.Entry(panel_izquierdo, width=28)
        self.entry_nombre.grid(row=2, column=1, pady=8)

        ttk.Label(panel_izquierdo, text="Edad:").grid(row=3, column=0, sticky="w", pady=8)
        self.entry_edad = ttk.Entry(panel_izquierdo, width=28)
        self.entry_edad.grid(row=3, column=1, pady=8)

        ttk.Label(panel_izquierdo, text="Área/Departamento:").grid(row=4, column=0, sticky="w", pady=8)
        self.entry_area = ttk.Entry(panel_izquierdo, width=28)
        self.entry_area.grid(row=4, column=1, pady=8)

        btn_guardar = ttk.Button(panel_izquierdo, text="Registrar Datos", command=self.registrar_dato)
        btn_guardar.grid(row=5, column=0, columnspan=2, pady=30, ipadx=10, ipady=5)

        # PANEL DERECHO: BÚSQUEDA Y TABLA DE DISTRIBUCIÓN
        panel_derecho = ttk.Frame(panel_principal, padding="15")
        panel_derecho.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Sub-panel superior para botones y búsqueda
        panel_busqueda = ttk.Frame(panel_derecho)
        panel_busqueda.pack(side=tk.TOP, fill=tk.X, pady=(0, 15))

        ttk.Label(panel_busqueda, text="Buscar:").pack(side=tk.LEFT, padx=(0, 5))
        self.entry_busqueda = ttk.Entry(panel_busqueda, width=25)
        self.entry_busqueda.pack(side=tk.LEFT, padx=(0, 10))
        
        btn_buscar = ttk.Button(panel_busqueda, text="Buscar", command=self.buscar_dato)
        btn_buscar.pack(side=tk.LEFT, padx=5)
        
        btn_restablecer = ttk.Button(panel_busqueda, text="Mostrar Todos", command=self.actualizar_tabla)
        btn_restablecer.pack(side=tk.LEFT, padx=5)

        # Botón de exportación a Excel (Nuevo)
        btn_exportar = ttk.Button(panel_busqueda, text="Exportar a Excel", command=self.exportar_excel)
        btn_exportar.pack(side=tk.RIGHT)

        # Configuración de la Tabla (Treeview)
        columnas = ("id", "nombre", "edad", "area")
        self.tabla = ttk.Treeview(panel_derecho, columns=columnas, show="headings")
        
        self.tabla.heading("id", text="Código ID")
        self.tabla.heading("nombre", text="Nombres y Apellidos")
        self.tabla.heading("edad", text="Edad")
        self.tabla.heading("area", text="Área/Depto")

        self.tabla.column("id", width=80, anchor=tk.CENTER)
        self.tabla.column("nombre", width=180, anchor=tk.W)
        self.tabla.column("edad", width=60, anchor=tk.CENTER)
        self.tabla.column("area", width=140, anchor=tk.W)

        scroll_y = ttk.Scrollbar(panel_derecho, orient=tk.VERTICAL, command=self.tabla.yview)
        self.tabla.configure(yscroll=scroll_y.set)
        
        self.tabla.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    # MÉTODOS DE LÓGICA Y PROCESAMIENTO
    def registrar_dato(self):
        id_val = self.entry_id.get().strip()
        nombre = self.entry_nombre.get().strip()
        edad = self.entry_edad.get().strip()
        area = self.entry_area.get().strip()

        if not (id_val and nombre and edad and area):
            messagebox.showwarning("Campos Incompletos", "Por favor, complete todos los campos del formulario.")
            return

        if not edad.isdigit():
            messagebox.showerror("Error de Formato", "El campo 'Edad' debe contener únicamente números enteros.")
            return

        nuevo_registro = {"id": id_val, "nombre": nombre, "edad": edad, "area": area}
        self.datos_registrados.append(nuevo_registro)
        self.limpiar_formulario()
        self.actualizar_tabla()
        messagebox.showinfo("Registro Exitoso", f"Los datos de '{nombre}' han sido registrados.")

    def limpiar_formulario(self):
        self.entry_id.delete(0, tk.END)
        self.entry_nombre.delete(0, tk.END)
        self.entry_edad.delete(0, tk.END)
        self.entry_area.delete(0, tk.END)
        self.entry_id.focus() 

    def actualizar_tabla(self, datos_filtrados=None):
        for item in self.tabla.get_children():
            self.tabla.delete(item)

        lista_a_distribuir = datos_filtrados if datos_filtrados is not None else self.datos_registrados

        for d in lista_a_distribuir:
            self.tabla.insert("", tk.END, values=(d["id"], d["nombre"], d["edad"], d["area"]))

    def buscar_dato(self):
        termino = self.entry_busqueda.get().strip().lower()
        if not termino:
            messagebox.showinfo("Búsqueda Vacía", "Ingrese un nombre o fragmento para iniciar la búsqueda.")
            return

        resultados = [d for d in self.datos_registrados if termino in d["nombre"].lower()]
        self.actualizar_tabla(resultados)
        
        if not resultados:
            messagebox.showinfo("Sin Coincidencias", f"No se encontró ningún registro que contenga: '{termino}'")

    # MÉTODO NUEVO: EXPORTACIÓN A EXCEL
    def exportar_excel(self):
        """Exporta los datos en memoria a un archivo CSV compatible con Excel."""
        if not self.datos_registrados:
            messagebox.showwarning("Tabla Vacía", "No hay datos registrados para exportar.")
            return
            
        nombre_archivo = "Registro_Datos_Exportados.csv"
        
        try:
            # Se utiliza utf-8-sig para que Excel reconozca correctamente tildes y ñ
            with open(nombre_archivo, mode='w', newline='', encoding='utf-8-sig') as archivo_excel:
                escritor = csv.writer(archivo_excel, delimiter=';') # El delimitador ';' es estándar para Excel en español
                
                # Escribir cabeceras
                escritor.writerow(["Código ID", "Nombres y Apellidos", "Edad", "Área/Departamento"])
                
                # Escribir los datos
                for d in self.datos_registrados:
                    escritor.writerow([d["id"], d["Nombres y Apellidos"], d["edad"], d["area"]])
                    
            ruta_absoluta = os.path.abspath(nombre_archivo)
            messagebox.showinfo("Exportación Exitosa", f"Los datos han sido exportados correctamente a:\n\n{ruta_absoluta}\n\nPuedes abrir este archivo directamente con Excel.")
            
        except Exception as e:
            messagebox.showerror("Error de Exportación", f"Ocurrió un problema al guardar el archivo:\n{e}")

# ---------------------------------------------------------
# PUNTO DE ENTRADA DE LA APLICACIÓN
# ---------------------------------------------------------
if __name__ == "__main__":
    ventana_principal = tk.Tk()
    app = SistemaRegistroDatos(ventana_principal)
    ventana_principal.mainloop()