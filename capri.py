# ============================================================
#  CAPRI - tu asistente de voz con cuerpo cyberpunk
# ============================================================
import os, re, json, math, time, html, random, threading, subprocess
import webbrowser, datetime, zipfile, platform, unicodedata, urllib.parse
from pathlib import Path
import tkinter as tk
import speech_recognition as sr
import pyttsx3

try:
    from PIL import Image, ImageTk
except Exception:
    Image = ImageTk = None
try:
    import pyautogui
except Exception:
    pyautogui = None
try:
    import pyperclip
except Exception:
    pyperclip = None
try:
    import ollama
    cliente = ollama
except Exception:
    cliente = None

CARPETA = os.path.dirname(os.path.abspath(__file__))
MEMORIA = os.path.join(CARPETA, "memoria.json")
CONTACTOS = os.path.join(CARPETA, "contactos.json")
CREACIONES = os.path.join(CARPETA, "creaciones")

# ---------------- AJUSTES (puedes cambiarlos) ----------------
ESPERA_WHATSAPP = 20                      # segundos que espera a que cargue WhatsApp Web
PEDIR_PERMISO_AL_ABRIR_PAGINAS = False    # ponlo en True si quieres permiso hasta para abrir páginas
MOVERSE = False                           # False = Capri se queda quieta. True = pasea por la pantalla
MARGEN_X = 10                             # distancia al borde derecho de la pantalla
MARGEN_Y = 60                             # distancia al borde de abajo (60 = encima de la barra de tareas)
SEGUNDOS_ACTIVA = 60        # tiempo que Capri sigue atenta sin que digas "Capri"
SIEMPRE_ESCUCHANDO = False  # True = nunca necesita que la llames
despierta_hasta = 0         # (no tocar) hasta qué momento sigue atenta

PALABRAS = ("capri", "kapri", "cápri", "capry", "capi", "cafri", "capre", "kapry", "cabri", "caprí")
SOLO_AL_INICIO = ("mira", "kapi", "cali")

# Frases que dice Capri (cambian al azar)
INICIO = ["Claro, de inmediato.", "Enseguida.", "Por supuesto, ahora mismo.", "Con gusto, de inmediato."]
HECHO = ["Ya lo hice. ¿En qué más te ayudo?", "Listo, ya está. ¿Qué más necesitas?", "Hecho. ¿En qué más te ayudo?"]
MAS = ["¿En qué más te ayudo?", "¿Qué más necesitas?", "¿Algo más?"]

SISTEMA = ("Eres Capri, una asistente de IA con estética cyberpunk. Hablas en español, "
           "con tono cercano, leal y con un toque de humor. Respondes en máximo "
           "2 oraciones cortas porque tu respuesta se dice en voz alta.")

SITIOS = {
    "youtube": "https://youtube.com", "google": "https://google.com",
    "gmail": "https://mail.google.com", "instagram": "https://instagram.com",
    "github": "https://github.com", "whatsapp": "https://web.whatsapp.com",
    "spotify": "https://open.spotify.com", "netflix": "https://netflix.com",
}

estado = "inactivo"   # inactivo | escuchando | pensando | hablando
salir = False
MIC = None
RECO = None

# ---------------- UTILIDADES ----------------
def normalizar(t):
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()

def buscar_palabra(frases):
    # Revisa cada opción que oyó Google. Devuelve la orden, o None si no la llamaron.
    for frase in frases:
        frase = frase.lower().strip()
        for p in PALABRAS:
            if p in frase:
                return frase.split(p, 1)[1].strip(" ,.")
        for p in SOLO_AL_INICIO:
            if frase == p or frase.startswith(p + " "):
                return frase[len(p):].strip(" ,.")
    return None

# ---------------- MEMORIA ----------------
def cargar_memoria():
    try:
        with open(MEMORIA, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def guardar_memoria():
    with open(MEMORIA, "w", encoding="utf-8") as f:
        json.dump(historial[-40:], f, ensure_ascii=False, indent=2)

historial = cargar_memoria()

# ---------------- RESPALDO ----------------
def hacer_respaldo():
    destino = os.path.join(CARPETA, "backups")
    os.makedirs(destino, exist_ok=True)
    nombre = datetime.datetime.now().strftime("respaldo_%Y%m%d_%H%M%S.zip")
    ruta = os.path.join(destino, nombre)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for raiz, dirs, archivos in os.walk(CARPETA):
            dirs[:] = [d for d in dirs if d not in ("backups", "venv", ".git", "__pycache__")]
            for a in archivos:
                completo = os.path.join(raiz, a)
                z.write(completo, os.path.relpath(completo, CARPETA))
    copias = sorted(os.listdir(destino))
    for vieja in copias[:-10]:
        os.remove(os.path.join(destino, vieja))
    return nombre

# ---------------- VOZ (Capri habla) ----------------
import asyncio

# --- AJUSTES DE LA VOZ (puedes cambiarlos) ---
USAR_VOZ_NEURAL = True             # True = voz natural por internet. False = voz normal de Windows
VOZ_NEURAL = "es-CO-SalomeNeural"  # voz de inicio (después la cambias diciendo "Capri, cambia tu voz")
RITMO = "+0%"                      # velocidad: "+10%" más rápida, "-10%" más lenta
TONO = "+0Hz"                      # tono: "+5Hz" más aguda, "-5Hz" más grave
VOZ_PREFERIDA = "sabina"           # voz normal de Windows: parte de su nombre, en minúsculas
VELOCIDAD = 175                    # velocidad de la voz normal de Windows

# Voces entre las que puedes escoger (código y descripción)
VOCES = [
    ("es-CO-SalomeNeural", "Salomé, mujer de Colombia"),
    ("es-CO-GonzaloNeural", "Gonzalo, hombre de Colombia"),
    ("es-MX-DaliaNeural", "Dalia, mujer de México"),
    ("es-MX-JorgeNeural", "Jorge, hombre de México"),
    ("es-ES-ElviraNeural", "Elvira, mujer de España"),
    ("es-ES-AlvaroNeural", "Álvaro, hombre de España"),
    ("es-AR-ElenaNeural", "Elena, mujer de Argentina"),
    ("es-US-PalomaNeural", "Paloma, mujer de Estados Unidos"),
]

ARCHIVO_VOZ = os.path.join(CARPETA, "voz.json")

def cargar_voz():
    try:
        with open(ARCHIVO_VOZ, "r", encoding="utf-8") as f:
            return json.load(f).get("voz", VOZ_NEURAL)
    except Exception:
        return VOZ_NEURAL

def guardar_voz(codigo):
    try:
        with open(ARCHIVO_VOZ, "w", encoding="utf-8") as f:
            json.dump({"voz": codigo}, f)
    except Exception as e:
        print("No pude guardar la voz:", e)

VOZ_NEURAL = cargar_voz()   # usa la voz que escogiste la última vez

try:
    import edge_tts
    import pygame
    pygame.mixer.init()
except Exception:
    edge_tts = None
    pygame = None

def crear_motor():
    motor = pyttsx3.init()
    voces = motor.getProperty("voices")
    print("Voces de Windows disponibles:", [v.name for v in voces])
    elegida = None
    for v in voces:
        if VOZ_PREFERIDA and VOZ_PREFERIDA in v.name.lower():
            elegida = v.id
            break
    if not elegida:
        for v in voces:
            if "spanish" in v.name.lower() or "es-" in v.id.lower() or "sabina" in v.name.lower():
                elegida = v.id
                break
    if elegida:
        motor.setProperty("voice", elegida)
    motor.setProperty("rate", VELOCIDAD)
    return motor

def hablar_neural(texto):
    ruta = os.path.join(CARPETA, "voz_temp.mp3")
    async def generar():
        await edge_tts.Communicate(texto, VOZ_NEURAL, rate=RITMO, pitch=TONO).save(ruta)
    asyncio.run(generar())
    pygame.mixer.music.load(ruta)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.05)
    pygame.mixer.music.unload()

def hablar(motor, texto):
    global estado
    print("Capri:", texto)
    estado = "hablando"
    if USAR_VOZ_NEURAL and edge_tts and pygame:
        try:
            hablar_neural(texto)
            return
        except Exception as e:
            print("La voz natural falló, uso la normal:", e)
    motor.say(texto)
    motor.runAndWait()

def cambiar_voz(motor, orden):
    # Capri se presenta con cada voz y tú dices "sí" a la que te guste
    global VOZ_NEURAL, estado
    if not (USAR_VOZ_NEURAL and edge_tts and pygame):
        hablar(motor, "La voz natural no está activa, así que no puedo cambiar de voz.")
        return
    anterior = VOZ_NEURAL
    # Si dices el nombre ("cambia tu voz a Gonzalo"), la pone directo
    n = normalizar(orden)
    for codigo, desc in VOCES:
        nombre = desc.split(",")[0]
        if normalizar(nombre) in n:
            VOZ_NEURAL = codigo
            guardar_voz(codigo)
            hablar(motor, f"Listo, ahora soy {nombre}. ¿Qué tal suena mi voz?")
            return
    # Si no, se presenta con todas las voces, una por una
    for codigo, desc in VOCES:
        VOZ_NEURAL = codigo
        hablar(motor, f"Hola, soy {desc}. ¿Me quedo con esta voz? Di sí o no.")
        estado = "escuchando"
        respuesta = None
        for f in escuchar_frases(8):
            palabras = set(normalizar(f).split())
            if palabras & NO_PALABRAS:
                respuesta = False
                break
            if palabras & SI_PALABRAS:
                respuesta = True
                break
        if respuesta:
            guardar_voz(codigo)
            hablar(motor, "Perfecto, me quedo con esta voz.")
            return
        if respuesta is None:
            VOZ_NEURAL = anterior
            hablar(motor, "No te escuché, así que dejo mi voz como estaba.")
            return
    VOZ_NEURAL = anterior
    hablar(motor, "Ya te mostré todas mis voces. Dejo la que tenía.")

# ---------------- PERMISOS ----------------
SI_PALABRAS = {"si", "claro", "dale", "adelante", "confirmo", "ok", "okey",
               "hazlo", "autorizo", "permiso", "acuerdo"}
NO_PALABRAS = {"no", "cancela", "cancelar", "detente", "negativo", "nunca"}

def escuchar_frases(segundos=8):
    try:
        audio = RECO.listen(MIC, timeout=segundos, phrase_time_limit=6)
        r = RECO.recognize_google(audio, language="es-CO", show_all=True)
        return [a["transcript"] for a in r.get("alternative", [])] if r else []
    except Exception:
        return []

def pedir_permiso(motor, pregunta):
    # Capri pregunta en voz alta y espera tu "sí" o "no"
    global estado
    for _ in range(2):
        hablar(motor, pregunta + " Di: sí, te doy permiso. O di: no.")
        estado = "escuchando"
        frases = escuchar_frases()
        print("Respuesta:", frases)
        for f in frases:
            palabras = set(normalizar(f).split())
            if palabras & NO_PALABRAS:
                return False
            if palabras & SI_PALABRAS:
                hablar(motor, random.choice(INICIO))
                return True
    hablar(motor, "No escuché una respuesta clara, así que cancelo.")
    return False

# ---------------- CONTACTOS ----------------
def cargar_contactos():
    try:
        with open(CONTACTOS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def buscar_contacto(plataforma, nombre):
    contactos = cargar_contactos().get(plataforma, {})
    n = normalizar(nombre)
    for k, v in contactos.items():
        if normalizar(k) == n:
            return k, v
    for k, v in contactos.items():
        if n and (n in normalizar(k) or normalizar(k) in n):
            return k, v
    return None, None

# ---------------- MENSAJES ----------------
PATRON_MENSAJE = re.compile(
    r"(?:manda|mandar|envía|envia|enviar|escribe|escribir)\s+(?:un\s+)?"
    r"(mensaje|whatsapp|wasap|guasap|instagram|insta)\s+(?:por\s+(\w+)\s+)?a\s+(.+?)\s+"
    r"(?:que diga|que dice|diciendo|diciéndole|diciendole)\s+(.+)")

def enviar_mensaje(motor, m):
    canal = normalizar(m.group(1))
    por = normalizar(m.group(2) or "")
    nombre, texto = m.group(3).strip(), m.group(4).strip()
    es_ig = canal in ("instagram", "insta") or por in ("instagram", "insta", "ig")
    plataforma = "instagram" if es_ig else "whatsapp"
    nombre_plat = "Instagram" if es_ig else "WhatsApp"

    clave, dato = buscar_contacto(plataforma, nombre)
    if not dato:
        hablar(motor, f"No encontré a {nombre} en tus contactos de {nombre_plat}. "
                      "Agrégalo en el archivo contactos punto json.")
        return
    if not pedir_permiso(motor, f"Voy a enviar por {nombre_plat} a {clave} este mensaje: {texto}. "
                                "¿Me das permiso?"):
        hablar(motor, "Entendido, no envié nada.")
        return

    if plataforma == "whatsapp":
        url = ("https://web.whatsapp.com/send?phone=" + str(dato) +
               "&text=" + urllib.parse.quote(texto))
        hablar(motor, "Abriendo WhatsApp. No toques el mouse ni el teclado unos segundos.")
        webbrowser.open(url)
        time.sleep(ESPERA_WHATSAPP)
        if pyautogui:
            pyautogui.press("enter")
            hablar(motor, "Listo, mensaje enviado.")
        else:
            hablar(motor, "Dejé el mensaje escrito. Presiona Enter para enviarlo.")
    else:
        webbrowser.open("https://ig.me/m/" + str(dato))
        if pyperclip:
            pyperclip.copy(texto)
        hablar(motor, "Abrí el chat de Instagram y copié tu mensaje. "
                      "Pégalo con Control V y envíalo tú.")

# ---------------- MAPAS Y PRESENTACIONES ----------------
PATRON_CREAR = re.compile(
    r"(?:crea|crear|haz|hacer|genera|generar)\s+(?:un|una)?\s*"
    r"(mapa conceptual|mapa mental|mapa|presentación|presentacion|diapositivas)\s+"
    r"(?:de la|de los|de las|del|de|sobre)\s+(.+?)(?:\s+con\s+(.+))?$")

PLANTILLA_MAPA = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>__TITULO__</title>
<style>body{background:#0b0b14;color:#fff;font-family:Segoe UI,Arial,sans-serif;margin:0;padding:20px;text-align:center}
h1{color:#00e5ff}.mermaid{background:#14061f;border-radius:12px;padding:20px}</style></head>
<body><h1>__TITULO__</h1>
<pre class="mermaid">
__MAPA__
</pre>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>mermaid.initialize({startOnLoad:true,theme:'dark'});</script></body></html>"""

PLANTILLA_PRES = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>__TITULO__</title>
<style>
body{margin:0;background:#0b0b14;color:#fff;font-family:Segoe UI,Arial,sans-serif}
.slide{display:none;min-height:100vh;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:40px;box-sizing:border-box;outline:none}
.slide h1,.slide h2{color:#00e5ff;font-size:3em;margin:0 0 20px}
.slide p{font-size:1.6em;color:#ddd;max-width:900px}
.nav{position:fixed;bottom:15px;right:20px}
.nav button{background:#ff2a8a;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:1.1em;cursor:pointer;margin-left:6px}
</style></head><body>
__SLIDES__
<div class="nav"><button onclick="mover(-1)">&#9664;</button><button onclick="mover(1)">&#9654;</button></div>
<script>
var i=0,s=document.querySelectorAll('.slide');
function ver(){s.forEach(function(e,k){e.style.display=(k==i)?'flex':'none'})}
function mover(d){i=Math.max(0,Math.min(s.length-1,i+d));ver()}
document.addEventListener('keydown',function(e){
 if(document.activeElement&&document.activeElement.isContentEditable)return;
 if(e.key=='ArrowRight')mover(1); if(e.key=='ArrowLeft')mover(-1);});
ver();
</script></body></html>"""

def limpiar(t):
    return re.sub(r"[()\[\]{}<>&\"'`;:#]", "", t).strip()

def crear_contenido(motor, m):
    tipo, tema, resto = m.group(1), limpiar(m.group(2)), m.group(3)
    es_mapa = "mapa" in tipo
    items = [limpiar(i) for i in re.split(r",|\sy\s", resto)] if resto else []
    items = [i for i in items if i]
    if not items:
        hablar(motor, "Dime los puntos así: crea un mapa de tu tema con punto uno, punto dos y punto tres.")
        return
    art, nombre = ("un", "mapa conceptual") if es_mapa else ("una", "presentación")
    abierto = "abierto" if es_mapa else "abierta"
    if not pedir_permiso(motor, f"Voy a crear {art} {nombre} sobre {tema} y abrirla en tu navegador. "
                                "¿Me das permiso?"):
        hablar(motor, "Entendido, no hice nada.")
        return

    os.makedirs(CREACIONES, exist_ok=True)
    titulo = html.escape(tema.capitalize())
    if es_mapa:
        lineas = ["mindmap", "  root((" + tema + "))"] + ["    " + i for i in items]
        pagina = PLANTILLA_MAPA.replace("__TITULO__", titulo).replace("__MAPA__", "\n".join(lineas))
    else:
        slides = ['<div class="slide" contenteditable="true"><h1>' + titulo +
                  '</h1><p>Presentación creada por Capri</p></div>']
        for i in items:
            slides.append('<div class="slide" contenteditable="true"><h2>' + html.escape(i.capitalize()) +
                          '</h2><p>Haz clic aquí y escribe tu contenido</p></div>')
        pagina = PLANTILLA_PRES.replace("__TITULO__", titulo).replace("__SLIDES__", "\n".join(slides))

    ruta = os.path.join(CREACIONES, datetime.datetime.now().strftime("creacion_%Y%m%d_%H%M%S.html"))
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(pagina)
    webbrowser.open(Path(ruta).as_uri())
    hablar(motor, f"Listo, tu {nombre} está {abierto} en el navegador.")

# ---------------- PÁGINAS WEB ----------------
PREFIJOS_WEB = ("entra a ", "entra en ", "ve a ", "abre la página ", "abre la pagina ",
                "abre página ", "abre pagina ", "abre el sitio ", "abre la web ")

def abrir_web(motor, orden):
    # Devuelve True si abrió la página, False si no te dio permiso
    sitio = orden
    for p in PREFIJOS_WEB:
        if orden.startswith(p):
            sitio = orden[len(p):].strip()
            break
    sitio = re.sub(r"^(de la |del |de )", "", sitio).strip()
    if PEDIR_PERMISO_AL_ABRIR_PAGINAS:
        if not pedir_permiso(motor, f"Voy a abrir {sitio}. ¿Me das permiso?"):
            hablar(motor, "Entendido, no abrí nada.")
            return False
    else:
        hablar(motor, random.choice(INICIO))
    if sitio in SITIOS:
        url = SITIOS[sitio]
    elif " punto " in sitio or "." in sitio:
        url = "https://" + sitio.replace(" punto ", ".").replace(" ", "")
    else:
        url = "https://duckduckgo.com/?q=!ducky+" + urllib.parse.quote_plus(sitio)
    webbrowser.open(url)
    return True

# ---------------- OTRAS ACCIONES ----------------
def abrir_app(nombre):
    nombre = nombre.strip()
    if not nombre:
        return False
    if nombre in SITIOS:
        webbrowser.open(SITIOS[nombre])
        return True
    sistema = platform.system()
    try:
        if sistema == "Windows":
            from AppOpener import open as abrir
            abrir(nombre, match_closest=True, throw_error=False, output=False)
        elif sistema == "Darwin":
            subprocess.Popen(["open", "-a", nombre])
        else:
            subprocess.Popen([nombre])
        return True
    except Exception:
        return False

def leer_portapapeles(motor):
    texto = pyperclip.paste() if pyperclip else ""
    if not texto or not texto.strip():
        hablar(motor, "No hay nada copiado. Selecciona un texto, presiona Control C y vuelve a pedírmelo.")
        return
    hablar(motor, texto.strip()[:600])

def conversar(texto):
  def conversar(texto):
    if cliente is None:
        return random.choice(["Aquí estoy.", "Te escucho.", "Dime."])
    historial.append({"role": "user", "content": texto})
    try:
        r = cliente.chat(model="llama3.2",
                         messages=[{"role": "system", "content": SISTEMA}] + historial[-20:],
                         options={"num_predict": 120})
        respuesta = r["message"]["content"]
    except Exception:
        historial.pop()
        return "No pude conectar con mi cerebro. Revisa que Ollama esté abierto."
    historial.append({"role": "assistant", "content": respuesta})
    guardar_memoria()
    return respuesta

def procesar(motor, orden):
    global salir, estado, SIEMPRE_ESCUCHANDO
    estado = "pensando"
    m_msg = PATRON_MENSAJE.search(orden)
    m_crea = PATRON_CREAR.search(orden)
    if any(p in orden for p in ("apágate", "apagate", "adiós", "adios", "hasta luego")):
        hablar(motor, "Hasta pronto.")
        salir = True
    elif m_msg:
        enviar_mensaje(motor, m_msg)
        hablar(motor, random.choice(MAS))
    elif m_crea:
        crear_contenido(motor, m_crea)
        hablar(motor, random.choice(MAS))
    elif any(p in normalizar(orden) for p in ("escuchame siempre", "modo continuo", "siempre atenta")):
        SIEMPRE_ESCUCHANDO = True
        hablar(motor, "Entendido, ahora te escucho siempre, sin que tengas que llamarme.")
        hablar(motor, random.choice(MAS))
    elif any(p in normalizar(orden) for p in ("modo normal", "solo cuando te llame", "deja de escucharme")):
        SIEMPRE_ESCUCHANDO = False
        hablar(motor, "De acuerdo, volveré a esperar a que me llames.")
        hablar(motor, random.choice(MAS))
    elif "voz" in orden and any(p in orden for p in ("cambia", "cambiar", "otra", "elige", "escoge")):
        cambiar_voz(motor, orden)
        hablar(motor, random.choice(MAS))
    elif "portapapeles" in orden or "lo que copi" in orden:
        leer_portapapeles(motor)
        hablar(motor, random.choice(MAS))
    elif orden.startswith(PREFIJOS_WEB):
        if abrir_web(motor, orden):
            hablar(motor, random.choice(HECHO))
        else:
            hablar(motor, random.choice(MAS))
    elif orden.startswith(("abre ", "abrir ", "ejecuta ", "inicia ")):
        resto = orden.split(" ", 1)[1]
        apps = [a.strip() for a in resto.replace(" y ", ",").split(",")]
        hablar(motor, random.choice(INICIO))
        for a in apps:
            abrir_app(a)
        hablar(motor, random.choice(HECHO))
    elif orden.startswith("busca "):
        consulta = orden[6:].replace("en google", "").strip()
        hablar(motor, random.choice(INICIO))
        webbrowser.open("https://www.google.com/search?q=" + consulta.replace(" ", "+"))
        hablar(motor, random.choice(HECHO))
    elif "respaldo" in orden or "copia de seguridad" in orden:
        hablar(motor, random.choice(INICIO))
        hacer_respaldo()
        hablar(motor, random.choice(HECHO))
    elif "qué hora" in orden or "que hora" in orden:
        hablar(motor, "Son las " + datetime.datetime.now().strftime("%I:%M %p"))
        hablar(motor, random.choice(MAS))
    else:
        hablar(motor, conversar(orden))

# ---------------- OÍDOS (ciclo que nunca se cierra) ----------------
def bucle_escucha():
    global estado, MIC, RECO, despierta_hasta
    motor = crear_motor()
    reconocedor = sr.Recognizer()
    RECO = reconocedor
    hablar(motor, "Hola, soy Capri. Sistemas en línea. ¿En qué te ayudo?")
    despierta_hasta = time.time() + SEGUNDOS_ACTIVA
    try:
        hacer_respaldo()
    except Exception as e:
        print("Respaldo falló:", e)
    with sr.Microphone() as mic:
        MIC = mic
        reconocedor.adjust_for_ambient_noise(mic, duration=1)
        while not salir:
            estado = "escuchando"
            try:
                audio = reconocedor.listen(mic, timeout=5, phrase_time_limit=12)
                resultado = reconocedor.recognize_google(audio, language="es-CO", show_all=True)
                frases = [a["transcript"] for a in resultado.get("alternative", [])] if resultado else []
                if not frases:
                    continue
                print("Escuché:", frases)
                orden = buscar_palabra(frases)
                atenta = SIEMPRE_ESCUCHANDO or time.time() < despierta_hasta
                if orden is None and atenta:
                    orden = frases[0].lower().strip(" ,.")   # no dijo "Capri", pero sigue atenta
                if orden is not None:
                    if orden:
                        procesar(motor, orden)
                    else:
                        hablar(motor, "¿Sí?")
                    despierta_hasta = time.time() + SEGUNDOS_ACTIVA
            except (sr.WaitTimeoutError, sr.UnknownValueError):
                continue
            except Exception as e:
                print("Error:", e)
                estado = "inactivo"
    ventana.after(0, ventana.destroy)

# ---------------- CUERPO ----------------
W, H = 180, 240
CLAVE = "#010101"
COLORES = {"inactivo": "#00e5ff", "escuchando": "#39ff14",
           "pensando": "#ffd600", "hablando": "#ff4081"}

ventana = tk.Tk()
ventana.overrideredirect(True)
ventana.attributes("-topmost", True)
if platform.system() == "Windows":
    ventana.attributes("-transparentcolor", CLAVE)
ventana.config(bg=CLAVE)
lienzo = tk.Canvas(ventana, width=W, height=H, bg=CLAVE, highlightthickness=0)
lienzo.pack()

def buscar_imagen():
    carpeta = os.path.join(CARPETA, "imagen")
    if os.path.isdir(carpeta):
        for f in sorted(os.listdir(carpeta)):
            if f.lower().endswith((".png", ".webp")):
                return os.path.join(carpeta, f)
    return None

sprite = None
ruta_img = buscar_imagen()
if ruta_img and Image is not None:
    try:
        img = Image.open(ruta_img).convert("RGBA")
        img.thumbnail((W - 10, H - 50))
        fondo = Image.new("RGBA", img.size, (1, 1, 1, 255))
        fondo.alpha_composite(img)
        sprite = ImageTk.PhotoImage(fondo.convert("RGB"))
        print("Usando imagen:", ruta_img)
    except Exception as e:
        print("No pude cargar la imagen:", e)

def personaje(color, t, b):
    cx = W // 2
    rosa, oscuro = "#ff2a8a", "#14061f"
    lienzo.create_polygon(cx-60, H-40, cx-48, 150+b, cx-15, 138+b, cx+15, 138+b,
                          cx+48, 150+b, cx+60, H-40, fill=oscuro, outline=color, width=2)
    lienzo.create_line(cx-14, 146+b, cx, 160+b, cx+14, 146+b, fill=color, width=2)
    lienzo.create_rectangle(cx-9, 125+b, cx+9, 142+b, fill="#e8b89c", outline="")
    lienzo.create_oval(cx-48, 28+b, cx+48, 140+b, fill=rosa, outline="")
    lienzo.create_oval(cx-34, 44+b, cx+34, 134+b, fill="#f2c9b0", outline="")
    lienzo.create_arc(cx-40, 32+b, cx+40, 100+b, start=0, extent=180, fill=rosa, outline="")
    lienzo.create_polygon(cx-40, 66+b, cx-6, 50+b, cx-26, 92+b, fill=rosa, outline="")
    lienzo.create_polygon(cx+40, 66+b, cx+6, 50+b, cx+26, 92+b, fill=rosa, outline="")
    lienzo.create_rectangle(cx-32, 78+b, cx+32, 94+b, fill="#0b0b14", outline=color, width=3)
    barrido = cx - 28 + (math.sin(t * 1.5) + 1) / 2 * 50
    lienzo.create_rectangle(barrido, 81+b, barrido+8, 91+b, fill=color, outline="")
    lienzo.create_line(cx+22, 104+b, cx+30, 104+b, cx+32, 112+b, fill=color, width=2)
    lienzo.create_oval(cx+31, 109+b, cx+35, 113+b, fill=color, outline="")
    lienzo.create_oval(cx-42, 88+b, cx-30, 104+b, fill=color, outline="white")
    if estado == "hablando":
        a = 2 + abs(math.sin(t * 4)) * 5
        lienzo.create_oval(cx-8, 110+b, cx+8, 110+b+a*2, fill="#7a1230", outline="")
    else:
        lienzo.create_line(cx-7, 114+b, cx+7, 114+b, fill="#9c4a3a", width=2)

def dibujar(t):
    lienzo.delete("all")
    color = COLORES.get(estado, "#00e5ff")
    b = math.sin(t) * 4
    cx = W // 2
    lienzo.create_oval(cx-55, H-50, cx+55, H-32, outline=color, width=2)
    lienzo.create_oval(cx-35, H-45, cx+35, H-37, outline=color)
    if sprite:
        lienzo.create_image(cx, (H - 40) // 2 + 5 + b, image=sprite)
    else:
        personaje(color, t, b)
    lienzo.create_text(cx, H-14, text="● " + estado.upper(), fill=color,
                       font=("Consolas", 9, "bold"))

ancho, alto = ventana.winfo_screenwidth(), ventana.winfo_screenheight()
x, y = ancho - W - MARGEN_X, alto - H - MARGEN_Y   # esquina de abajo a la derecha
destino = [x, y]
t = 0.0
pausa = 0

def animar():
    global x, y, t, pausa
    t += 0.15
    dibujar(t)
    if MOVERSE:
        if pausa > 0:
            pausa -= 1
        else:
            dx, dy = destino[0] - x, destino[1] - y
            if abs(dx) < 6 and abs(dy) < 6:
                destino[0] = random.randint(0, max(1, ancho - W))
                destino[1] = random.randint(0, max(1, alto - H - 60))
                pausa = random.randint(30, 150)
            else:
                x += dx * 0.03
                y += dy * 0.03
    ventana.geometry(f"{W}x{H}+{int(x)}+{int(y)}")
    ventana.after(33, animar)

def cerrar(_=None):
    global salir
    salir = True
    ventana.destroy()

ventana.bind("<Button-3>", cerrar)
animar()
threading.Thread(target=bucle_escucha, daemon=True).start()
ventana.mainloop()
