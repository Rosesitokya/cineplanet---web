import random
import os
from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import mysql.connector

app = Flask(__name__)
app.secret_key = "llave_super_secreta_cineplanet" 

def conectar():
    return mysql.connector.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=int(os.environ.get('DB_PORT', 3306)),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'cineplanet')
    )

@app.route('/')
def inicio():
    return render_template('index.html', peliculas=CATALOGO_PELICULAS)

@app.route('/pelicula/<int:id_peli>')
def detalle_pelicula(id_peli):
    peli = next((p for p in CATALOGO_PELICULAS if p['id'] == id_peli), CATALOGO_PELICULAS[0])
    cine_elegido = request.args.get('cine', 'Cineplanet San Miguel')
    return render_template('detalle_pelicula.html', peli=peli, cine=cine_elegido)

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        correo = request.form.get('correo')
        contrasena = request.form.get('contrasena')
        
        conexion = conectar()
        cursor = conexion.cursor()
        try:
            cursor.execute("INSERT INTO cliente (nombre, correo, contrasena, telefono) VALUES (%s, %s, %s, %s)", 
                           (nombre, correo, contrasena, '000000000'))
            conexion.commit()
            flash('Cuenta creada con éxito. Ahora inicia sesión.', 'success')
            return redirect(url_for('login'))
        except:
            flash('Error: Ese correo ya está registrado.', 'error')
        finally:
            conexion.close()
            
    return render_template('registro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo', '').strip()
        contrasena = request.form.get('contrasena', '').strip()

        # 1. Si es el administrador predeterminado, entra directo al panel admin
        if correo.lower() == 'admin@hotmail.com' and contrasena == 'HOLA':
            session['es_admin'] = True
            session['id_cliente'] = 0
            session['nombre'] = 'Administrador 1'
            return redirect(url_for('admin_dashboard'))

        conexion = conectar()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT * FROM cliente WHERE correo = %s AND contrasena = %s", (correo, contrasena))
        usuario = cursor.fetchone()
        conexion.close()

        if usuario:
            session['es_admin'] = False
            session['id_cliente'] = usuario['id_cliente']
            session['nombre'] = usuario['nombre']
            return redirect(url_for('inicio'))
        else:
            flash('Correo o contraseña incorrectos.', 'error')
            
    return render_template('login.html')

@app.route('/comprar', methods=['GET', 'POST'])
def comprar():
    if session.get('es_admin'):
        flash('🚫 Modo Administrador: Puedes navegar la cartelera, pero no realizar compras.', 'error')
        return redirect(url_for('inicio'))
    if 'id_cliente' not in session:
        flash('Inicia sesión primero para comprar tus entradas.', 'error')
        return redirect(url_for('login'))
        
    if request.method == 'GET':
        cine_pre = request.args.get('cine', '')
        horario_pre = request.args.get('horario', '')
        titulo_pre = request.args.get('titulo', 'Duna: parte dos')
        return render_template('comprar.html', cine_pre=cine_pre, horario_pre=horario_pre, titulo_pre=titulo_pre)
    
    if request.method == 'POST':
        # 1. Recibimos cantidades y datos del formulario
        cant_adulto = int(request.form.get('cant_adulto', 0))
        cant_mayor = int(request.form.get('cant_mayor', 0))
        cant_nino = int(request.form.get('cant_nino', 0))
        total_entradas = cant_adulto + cant_mayor + cant_nino

        asientos = request.form.get('asientos_seleccionados', '').strip()
        snack_nombre = request.form.get('snack_nombre', 'Ninguno')
        snack_precio = float(request.form.get('snack_precio', 0))
        metodo = request.form.get('metodo', 'Yape')

        if total_entradas == 0 or not asientos:
            flash('❌ Debes elegir al menos 1 entrada y seleccionar tus asientos en el mapa.', 'error')
            return redirect(url_for('comprar'))

        monto_entradas = (cant_adulto * 22.00) + (cant_mayor * 15.00) + (cant_nino * 12.00)
        monto_total = monto_entradas + snack_precio
        id_cliente = session['id_cliente']

        conexion = conectar()
        cursor = conexion.cursor(dictionary=True)
        try:
            cursor.execute("""
                INSERT INTO carrito_grupal (id_cliente, estado, monto_total, id_funcion, id_pelicula, id_sala)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (id_cliente, 'Pagado', monto_total, 1, 1, 1))
            id_carrito = cursor.lastrowid

            cursor.execute("""
                INSERT INTO transaccion (monto, metodo_pago, estado, id_carrito, id_cliente)
                VALUES (%s, %s, %s, %s, %s)
            """, (monto_total, metodo, 'Completado', id_carrito, id_cliente))
            id_transaccion = cursor.lastrowid

            codigo_locker = None
            if snack_precio > 0:
                cursor.execute("""
                    INSERT INTO pedidodulceria (estado_kds, tiempo_preparacion, id_carrito, id_cliente)
                    VALUES (%s, %s, %s, %s)
                """, ('En Preparacion', 5, id_carrito, id_cliente))
                id_pedido = cursor.lastrowid

                codigo_locker = random.randint(1000, 9999)
                cursor.execute("""
                    INSERT INTO smart_locker (codigo_apertura, estado, id_pedido)
                    VALUES (%s, %s, %s)
                """, (codigo_locker, 'Ocupado', id_pedido))

            conexion.commit()

            cursor.execute("SELECT titulo, duracion, clasificacion FROM pelicula WHERE id_pelicula = 1")
            pelicula = cursor.fetchone()
            codigo_ticket = f"CP-{id_transaccion}-{random.randint(1000, 9999)}"

            return render_template('confirmacion.html',
                                   pelicula=pelicula,
                                   asientos=asientos,
                                   total_entradas=total_entradas,
                                   monto_total=monto_total,
                                   snack_nombre=snack_nombre,
                                   codigo_locker=codigo_locker,
                                   codigo=codigo_ticket,
                                   metodo=metodo,
                                   id_carrito=id_carrito)
        except Exception as e:
            conexion.rollback()
            return f"<h2>❌ Error BD:</h2><p>{e}</p>"
        finally:
            conexion.close()


@app.route('/cancelar_entrada/<int:id_carrito>', methods=['POST'])
def cancelar_entrada(id_carrito):
    if 'id_cliente' not in session:
        return redirect(url_for('login'))

    conexion = conectar()
    cursor = conexion.cursor()
    try:
        cursor.execute("DELETE FROM smart_locker WHERE id_pedido IN (SELECT id_pedido FROM pedidodulceria WHERE id_carrito = %s)", (id_carrito,))
        cursor.execute("DELETE FROM pedidodulceria WHERE id_carrito = %s", (id_carrito,))
        cursor.execute("DELETE FROM comprobante WHERE id_transaccion IN (SELECT id_transaccion FROM transaccion WHERE id_carrito = %s)", (id_carrito,))
        cursor.execute("DELETE FROM transaccion WHERE id_carrito = %s", (id_carrito,))
        cursor.execute("DELETE FROM carrito_grupal WHERE id_carrito = %s AND id_cliente = %s", (id_carrito, session['id_cliente']))
        
        conexion.commit()
        flash('🗑️ Tu entrada ha sido cancelada y el reembolso está en proceso.', 'error')
    except Exception as e:
        conexion.rollback()
        flash(f'Error al cancelar la entrada: {e}', 'error')
    finally:
        conexion.close()

    return redirect(url_for('perfil'))

@app.route('/agregar_dulceria/<int:id_carrito>', methods=['POST'])
def agregar_dulceria(id_carrito):
    if 'id_cliente' not in session:
        return redirect(url_for('login'))

    conexion = conectar()
    cursor = conexion.cursor()
    try:
        cursor.execute("INSERT INTO pedidodulceria (estado_kds, tiempo_preparacion, id_carrito, id_cliente) VALUES (%s, %s, %s, %s)",
                       ('En Preparacion', 5, id_carrito, session['id_cliente']))
        id_pedido = cursor.lastrowid

        codigo_locker = random.randint(1000, 9999)
        cursor.execute("INSERT INTO smart_locker (codigo_apertura, estado, id_pedido) VALUES (%s, %s, %s)",
                       (codigo_locker, 'Ocupado', id_pedido))
        conexion.commit()
        flash(f'🍿 ¡Combo agregado! Tu código de Smart Locker es: {codigo_locker}', 'success')
    except Exception as e:
        conexion.rollback()
        flash(f'Error al pedir dulcería: {e}', 'error')
    finally:
        conexion.close()

    return redirect(url_for('perfil'))

@app.route('/perfil')
def perfil():
    if 'id_cliente' not in session:
        return redirect(url_for('login'))

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
        SELECT c.id_carrito, p.titulo, p.duracion, p.clasificacion, c.monto_total, t.metodo_pago, t.id_transaccion
        FROM carrito_grupal c
        JOIN pelicula p ON c.id_pelicula = p.id_pelicula
        JOIN transaccion t ON c.id_carrito = t.id_carrito
        WHERE c.id_cliente = %s
        ORDER BY c.id_carrito DESC
    """, (session['id_cliente'],))
    mis_entradas = cursor.fetchall()

    cursor.execute("""
        SELECT pd.id_pedido, pd.estado_kds, pd.tiempo_preparacion, sl.codigo_apertura, sl.estado AS estado_locker
        FROM pedidodulceria pd
        JOIN smart_locker sl ON pd.id_pedido = sl.id_pedido
        WHERE pd.id_cliente = %s
        ORDER BY pd.id_pedido DESC
    """, (session['id_cliente'],))
    mis_snacks = cursor.fetchall()

    conexion.close()
    plan_actual = session.get('plan_socio')
    return render_template('perfil.html',
                           entradas=mis_entradas,
                           snacks=mis_snacks,
                           plan_actual=plan_actual,
                           info_plan=PLANES_SOCIO.get(plan_actual))
CATALOGO_PELICULAS = [
    {
        'id': 1, 'titulo': 'Duna: parte dos', 'genero': 'Ciencia ficción', 'duracion': '2 h 46 min',
        'clasificacion': '+14', 'etiqueta': 'ESTRENO', 'imagen': 'poster_duna.jpg',
        'formato': '2D • Doblada', 'horarios': ['19:30', '21:00', '22:15'], 'estado': 'cartelera',
        'sinopsis': 'Paul Atreides se une a Chani y a los Fremen mientras busca venganza contra los conspiradores que destruyeron a su familia.',
        'trailer': 'https://www.youtube.com/embed/Way9Dexny3w'
    },
    {
        'id': 2, 'titulo': 'Robot salvaje', 'genero': 'Animación', 'duracion': '1 h 42 min',
        'clasificacion': 'APT', 'etiqueta': 'FAMILIAR', 'imagen': 'poster_robot.jpg',
        'formato': '2D • Doblada', 'horarios': ['16:30', '18:00', '20:15'], 'estado': 'cartelera',
        'sinopsis': 'Tras un naufragio, un robot inteligente llamado Roz queda varado en una isla deshabitada y deberá adaptarse al entorno y cuidar de un ganso huérfano.',
        'trailer': 'https://www.youtube.com/embed/67vbA5ZJdKQ'
    },
    {
        'id': 3, 'titulo': 'El planeta de los simios', 'genero': 'Aventura', 'duracion': '2 h 25 min',
        'clasificacion': '+14', 'etiqueta': '', 'imagen': 'poster_simios.jpg',
        'formato': '2D • Doblada', 'horarios': ['18:45', '21:30'], 'estado': 'cartelera',
        'sinopsis': 'Varias generaciones después del reinado de César, un joven simio emprende un viaje que lo llevará a cuestionar todo lo que sabe sobre el pasado.',
        'trailer': 'https://www.youtube.com/embed/XtFI7SNtVpY'
    },
    {
        'id': 4, 'titulo': 'Garfield: fuera de casa', 'genero': 'Animación', 'duracion': '1 h 41 min',
        'clasificacion': 'APT', 'etiqueta': '', 'imagen': 'poster_garfield.jpg',
        'formato': '2D • Doblada', 'horarios': ['15:00', '17:00', '19:20'], 'estado': 'cartelera',
        'sinopsis': 'Después de un inesperado reencuentro con su padre, Garfield y Odie se ven obligados a abandonar su cómoda vida para unirse a un divertido atraco.',
        'trailer': 'https://www.youtube.com/embed/IeFWNtMo1Fs'
    },
    {
        'id': 5, 'titulo': 'Deadpool & Wolverine', 'genero': 'Acción', 'duracion': '2 h 08 min',
        'clasificacion': '+14', 'etiqueta': 'ESTRENO', 'imagen': 'poster_deadpool.jpg',
        'formato': 'PRIME • Subtitulada', 'horarios': ['19:00', '21:45'], 'estado': 'cartelera',
        'sinopsis': 'Un apático Wade Wilson se esfuerza por adaptarse a la vida civil hasta que una amenaza existencial lo obliga a reclutar a un reacio Wolverine.',
        'trailer': 'https://www.youtube.com/embed/73_1biulkYk'
    },
    {
        'id': 6, 'titulo': 'Gladiador II', 'genero': 'Acción', 'duracion': '2 h 28 min',
        'clasificacion': '+14', 'etiqueta': 'PRÓXIMAMENTE', 'imagen': 'poster_gladiador.jpg',
        'formato': 'PRIME • Subtitulada', 'horarios': ['Estreno 25 Nov'], 'estado': 'proximamente',
        'sinopsis': 'Años después de presenciar la muerte de Máximo, Lucio se ve obligado a entrar en el Coliseo tras la conquista de su hogar por los emperadores tiránicos.',
        'trailer': 'https://www.youtube.com/embed/4rgYUipGJNo'
    },
    {
        'id': 7, 'titulo': 'Sonic 3', 'genero': 'Aventura', 'duracion': '1 h 50 min',
        'clasificacion': 'APT', 'etiqueta': 'PRÓXIMAMENTE', 'imagen': 'poster_sonic.jpg',
        'formato': '2D • Doblada', 'horarios': ['Estreno 19 Dic'], 'estado': 'proximamente',
        'sinopsis': 'Sonic, Knuckles y Tails se reúnen para enfrentarse a un nuevo y poderoso adversario: Shadow, un misterioso villano con poderes nunca antes vistos.',
        'trailer': 'https://www.youtube.com/embed/qSu6i2iFMO0'
    },
    {
        'id': 8, 'titulo': 'Mufasa: El Rey León', 'genero': 'Animación', 'duracion': '1 h 58 min',
        'clasificacion': 'APT', 'etiqueta': 'PRÓXIMAMENTE', 'imagen': 'poster_mufasa.jpg',
        'formato': '2D • Doblada', 'horarios': ['Estreno 26 Dic'], 'estado': 'proximamente',
        'sinopsis': 'Rafiki le cuenta a la joven cachorra Kiara la leyenda de Mufasa, un cachorro huérfano y perdido que conoce a un simpático león llamado Taka.',
        'trailer': 'https://www.youtube.com/embed/o17MF9vnabg'
    }
]

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('inicio'))

PLANES_SOCIO = {
    'Plata': {
        'precio': 19.90,
        'color': '#94a3b8',
        'beneficios': [
            '1 entrada 2D gratis al mes',
            '15% de descuento en Dulcería Online',
            'Refill de cancha grande a S/ 5.00',
            'Acceso a preventas exclusivas'
        ]
    },
    'Oro': {
        'precio': 39.90,
        'color': '#ffd500',
        'beneficios': [
            '2 entradas 2D o 3D gratis al mes',
            '25% de descuento en toda la Dulcería',
            'Prioridad de entrega en Smart Lockers',
            '1 Combo Cancha + Bebida gratis por cumpleaños',
            'Cero comisiones por compra online'
        ]
    },
    'Diamante': {
        'precio': 69.90,
        'color': '#38bdf8',
        'beneficios': [
            '4 entradas gratis al mes (incluye Sala PRIME y XTREME)',
            '40% de descuento ilimitado en Dulcería',
            'Smart Locker VIP reservado sin esperas',
            'Invitaciones dobles a Avant-Première',
            'Refill ilimitado de cancha y bebida en cada visita'
        ]
    }
}

@app.route('/socio')
def socio():
    plan_actual = session.get('plan_socio')  # None si aún no ha comprado membresía
    puntos_disponibles = 0

    if 'id_cliente' in session and plan_actual:
        conexion = conectar()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT COALESCE(SUM(monto), 0) AS total FROM transaccion WHERE id_cliente = %s", (session['id_cliente'],))
        total = float(cursor.fetchone()['total'])
        conexion.close()
        puntos_disponibles = max(0, int(total * 10) + session.get('puntos_bono', 0) - session.get('puntos_canjeados', 0))

    return render_template('socio.html',
                           plan_actual=plan_actual,
                           info_plan=PLANES_SOCIO.get(plan_actual),
                           planes=PLANES_SOCIO,
                           puntos=puntos_disponibles)

@app.route('/pagar_membresia/<plan>', methods=['GET', 'POST'])
def pagar_membresia(plan):
    if session.get('es_admin'):
        flash('🚫 Modo Administrador: Puedes navegar la cartelera, pero no realizar compras.', 'error')
        return redirect(url_for('inicio'))

    if 'id_cliente' not in session:
        flash('Inicia sesión o regístrate primero para comprar tu membresía.', 'error')
        return redirect(url_for('login'))

    if plan not in PLANES_SOCIO:
        return redirect(url_for('socio'))

    info_plan = PLANES_SOCIO[plan]

    if request.method == 'POST':
        metodo = request.form.get('metodo')
        comprobante = request.form.get('comprobante')
        documento = request.form.get('documento')

        session['plan_socio'] = plan
        session['metodo_socio'] = metodo
        session['comprobante_socio'] = f"{comprobante} ({documento})"
        bonos = {'Plata': 200, 'Oro': 500, 'Diamante': 1000}
        session['puntos_bono'] = bonos[plan]

        flash(f'💎 ¡Pago confirmado con {metodo}! Se emitió tu {comprobante}. Ya eres Socio {plan}.', 'success')
        return redirect(url_for('perfil'))

    return render_template('pagar_membresia.html', plan=plan, info=info_plan)


@app.route('/cancelar_membresia', methods=['POST'])
def cancelar_membresia():
    if 'id_cliente' not in session:
        return redirect(url_for('login'))

    plan_anterior = session.pop('plan_socio', None)
    session.pop('metodo_socio', None)
    session.pop('comprobante_socio', None)
    session.pop('puntos_bono', None)

    if plan_anterior:
        flash(f'Tu membresía Socio {plan_anterior} ha sido cancelada correctamente.', 'error')
    return redirect(url_for('perfil'))

@app.route('/canjear', methods=['POST'])
def canjear():
    if 'id_cliente' not in session or not session.get('plan_socio'):
        flash('🔒 Necesitas una membresía activa para canjear recompensas.', 'error')
        return redirect(url_for('socio'))

    premio = request.form.get('premio')
    costo = int(request.form.get('costo', 0))

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT COALESCE(SUM(monto), 0) AS total FROM transaccion WHERE id_cliente = %s", (session['id_cliente'],))
    total = float(cursor.fetchone()['total'])
    conexion.close()

    puntos_disponibles = int(total * 10) + session.get('puntos_bono', 0) - session.get('puntos_canjeados', 0)

    if puntos_disponibles >= costo:
        session['puntos_canjeados'] = session.get('puntos_canjeados', 0) + costo
        cupon = f"VIP-{random.randint(1000, 9999)}"
        flash(f'🎉 ¡Canjeaste "{premio}"! Código de canje: {cupon}', 'success')
    else:
        flash(f'❌ Te faltan {costo - puntos_disponibles} puntos para "{premio}".', 'error')

    return redirect(url_for('socio'))

@app.route('/cines')
def cines(): return render_template('cines.html')
@app.route('/promociones')
def promociones(): return render_template('promociones.html')

@app.route('/info/<seccion>', methods=['GET', 'POST'])
def info_pagina(seccion):
    paginas = {
        'nosotros': {
            'titulo': 'Sobre Cineplanet',
            'subtitulo': 'El cine nos encuentra desde hace más de 20 años.',
            'contenido': 'Somos la cadena de cines líder en el Perú, comprometidos con ofrecer la mejor experiencia audiovisual con salas 2D, 3D, XTREME y PRIME, además de nuestra nueva tecnología de pedidos en Dulcería con retiro sin colas en Smart Lockers.',
            'formulario': False
        },
        'faq': {
            'titulo': 'Preguntas Frecuentes',
            'subtitulo': 'Resolvemos tus dudas más comunes.',
            'contenido': '• ¿Cómo retiro mi dulcería? Al comprar online recibirás un código PIN de 4 dígitos en tu perfil para abrir tu Smart Locker.\n• ¿Puedo cancelar mis entradas? Sí, desde tu Perfil de Usuario puedes cancelar tus entradas antes de la función.\n• ¿Cómo acumulo puntos? Siendo Socio Plata, Oro o Diamante acumulas 10 puntos por cada S/ 1 en compras.',
            'formulario': False
        },
        'terminos': {
            'titulo': 'Términos y Condiciones',
            'subtitulo': 'Políticas de compra y uso de la plataforma.',
            'contenido': 'Las entradas adquiridas a través de nuestra plataforma digital son válidas únicamente para la sede, fecha, sala y horario seleccionados. Los beneficios de Socio Cineplanet son personales e intransferibles y se renuevan mensualmente salvo cancelación desde el perfil del usuario.',
            'formulario': False
        },
        'contactanos': {
            'titulo': 'Contáctanos',
            'subtitulo': '¿Tienes alguna consulta? Escríbenos y te responderemos a la brevedad.',
            'contenido': 'Nuestro equipo de atención al cliente atiende de lunes a domingo de 9:00 a.m. a 10:00 p.m.',
            'formulario': True,
            'boton': 'Enviar mensaje ➔'
        },
        'reclamaciones': {
            'titulo': 'Libro de Reclamaciones',
            'subtitulo': 'Conforme a lo establecido en el Código de Protección y Defensa del Consumidor.',
            'contenido': 'Registra tu queja o reclamo detallando la sede y el inconveniente. Recibirás un código de seguimiento inmediato.',
            'formulario': True,
            'boton': 'Registrar reclamo ➔'
        }
    }

    data = paginas.get(seccion, paginas['nosotros'])

    if request.method == 'POST':
        codigo_caso = f"CP-CASE-{random.randint(1000, 9999)}"
        flash(f'✅ Hemos registrado tu solicitud con el código {codigo_caso}. Te responderemos pronto.', 'success')
        return redirect(url_for('info_pagina', seccion=seccion))

    return render_template('info.html', data=data, seccion=seccion)

GRUPOS_ACTIVOS = {}

@app.route('/compra_grupal', methods=['GET', 'POST'])
def compra_grupal():
    if session.get('es_admin'):
        flash('🚫 Modo Administrador: Puedes navegar la cartelera, pero no realizar compras.', 'error')
        return redirect(url_for('inicio'))
    
    if 'id_cliente' not in session:
        flash('Inicia sesión para crear o unirte a una Compra Grupal.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        accion = request.form.get('accion')

        if accion == 'crear':
            codigo = f"GRP-{random.randint(1000, 9999)}"
            id_peli = int(request.form.get('id_pelicula', 1))
            peli = next((p for p in CATALOGO_PELICULAS if p['id'] == id_peli), CATALOGO_PELICULAS[0])
            cine = request.form.get('cine', 'Cineplanet San Miguel')
            horario = request.form.get('horario', '19:30')

            # Bloqueo de concurrencia: 10 minutos (tiempo_expiracion)
            expira = datetime.now() + timedelta(minutes=10)

            GRUPOS_ACTIVOS[codigo] = {
                'codigo': codigo,
                'organizador': session['nombre'],
                'pelicula': peli['titulo'],
                'id_pelicula': id_peli,
                'cine': cine,
                'horario': horario,
                'expira': expira.timestamp(),
                'ocupados_base': ['B4', 'B5', 'C6', 'C7', 'D3', 'E8'],
                'miembros': {
                    str(session['id_cliente']): {
                        'nombre': session['nombre'],
                        'color': '#ffd500',
                        'asientos': [],
                        'snack_nombre': 'Ninguno',
                        'snack_precio': 0.0,
                        'pagado': False,
                        'metodo': '',
                        'comprobante': ''
                    }
                },
                'id_carrito_bd': None
            }
            return redirect(url_for('ver_grupo', codigo=codigo))

        elif accion == 'unirse':
            codigo = request.form.get('codigo', '').strip().upper()
            if codigo not in GRUPOS_ACTIVOS:
                flash('❌ No existe ninguna sala grupal con ese código.', 'error')
                return redirect(url_for('compra_grupal'))

            grupo = GRUPOS_ACTIVOS[codigo]
            uid = str(session['id_cliente'])
            if uid not in grupo['miembros']:
                colores = ['#38bdf8', '#4ade80', '#f472b6', '#fb923c', '#a78bfa']
                color = colores[len(grupo['miembros']) % len(colores)]
                grupo['miembros'][uid] = {
                    'nombre': session['nombre'],
                    'color': color,
                    'asientos': [],
                    'snack_nombre': 'Ninguno',
                    'snack_precio': 0.0,
                    'pagado': False,
                    'metodo': '',
                    'comprobante': ''
                }
            return redirect(url_for('ver_grupo', codigo=codigo))

    pelis_cartelera = [p for p in CATALOGO_PELICULAS if p['estado'] == 'cartelera']
    return render_template('grupo.html', modo='lobby', peliculas=pelis_cartelera)


@app.route('/grupo/<codigo>')
def ver_grupo(codigo):
    if 'id_cliente' not in session:
        flash('Inicia sesión para entrar a la sala grupal.', 'error')
        return redirect(url_for('login'))

    codigo = codigo.upper()
    if codigo not in GRUPOS_ACTIVOS:
        flash('❌ La sala grupal expiró o no existe.', 'error')
        return redirect(url_for('compra_grupal'))

    grupo = GRUPOS_ACTIVOS[codigo]
    uid = str(session['id_cliente'])
    if uid not in grupo['miembros']:
        colores = ['#38bdf8', '#4ade80', '#f472b6', '#fb923c', '#a78bfa']
        grupo['miembros'][uid] = {
            'nombre': session['nombre'],
            'color': colores[len(grupo['miembros']) % len(colores)],
            'asientos': [],
            'snack_nombre': 'Ninguno',
            'snack_precio': 0.0,
            'pagado': False,
            'metodo': '',
            'comprobante': ''
        }

    return render_template('grupo.html', modo='sala', grupo=grupo, uid=uid)


@app.route('/api/grupo/<codigo>/estado')
def api_estado_grupo(codigo):
    grupo = GRUPOS_ACTIVOS.get(codigo.upper())
    if not grupo:
        return jsonify({'error': 'Grupo no encontrado'}), 404

    restante = max(0, int(grupo['expira'] - datetime.now().timestamp()))
    return jsonify({
        'restante': restante,
        'miembros': grupo['miembros'],
        'ocupados_base': grupo['ocupados_base']
    })


@app.route('/api/grupo/<codigo>/asiento', methods=['POST'])
def api_toggle_asiento(codigo):
    if 'id_cliente' not in session:
        return jsonify({'ok': False, 'msg': 'No autenticado'}), 401

    grupo = GRUPOS_ACTIVOS.get(codigo.upper())
    if not grupo:
        return jsonify({'ok': False, 'msg': 'Sala expirada'}), 404

    data = request.get_json()
    asiento = data.get('asiento')
    uid = str(session['id_cliente'])
    miembro = grupo['miembros'].get(uid)

    if miembro['pagado']:
        return jsonify({'ok': False, 'msg': 'Ya pagaste tu parte, no puedes cambiar tus asientos.'})

    for otro_id, m in grupo['miembros'].items():
        if otro_id != uid and asiento in m['asientos']:
            return jsonify({'ok': False, 'msg': f'Asiento bloqueado por {m["nombre"]}.'})

    if asiento in miembro['asientos']:
        miembro['asientos'].remove(asiento)
    else:
        miembro['asientos'].append(asiento)

    return jsonify({'ok': True, 'miembros': grupo['miembros']})


@app.route('/api/grupo/<codigo>/snack', methods=['POST'])
def api_grupo_snack(codigo):
    if 'id_cliente' not in session:
        return jsonify({'ok': False}), 401

    grupo = GRUPOS_ACTIVOS.get(codigo.upper())
    uid = str(session['id_cliente'])
    data = request.get_json()
    if grupo and uid in grupo['miembros'] and not grupo['miembros'][uid]['pagado']:
        grupo['miembros'][uid]['snack_nombre'] = data.get('nombre', 'Ninguno')
        grupo['miembros'][uid]['snack_precio'] = float(data.get('precio', 0))
    return jsonify({'ok': True, 'miembros': grupo['miembros']})


@app.route('/grupo/<codigo>/pagar', methods=['POST'])
def pagar_parte_grupo(codigo):
    if 'id_cliente' not in session:
        return redirect(url_for('login'))

    grupo = GRUPOS_ACTIVOS.get(codigo.upper())
    if not grupo:
        flash('La sala grupal expiró.', 'error')
        return redirect(url_for('compra_grupal'))

    uid = str(session['id_cliente'])
    miembro = grupo['miembros'][uid]

    if not miembro['asientos']:
        flash('❌ Selecciona al menos 1 asiento antes de pagar tu parte.', 'error')
        return redirect(url_for('ver_grupo', codigo=codigo))

    metodo = request.form.get('metodo', 'Yape')
    tipo_comp = request.form.get('comprobante', 'Boleta Electrónica')
    doc = request.form.get('documento', '00000000')
    monto_parte = (len(miembro['asientos']) * 22.00) + miembro['snack_precio']

    conexion = conectar()
    cursor = conexion.cursor()
    try:
        if not grupo['id_carrito_bd']:
            cursor.execute("""
                INSERT INTO carrito_grupal (id_cliente, estado, monto_total, id_funcion, id_pelicula, id_sala)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (session['id_cliente'], 'En Proceso', monto_parte, 1, 1, 1))
            grupo['id_carrito_bd'] = cursor.lastrowid
        else:
            cursor.execute("""
                UPDATE carrito_grupal SET monto_total = monto_total + %s WHERE id_carrito = %s
            """, (monto_parte, grupo['id_carrito_bd']))

        cursor.execute("""
            INSERT INTO transaccion (monto, metodo_pago, estado, id_carrito, id_cliente)
            VALUES (%s, %s, %s, %s, %s)
        """, (monto_parte, metodo, 'Completado', grupo['id_carrito_bd'], session['id_cliente']))
        id_trans = cursor.lastrowid

        try:
            cursor.execute("""
                INSERT INTO comprobante (tipo, detalles_tributarios, id_transaccion)
                VALUES (%s, %s, %s)
            """, (tipo_comp, f"Doc: {doc} | Grupo: {codigo}", id_trans))
        except:
            pass

        pin_msg = ""
        if miembro['snack_precio'] > 0:
            cursor.execute("""
                INSERT INTO pedidodulceria (estado_kds, tiempo_preparacion, id_carrito, id_cliente)
                VALUES (%s, %s, %s, %s)
            """, ('En Preparacion', 2, grupo['id_carrito_bd'], session['id_cliente']))
            id_pedido = cursor.lastrowid
            pin = random.randint(1000, 9999)
            cursor.execute("""
                INSERT INTO smart_locker (codigo_apertura, estado, id_pedido)
                VALUES (%s, %s, %s)
            """, (pin, 'Ocupado', id_pedido))
            pin_msg = f" • Smart Locker PIN: {pin}"

        miembro['pagado'] = True
        miembro['metodo'] = metodo
        miembro['comprobante'] = f"{tipo_comp} ({doc})"

        if all(m['pagado'] for m in grupo['miembros'].values()):
            cursor.execute("UPDATE carrito_grupal SET estado = 'Pagado' WHERE id_carrito = %s", (grupo['id_carrito_bd'],))

        conexion.commit()
        flash(f'✅ ¡Pagaste tu parte (S/ {monto_parte:.2f}) con {metodo}!{pin_msg}', 'success')
    except Exception as e:
        conexion.rollback()
        flash(f'❌ Error al procesar tu pago: {e}', 'error')
    finally:
        conexion.close()

    return redirect(url_for('ver_grupo', codigo=codigo))

FUNCIONES_ADMIN = [
    {'id': 1, 'pelicula': 'Duna: parte dos', 'sala': 'Sala 01 · 2D SUB', 'horario': '19:30', 'vendidas': 148, 'capacidad': 176, 'estado': 'Venta abierta'},
    {'id': 2, 'pelicula': 'Robot salvaje', 'sala': 'Sala 03 · 2D DOB', 'horario': '20:15', 'vendidas': 112, 'capacidad': 180, 'estado': 'Venta abierta'},
    {'id': 3, 'pelicula': 'El planeta de los simios', 'sala': 'Sala 02 · PRIME', 'horario': '21:30', 'vendidas': 169, 'capacidad': 180, 'estado': 'Últimas butacas'},
    {'id': 4, 'pelicula': 'Garfield: fuera de casa', 'sala': 'Sala 04 · 2D DOB', 'horario': '19:20', 'vendidas': 68, 'capacidad': 180, 'estado': 'Venta abierta'}
]

DATOS_SEDES = {
    'San Miguel': {
        'ingresos_base': 28520, 'entradas_base': 1240, 'ocupacion': 68, 'funciones_tot': 32,
        'horas': [80, 140, 190, 160, 280, 240, 150]
    },
    'San Martín de Porres': {
        'ingresos_base': 19400, 'entradas_base': 890, 'ocupacion': 54, 'funciones_tot': 24,
        'horas': [50, 95, 130, 120, 210, 185, 100]
    },
    'Salaverry': {
        'ingresos_base': 34100, 'entradas_base': 1420, 'ocupacion': 79, 'funciones_tot': 36,
        'horas': [110, 165, 220, 195, 310, 270, 150]
    }
}

@app.route('/admin')
def admin_dashboard():
    if not session.get('es_admin'):
        flash('🔒 Acceso restringido solo para administradores.', 'error')
        return redirect(url_for('login'))

    sede = request.args.get('sede', 'San Miguel')
    if sede not in DATOS_SEDES:
        sede = 'San Miguel'
    base = DATOS_SEDES[sede]

    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS cant, COALESCE(SUM(monto), 0) AS total FROM transaccion")
    stats = cursor.fetchone()
    ventas_reales = int(stats['cant'])
    ingresos_reales = float(stats['total'])

    cursor.execute("""
        SELECT t.id_transaccion, c.nombre AS cliente, c.correo, t.monto, t.metodo_pago, t.estado, cg.id_carrito
        FROM transaccion t
        JOIN cliente c ON t.id_cliente = c.id_cliente
        JOIN carrito_grupal cg ON t.id_carrito = cg.id_carrito
        ORDER BY t.id_transaccion DESC
    """)
    ventas = cursor.fetchall()

    cursor.execute("""
        SELECT pd.id_pedido, c.nombre AS cliente, pd.estado_kds, pd.tiempo_preparacion, sl.codigo_apertura, sl.estado AS estado_locker
        FROM pedidodulceria pd
        JOIN cliente c ON pd.id_cliente = c.id_cliente
        JOIN smart_locker sl ON pd.id_pedido = sl.id_pedido
        ORDER BY pd.id_pedido DESC
    """)
    pedidos_kds = cursor.fetchall()
    conexion.close()

    ingresos_totales = base['ingresos_base'] + ingresos_reales
    entradas_totales = base['entradas_base'] + ventas_reales
    horas_labels = ['10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00']
    valores_horas = list(base['horas'])
    valores_horas[4] += ventas_reales  # Las compras reales de BD suben la barra de las 18:00
    max_val = max(valores_horas) or 1

    grafico = []
    for h, v in zip(horas_labels, valores_horas):
        grafico.append({
            'hora': h,
            'valor': v,
            'altura': int((v / max_val) * 150),
            'es_pico': (v == max_val)
        })

    return render_template('admin.html',
                           sede=sede,
                           sedes=list(DATOS_SEDES.keys()),
                           ingresos=ingresos_totales,
                           entradas=entradas_totales,
                           ocupacion=base['ocupacion'],
                           funciones_tot=base['funciones_tot'],
                           ventas_reales=ventas_reales,
                           grafico=grafico,
                           funciones=FUNCIONES_ADMIN,
                           peliculas=CATALOGO_PELICULAS,
                           ventas=ventas,
                           pedidos_kds=pedidos_kds)


@app.route('/admin/nueva_funcion', methods=['POST'])
def admin_nueva_funcion():
    if not session.get('es_admin'):
        return redirect(url_for('login'))

    nuevo_id = max([f['id'] for f in FUNCIONES_ADMIN], default=0) + 1
    FUNCIONES_ADMIN.insert(0, {
        'id': nuevo_id,
        'pelicula': request.form.get('pelicula'),
        'sala': request.form.get('sala'),
        'horario': request.form.get('horario'),
        'vendidas': 0,
        'capacidad': 180,
        'estado': 'Venta abierta'
    })
    flash('✅ Nueva función agregada a la programación.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/eliminar_funcion/<int:id_func>', methods=['POST'])
def admin_eliminar_funcion(id_func):
    if not session.get('es_admin'):
        return redirect(url_for('login'))

    global FUNCIONES_ADMIN
    FUNCIONES_ADMIN = [f for f in FUNCIONES_ADMIN if f['id'] != id_func]
    flash('🗑️ Función eliminada de la programación.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/nueva_pelicula', methods=['POST'])
def admin_nueva_pelicula():
    if not session.get('es_admin'):
        return redirect(url_for('login'))

    archivo = request.files.get('imagen_archivo')
    nombre_img = 'poster_duna.jpg'
    if archivo and archivo.filename:
        nombre_img = secure_filename(archivo.filename)
        archivo.save(os.path.join('static', nombre_img))

    trailer_raw = request.form.get('trailer', '').strip()
    if 'watch?v=' in trailer_raw:
        trailer_url = trailer_raw.replace('watch?v=', 'embed/').split('&')[0]
    elif 'youtu.be/' in trailer_raw:
        trailer_url = trailer_raw.replace('youtu.be/', 'www.youtube.com/embed/').split('?')[0]
    else:
        trailer_url = trailer_raw or 'https://www.youtube.com/embed/Way9Dexny3w'

    estado = request.form.get('estado', 'cartelera')
    nuevo_id = max([p['id'] for p in CATALOGO_PELICULAS], default=0) + 1

    CATALOGO_PELICULAS.append({
        'id': nuevo_id,
        'titulo': request.form.get('titulo'),
        'genero': request.form.get('genero'),
        'duracion': request.form.get('duracion'),
        'clasificacion': request.form.get('clasificacion'),
        'etiqueta': 'ESTRENO' if estado == 'cartelera' else 'PRÓXIMAMENTE',
        'imagen': nombre_img,
        'formato': request.form.get('formato', '2D • Doblada'),
        'horarios': ['18:00', '20:30'] if estado == 'cartelera' else [request.form.get('fecha_estreno', 'Próximamente')],
        'estado': estado,
        'sinopsis': request.form.get('sinopsis'),
        'trailer': trailer_url
    })
    flash(f'🎬 Película publicada en {"En cartelera" if estado == "cartelera" else "Próximamente"}.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/eliminar_pelicula/<int:id_peli>', methods=['POST'])
def admin_eliminar_pelicula(id_peli):
    if not session.get('es_admin'):
        return redirect(url_for('login'))

    global CATALOGO_PELICULAS
    CATALOGO_PELICULAS = [p for p in CATALOGO_PELICULAS if p['id'] != id_peli]
    flash('🗑️ Película eliminada de la cartelera.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/kds/<int:id_pedido>', methods=['POST'])
def admin_actualizar_kds(id_pedido):
    if not session.get('es_admin'):
        return redirect(url_for('login'))

    nuevo_estado = request.form.get('estado_kds', 'Listo en Locker')
    conexion = conectar()
    cursor = conexion.cursor()
    cursor.execute("UPDATE pedidodulceria SET estado_kds = %s WHERE id_pedido = %s", (nuevo_estado, id_pedido))
    conexion.commit()
    conexion.close()
    flash(f'🍿 Pedido #{id_pedido} actualizado a: {nuevo_estado}', 'success')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)