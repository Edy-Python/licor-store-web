import os
import textwrap
from fpdf import FPDF
from num2words import num2words
import flet as ft
from database import obtener_cursor

def _obtener_config_empresa():
    """Retorna los datos de configuración de la empresa desde la base de datos."""
    try:
        with obtener_cursor() as cursor:
            cursor.execute("SELECT nombre_negocio, ruc, direccion, telefono, mensaje_ticket, COALESCE(referencia, '') FROM configuracion LIMIT 1")
            conf = cursor.fetchone()
            if conf:
                return {
                    "nombre": conf[0] or "",
                    "ruc": conf[1] or "",
                    "direccion": conf[2] or "",
                    "telefono": conf[3] or "",
                    "mensaje": conf[4] or "¡Gracias por su compra!",
                    "referencia": conf[5] or ""
                }
    except Exception as ex:
        print(f"Error al obtener configuración de empresa: {ex}")
    return {
        "nombre": "",
        "ruc": "",
        "direccion": "",
        "telefono": "",
        "mensaje": "¡Gracias por su compra!",
        "referencia": ""
    }

def _dibujar_cabecera_pdf(pdf: FPDF, conf: dict, logo_x: float = 7, logo_w: float = 66, espacio_post: float = 3):
    """Dibuja de forma estandarizada el logo y la cabecera comercial de la empresa."""
    logo_path = os.path.join(os.getcwd(), "LogoLK.png")
    if not os.path.exists(logo_path):
        logo_path = os.path.join(os.getcwd(), "assets", "LogoLK.png")
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=logo_x, y=5, w=logo_w)
        pdf.ln(21)

    nom = conf.get("nombre", "").strip()
    if nom:
        pdf.set_font("PrimaSans", 'B', 13)
        pdf.multi_cell(w=70, h=5, txt=nom.upper(), align='C')

    pdf.set_font("PrimaSans", size=8)
    ruc = conf.get("ruc", "").strip()
    if ruc:
        pdf.cell(70, 4, txt=f"RUC: {ruc}", ln=True, align='C')

    dir_emp = conf.get("direccion", "").strip()
    if dir_emp:
        for linea_dir in textwrap.wrap(dir_emp, width=55):
            pdf.cell(70, 4, txt=linea_dir, ln=True, align='C')

    ref_emp = conf.get("referencia", "").strip()
    if ref_emp:
        for linea_ref in textwrap.wrap(ref_emp, width=55):
            pdf.cell(70, 4, txt=linea_ref, ln=True, align='C')

    tel = conf.get("telefono", "").strip()
    if tel:
        pdf.cell(70, 4, txt=f"Cel: {tel}", ln=True, align='C')

    pdf.ln(espacio_post)

def exportar_ticket_pdf(page: ft.Page, id_venta, codigo_ticket):
    page.open(ft.SnackBar(ft.Text(f"⏳ Generando PDF de {codigo_ticket}...", color=ft.colors.BLACK, weight=ft.FontWeight.BOLD), bgcolor=ft.colors.YELLOW))

    try:
        conf_empresa = _obtener_config_empresa()
        c_msg_emp = conf_empresa["mensaje"]

        with obtener_cursor() as cursor:
            cursor.execute("SELECT fecha_emision, hora_emision, vendedor, cliente_nombre, cliente_dni, cliente_direccion, total_pen, total_usd, metodo_pago, monto_efectivo, monto_yape, monto_plin, monto_tarjeta, vuelto, condicion_pago FROM ventas WHERE id_venta = %s", (id_venta,))
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

        f_emision, h_emision, vendedor, c_nombre, c_dni, c_dir, t_pen, t_usd, m_pago, m_efec, m_yape, m_transf, m_tarj, vuelto, *resto = cabecera
        cond_pago = resto[0] if resto and resto[0] else "Contado"

        lineas_totales_productos = sum(max(1, len(textwrap.wrap(str(d[0]), width=18))) for d in detalles)
        alto_total = 165 + (len(detalles) * 3) + (lineas_totales_productos * 5) 

        pdf = FPDF(orientation='P', unit='mm', format=(80, alto_total)) 
        pdf.set_margins(5, 5, 5) 
        pdf.set_auto_page_break(auto=False, margin=0) 

        # 1. Integración de la tipografía PrimaSans (Regular y Bold)
        ruta_regular = os.path.join(os.getcwd(), "assets", "prima-sans.otf")
        ruta_bold = os.path.join(os.getcwd(), "assets", "prima-sans-bold.otf")
        pdf.add_font("PrimaSans", style="", fname=ruta_regular)
        pdf.add_font("PrimaSans", style="B", fname=ruta_bold)
        pdf.add_font("PrimaSans", style="I", fname=ruta_regular)

        pdf.add_page()
        
        # Requisito 1: Logo centrado más grande (w=66, x=7)
        _dibujar_cabecera_pdf(pdf, conf_empresa, logo_x=7, logo_w=66, espacio_post=3)

        # 2. Equilibrio del Título y Número de Nota de Venta (armonía a 11pt)
        pdf.set_font("PrimaSans", 'B', 11)
        pdf.cell(70, 4.5, txt="NOTA DE VENTA", ln=True, align='C')
        pdf.set_font("PrimaSans", 'B', 11)
        pdf.cell(70, 5.5, txt=codigo_ticket, ln=True, align='C')
        pdf.ln(2.5)
        
        # Requisito 2: Estandarización de fuente a 8pt (regular)
        def dibujar_fila_cliente(etiqueta, valor):
            pdf.set_font("PrimaSans", size=8)
            pdf.cell(18, 4.2, txt=etiqueta, align='L')
            pdf.set_font("PrimaSans", size=8)
            pdf.cell(52, 4.2, txt=str(valor), ln=True, align='L')

        dibujar_fila_cliente("F. Emisión:", f_emision)
        dibujar_fila_cliente("H. Emisión:", h_emision)
        dibujar_fila_cliente("Cliente:", c_nombre if c_nombre else 'VARIOS')
        dibujar_fila_cliente("DNI:", c_dni if c_dni else '00000000')
        dibujar_fila_cliente("Dirección:", c_dir[:40] if c_dir else 'Tacna')
        pdf.ln(3)
        
        # 1. Punto de inicio total de la tabla (Cabecera + Cuerpo)
        y_inicio_tabla = pdf.get_y()
        alto_cabecera = 6.5
        alto_celda = 4

        # 2. Imprimir Encabezados con border=0 y altura ampliada (6.5mm)
        pdf.set_font("PrimaSans", 'B', 7.5)
        pdf.set_xy(5, y_inicio_tabla)
        pdf.cell(7, alto_cabecera, txt="Cant", border=0, align='C')
        pdf.cell(8, alto_cabecera, txt="Unid", border=0, align='C')
        pdf.cell(25, alto_cabecera, txt="Descripción", border=0, align='C')
        pdf.cell(10, alto_cabecera, txt="P.U.", border=0, align='C')
        pdf.cell(10, alto_cabecera, txt="Sub S/", border=0, align='C')
        pdf.cell(10, alto_cabecera, txt="Sub $", border=0, ln=True, align='C')

        # 3. Imprimir Productos con border=0 (sin dibujar rectángulos ni líneas internas)
        pdf.set_y(y_inicio_tabla + alto_cabecera)
        for det in detalles:
            lineas = textwrap.wrap(str(det[0]), width=16) or [""]
            alto_fila = len(lineas) * alto_celda
            y_fila = pdf.get_y()

            pdf.set_font("PrimaSans", '', 7)

            pdf.set_xy(5, y_fila)
            pdf.cell(7, alto_celda, txt=str(det[1]), border=0, align='C')

            pdf.set_xy(12, y_fila)
            pdf.cell(8, alto_celda, txt=str(det[2][:3]).upper(), border=0, align='C')

            pdf.set_xy(45, y_fila)
            pdf.cell(10, alto_celda, txt=f"{det[3]:.2f}", border=0, align='C')

            pdf.set_xy(55, y_fila)
            pdf.cell(10, alto_celda, txt=f"{det[4]:.2f}", border=0, align='R')

            pdf.set_xy(65, y_fila)
            pdf.cell(10, alto_celda, txt=f"{det[5]:.2f}", border=0, align='R')

            for i, linea in enumerate(lineas):
                pdf.set_xy(20, y_fila + (i * alto_celda))
                pdf.cell(25, alto_celda, txt=linea, border=0, align='L')

            # Bajar el cursor al final de la fila actual
            pdf.set_y(y_fila + alto_fila)

        # 4. Punto de fin total de la tabla
        y_fin_tabla = pdf.get_y()

        # 5. Dibujar la Cuadrícula Maestra Unificada
        pdf.set_draw_color(0, 0, 0)
        pdf.rect(5, y_inicio_tabla, 70, y_fin_tabla - y_inicio_tabla)
        pdf.line(5, y_inicio_tabla + alto_cabecera, 75, y_inicio_tabla + alto_cabecera)

        pdf.line(12, y_inicio_tabla, 12, y_fin_tabla)
        pdf.line(20, y_inicio_tabla, 20, y_fin_tabla)
        pdf.line(45, y_inicio_tabla, 45, y_fin_tabla)
        pdf.line(55, y_inicio_tabla, 55, y_fin_tabla)
        pdf.line(65, y_inicio_tabla, 65, y_fin_tabla)

        pdf.ln(2)
        
        # Totales
        pdf.set_font("PrimaSans", 'B', 8)
        if t_pen > 0:
            pdf.cell(35, 5, txt="", align='L')
            pdf.cell(23, 5, txt="Total a pagar: S/", align='R')
            pdf.cell(12, 5, txt=f"{t_pen:.2f}", ln=True, align='R')
        if t_usd > 0:
            pdf.cell(35, 5, txt="", align='L')
            pdf.cell(23, 5, txt="Total a pagar: $", align='R')
            pdf.cell(12, 5, txt=f"{t_usd:.2f}", ln=True, align='R')
            
        pdf.ln(2)
        
        if t_pen > 0:
            entero = int(t_pen)
            centimos = int(round((t_pen - entero) * 100))
            texto_pen = num2words(entero, lang='es').capitalize()
            pdf.set_font("PrimaSans", size=8)
            pdf.write(4, "Son: ")
            pdf.set_font("PrimaSans", 'B', 8)
            pdf.write(4, f"{texto_pen} con {centimos:02d}/100 Soles\n")
        
        if t_usd > 0:
            entero_usd = int(t_usd)
            centimos_usd = int(round((t_usd - entero_usd) * 100))
            texto_usd = num2words(entero_usd, lang='es').capitalize()
            pdf.set_font("PrimaSans", size=8)
            pdf.write(4, "Son: ")
            pdf.set_font("PrimaSans", 'B', 8)
            pdf.write(4, f"{texto_usd} con {centimos_usd:02d}/100 Dólares Americanos\n")
        
        pdf.ln(2)
        
        # Datos de pago y cierre estandarizados a 8pt
        pdf.set_font("PrimaSans", 'B', 8)
        pdf.write(4.5, "Condición de Pago: ")
        pdf.set_font("PrimaSans", size=8)
        pdf.write(4.5, f"{str(cond_pago).capitalize()}\n")
        
        pdf.set_font("PrimaSans", 'B', 8)
        pdf.cell(70, 4.5, txt="Pagos:", ln=True, align='L')
        
        pdf.set_font("PrimaSans", size=8)
        if m_efec > 0: 
            pdf.cell(70, 4.2, txt=f"• Efectivo - S/ {m_efec:.2f}", ln=True, align='L')
        if m_yape > 0: 
            pdf.cell(70, 4.2, txt=f"• Yape - S/ {m_yape:.2f}", ln=True, align='L')
        if m_transf > 0: 
            pdf.cell(70, 4.2, txt=f"• Transferencia - S/ {m_transf:.2f}", ln=True, align='L')
        if m_tarj > 0: 
            pdf.cell(70, 4.2, txt=f"• Tarjeta - S/ {m_tarj:.2f}", ln=True, align='L')
        if t_usd > 0: 
            pdf.cell(70, 4.2, txt=f"• Dólares - $ {t_usd:.2f}", ln=True, align='L')

        pdf.set_font("PrimaSans", 'B', 8)
        pdf.write(4.5, "Vuelto: ")
        pdf.set_font("PrimaSans", size=8)
        pdf.write(4.5, f"S/ {vuelto:.2f}\n")

        pdf.set_font("PrimaSans", 'B', 8)
        pdf.write(4.5, "Vendedor: ")
        pdf.set_font("PrimaSans", size=8)
        pdf.write(4.5, f"{str(vendedor).upper()}\n")

        if c_msg_emp and str(c_msg_emp).strip():
            pdf.ln(4)
            pdf.set_font("PrimaSans", 'B', 8)
            pdf.cell(70, 4.5, txt=str(c_msg_emp).strip(), ln=True, align='C')

        dir_base = os.path.dirname(os.path.abspath(__file__))
        ruta_pdf = os.path.join(dir_base, "assets", f"{codigo_ticket}.pdf")
        os.makedirs(os.path.dirname(ruta_pdf), exist_ok=True)
        pdf.output(ruta_pdf)

        page.launch_url(f"/{codigo_ticket}.pdf", web_window_name="_blank") 
        page.open(ft.SnackBar(ft.Text("✅ ¡PDF generado! Se abrió en una pestaña nueva.", color=ft.colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.colors.GREEN, duration=6000))

    except Exception as e:
        print(f"Error PDF Térmico: {e}")
        page.open(ft.SnackBar(ft.Text(f"❌ Error al exportar: {e}", color=ft.colors.WHITE), bgcolor=ft.colors.RED))


def exportar_recibo_abono_pdf(page: ft.Page, id_pago):
    try:
        with obtener_cursor() as cursor:
            cursor.execute("""
                SELECT p.id_pago, p.id_venta, p.fecha, p.hora, p.monto, p.metodo_pago, p.usuario, p.observaciones,
                       v.codigo_ticket, v.cliente_nombre, v.cliente_dni, v.cliente_direccion, v.total_pen, v.vendedor
                FROM pagos_credito p
                JOIN ventas v ON p.id_venta = v.id_venta
                WHERE p.id_pago = %s
            """, (id_pago,))
            datos = cursor.fetchone()
            if not datos:
                page.open(ft.SnackBar(ft.Text("No se encontró el abono."), bgcolor=ft.colors.RED))
                return

            (p_id, v_id, p_fecha, p_hora, p_monto, p_metodo, p_usuario, p_obs,
             v_cod, v_cliente, v_dni, v_dir, v_total, v_vendedor) = datos
            p_monto = float(p_monto)
            v_total = float(v_total)

            cursor.execute("SELECT COALESCE(SUM(monto), 0) FROM pagos_credito WHERE id_venta = %s AND id_pago <= %s", (v_id, p_id))
            total_pagado_hasta_aqui = float(cursor.fetchone()[0])

            saldo_anterior = max(0.0, v_total - (total_pagado_hasta_aqui - p_monto))
            saldo_restante = max(0.0, v_total - total_pagado_hasta_aqui)

        conf_empresa = _obtener_config_empresa()
        c_msg_emp = conf_empresa["mensaje"]

        pdf = FPDF(orientation='P', unit='mm', format=(80, 175))
        pdf.set_margins(5, 5, 5)
        pdf.set_auto_page_break(auto=False, margin=0)

        # Integración de la tipografía PrimaSans (Regular y Bold)
        ruta_regular = os.path.join(os.getcwd(), "assets", "prima-sans.otf")
        ruta_bold = os.path.join(os.getcwd(), "assets", "prima-sans-bold.otf")
        pdf.add_font("PrimaSans", style="", fname=ruta_regular)
        pdf.add_font("PrimaSans", style="B", fname=ruta_bold)
        pdf.add_font("PrimaSans", style="I", fname=ruta_regular)

        pdf.add_page()

        _dibujar_cabecera_pdf(pdf, conf_empresa, logo_x=7, logo_w=66, espacio_post=2)

        pdf.set_font("PrimaSans", 'B', 10.5)
        pdf.cell(70, 5, txt="RECIBO DE ABONO / COBRANZA", ln=True, align='C')
        pdf.set_font("PrimaSans", 'B', 8.5)
        pdf.cell(70, 4.5, txt=f"N° RECIBO: ABON-{p_id:06d}", ln=True, align='C')
        pdf.ln(2)

        y_actual = pdf.get_y()
        pdf.set_draw_color(0, 0, 0)
        pdf.line(5, y_actual, 75, y_actual)
        pdf.ln(2)

        def fila_rec_info(etiqueta, valor):
            pdf.set_font("PrimaSans", 'B', 8)
            pdf.cell(24, 4.5, txt=etiqueta, align='L')
            pdf.set_font("PrimaSans", size=8)
            pdf.cell(46, 4.5, txt=str(valor), ln=True, align='L')

        fila_rec_info("Fecha / Hora:", f"{p_fecha} {p_hora}")
        fila_rec_info("Ticket Venta:", v_cod)
        fila_rec_info("Cliente:", v_cliente if v_cliente else 'VARIOS')
        fila_rec_info("DNI / RUC:", v_dni if v_dni else '00000000')
        fila_rec_info("Cajero/Usuario:", str(p_usuario).upper())
        pdf.ln(2)

        y_actual = pdf.get_y()
        pdf.set_draw_color(0, 0, 0)
        pdf.line(5, y_actual, 75, y_actual)
        pdf.ln(2)

        pdf.set_font("PrimaSans", 'B', 9.5)
        pdf.cell(40, 5, txt="MONTO ABONADO:", align='L')
        pdf.cell(30, 5, txt=f"S/ {p_monto:.2f}", ln=True, align='R')

        entero = int(p_monto)
        centimos = int(round((p_monto - entero) * 100))
        texto_pen = num2words(entero, lang='es').capitalize()
        pdf.set_font("PrimaSans", size=8)
        pdf.write(4, "Son: ")
        pdf.set_font("PrimaSans", 'B', 8)
        pdf.write(4, f"{texto_pen} con {centimos:02d}/100 Soles\n")

        pdf.ln(2)
        fila_rec_info("Método de Pago:", p_metodo)

        y_actual = pdf.get_y()
        pdf.set_draw_color(0, 0, 0)
        pdf.line(5, y_actual, 75, y_actual)
        pdf.ln(2)

        pdf.set_font("PrimaSans", 'B', 8.5)
        pdf.cell(70, 4.5, txt="ESTADO DE LA DEUDA:", ln=True, align='L')
        pdf.set_font("PrimaSans", size=8)
        pdf.cell(45, 4.5, txt="Total Venta Original:", align='L')
        pdf.cell(25, 4.5, txt=f"S/ {v_total:.2f}", ln=True, align='R')
        pdf.cell(45, 4.5, txt="Saldo Anterior:", align='L')
        pdf.cell(25, 4.5, txt=f"S/ {saldo_anterior:.2f}", ln=True, align='R')
        pdf.set_font("PrimaSans", 'B', 8)
        pdf.cell(45, 4.5, txt="(-) Abono Realizado:", align='L')
        pdf.cell(25, 4.5, txt=f"S/ {p_monto:.2f}", ln=True, align='R')
        pdf.set_font("PrimaSans", 'B', 8.5)
        pdf.cell(45, 5, txt="(=) SALDO RESTANTE:", align='L')
        pdf.cell(25, 5, txt=f"S/ {saldo_restante:.2f}", ln=True, align='R')

        if p_obs and str(p_obs).strip():
            pdf.ln(2)
            pdf.set_font("PrimaSans", 'I', 8)
            pdf.cell(70, 4, txt=f"Nota: {p_obs[:50]}", ln=True, align='L')

        pdf.ln(6)
        pdf.set_font("PrimaSans", size=8)
        pdf.cell(70, 4, txt="____________________________", ln=True, align='C')
        pdf.cell(70, 4, txt="Firma / Sello de Conformidad", ln=True, align='C')

        if c_msg_emp and str(c_msg_emp).strip():
            pdf.ln(3)
            pdf.set_font("PrimaSans", 'B', 8)
            pdf.cell(70, 4.5, txt=str(c_msg_emp).strip(), ln=True, align='C')

        dir_base = os.path.dirname(os.path.abspath(__file__))
        nom_arch = f"recibo_abono_{p_id}.pdf"
        ruta_pdf = os.path.join(dir_base, "assets", nom_arch)
        os.makedirs(os.path.dirname(ruta_pdf), exist_ok=True)
        pdf.output(ruta_pdf)

        page.launch_url(f"/{nom_arch}", web_window_name="_blank")
        page.open(ft.SnackBar(ft.Text("✅ Recibo de abono generado en PDF térmico.", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN, duration=4000))

    except Exception as ex:
        print(f"Error generando recibo abono: {ex}")
        page.open(ft.SnackBar(ft.Text(f"❌ Error al generar recibo: {ex}"), bgcolor=ft.colors.RED))


def exportar_cierre_turno_pdf(page: ft.Page, id_cierre):
    try:
        with obtener_cursor() as cursor:
            cursor.execute("""
                SELECT id_cierre, fecha, hora, usuario, monto_apertura, 
                       total_ventas_efectivo, total_ventas_yape, total_ventas_transferencia, total_ventas_tarjeta, total_ventas_dolares,
                       total_abonos_cobrados, total_gastos, efectivo_esperado, efectivo_real_conteo, diferencia, estado_cuadre, observaciones
                FROM cierres_caja WHERE id_cierre = %s
            """, (id_cierre,))
            row = cursor.fetchone()
            if not row:
                page.open(ft.SnackBar(ft.Text("No se encontró el registro de cierre."), bgcolor=ft.colors.RED))
                return

            (c_id, c_fecha, c_hora, c_usr, c_ape,
             c_vef, c_vyp, c_vtr, c_vta, c_vusd,
             c_abo, c_gas, c_esp, c_fis, c_dif, c_est, c_obs) = row

        conf_empresa = _obtener_config_empresa()
        c_msg_emp = conf_empresa["mensaje"]

        pdf = FPDF(orientation='P', unit='mm', format=(80, 210))
        pdf.set_margins(5, 5, 5)
        pdf.set_auto_page_break(auto=False, margin=0)

        # Integración de la tipografía PrimaSans (Regular y Bold)
        ruta_regular = os.path.join(os.getcwd(), "assets", "prima-sans.otf")
        ruta_bold = os.path.join(os.getcwd(), "assets", "prima-sans-bold.otf")
        pdf.add_font("PrimaSans", style="", fname=ruta_regular)
        pdf.add_font("PrimaSans", style="B", fname=ruta_bold)
        pdf.add_font("PrimaSans", style="I", fname=ruta_regular)

        pdf.add_page()

        _dibujar_cabecera_pdf(pdf, conf_empresa, logo_x=7, logo_w=66, espacio_post=2)

        pdf.set_font("PrimaSans", 'B', 10.5)
        pdf.cell(70, 5, txt="CIERRE Y ARQUEO DE CAJA", ln=True, align='C')
        pdf.set_font("PrimaSans", 'B', 8.5)
        pdf.cell(70, 4.5, txt=f"TURNO N°: CC-{c_id:05d}", ln=True, align='C')
        pdf.ln(2)

        y_actual = pdf.get_y()
        pdf.set_draw_color(0, 0, 0)
        pdf.line(5, y_actual, 75, y_actual)
        pdf.ln(2)

        def fila_cie_item(etiqueta, valor, negrita=False, tam=8):
            pdf.set_font("PrimaSans", 'B' if negrita else '', tam)
            pdf.cell(48, 4.5, txt=etiqueta, align='L')
            pdf.cell(22, 4.5, txt=str(valor), ln=True, align='R')

        pdf.set_font("PrimaSans", 'B', 8)
        pdf.cell(24, 4.5, txt="Fecha / Hora:", align='L')
        pdf.set_font("PrimaSans", size=8)
        pdf.cell(46, 4.5, txt=f"{c_fecha} {c_hora}", ln=True, align='L')
        pdf.set_font("PrimaSans", 'B', 8)
        pdf.cell(24, 4.5, txt="Responsable:", align='L')
        pdf.set_font("PrimaSans", size=8)
        pdf.cell(46, 4.5, txt=f"{str(c_usr).upper()}", ln=True, align='L')
        pdf.ln(2)

        y_actual = pdf.get_y()
        pdf.set_draw_color(0, 0, 0)
        pdf.line(5, y_actual, 75, y_actual)
        pdf.ln(2)

        pdf.set_font("PrimaSans", 'B', 8.5)
        pdf.cell(70, 4.5, txt="MOVIMIENTOS DE EFECTIVO (CAJA):", ln=True, align='L')
        fila_cie_item("(+) Base Inicial Apertura:", f"S/ {float(c_ape):.2f}")
        fila_cie_item("(+) Ventas en Efectivo:", f"S/ {float(c_vef):.2f}")
        fila_cie_item("(+) Cobranzas de Crédito:", f"S/ {float(c_abo):.2f}")
        fila_cie_item("(-) Salidas / Gastos del Día:", f"S/ {float(c_gas):.2f}")
        pdf.ln(1)

        y_actual = pdf.get_y()
        pdf.set_draw_color(0, 0, 0)
        pdf.line(5, y_actual, 75, y_actual)
        pdf.ln(2)

        fila_cie_item("(=) TOTAL ESPERADO EN CAJA:", f"S/ {float(c_esp):.2f}", negrita=True, tam=8.5)
        fila_cie_item("(=) EFECTIVO FÍSICO CONTADO:", f"S/ {float(c_fis):.2f}", negrita=True, tam=8.5)
        dif_sign = "+" if float(c_dif) > 0 else ""
        fila_cie_item(f"DIFERENCIA ({c_est}):", f"{dif_sign}S/ {float(c_dif):.2f}", negrita=True, tam=8.5)
        pdf.ln(2)

        y_actual = pdf.get_y()
        pdf.set_draw_color(0, 0, 0)
        pdf.line(5, y_actual, 75, y_actual)
        pdf.ln(2)

        pdf.set_font("PrimaSans", 'B', 8.5)
        pdf.cell(70, 4.5, txt="VENTAS EN OTROS MEDIOS (BANCOS):", ln=True, align='L')
        fila_cie_item("Yape:", f"S/ {float(c_vyp):.2f}")
        fila_cie_item("Transferencias:", f"S/ {float(c_vtr):.2f}")
        fila_cie_item("Tarjetas:", f"S/ {float(c_vta):.2f}")
        fila_cie_item("Dólares Físicos:", f"$ {float(c_vusd):.2f}")

        if c_obs and str(c_obs).strip():
            pdf.ln(2)
            pdf.set_font("PrimaSans", 'B', 8)
            pdf.cell(70, 4, txt="Observaciones:", ln=True, align='L')
            pdf.set_font("PrimaSans", size=8)
            for l_obs in textwrap.wrap(str(c_obs).strip(), width=45):
                pdf.cell(70, 3.8, txt=l_obs, ln=True, align='L')

        pdf.ln(8)
        pdf.set_font("PrimaSans", size=8)
        pdf.cell(70, 4, txt="____________________________", ln=True, align='C')
        pdf.cell(70, 4, txt="Firma de Conformidad del Cajero", ln=True, align='C')

        if c_msg_emp and str(c_msg_emp).strip():
            pdf.ln(3)
            pdf.set_font("PrimaSans", 'B', 8)
            pdf.cell(70, 4.5, txt=str(c_msg_emp).strip(), ln=True, align='C')

        dir_base = os.path.dirname(os.path.abspath(__file__))
        nom_arch = f"cierre_turno_{c_id}.pdf"
        ruta_pdf = os.path.join(dir_base, "assets", nom_arch)
        os.makedirs(os.path.dirname(ruta_pdf), exist_ok=True)
        pdf.output(ruta_pdf)

        page.launch_url(f"/{nom_arch}", web_window_name="_blank")
        page.open(ft.SnackBar(ft.Text("✅ Ticket de Cierre de Turno generado en PDF.", color=ft.colors.WHITE), bgcolor=ft.colors.GREEN, duration=4000))

    except Exception as ex:
        print(f"Error generando ticket cierre: {ex}")
        page.open(ft.SnackBar(ft.Text(f"❌ Error al generar ticket cierre: {ex}"), bgcolor=ft.colors.RED))
