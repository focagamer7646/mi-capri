# mi-capri
python
# ============================================================
#  CAPRI - tu asistente de voz con cuerpo cyberpunk
# ============================================================
import os, sys, json, math, random, threading, subprocess, webbrowser, datetime, zipfile, platform
import tkinter as tk
import speech_recognition as sr
import pyttsx3

try:
    from PIL import Image, ImageTk
except Exception:
    Image = ImageTk = None

# Conexión con el cerebro de IA (necesita tu clave de API)
try:
    from anthropic import Anthropic
    cliente = Anthropic()
except Exception:
    cliente = None

CARPETA = os.path.dirname(os.path.abspath(__file__))
MEMORIA = os.path.join(CARPETA, "memoria.json")

# Palabras para despertar a Capri (incluyo variantes por si te entiende mal)
PALABRAS = ("capri", "kapri", "cápri", "capry")

SISTEMA = ("Eres Capri, una asistente de IA con estética cyberpunk. Hablas en español, "
           "con tono cercano, leal y con un toque de humor. Respondes en máximo "
           "2 oraciones cortas porque tu respuesta se dice en voz alta.")

# Páginas que Capri puede abrir por su nombre
SITIOS = {
    "youtube": "https://youtube.com", "google": "https://google.com",
    "gmail": "https://mail.google.com", "instagram": "https://instagram.com",
    "github": "https://github.com", "whatsapp": "https://web.whatsapp.com",
    "spotify": "https://open.spotify.com", "netflix": "https://netflix.com",
}

estado = "inactivo"   # inactivo | escuchando | pensando | hablando
salir = False

# ---------------- MEMORIA (recuerda lo que hablan) ----------------
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

# ---------------- COPIA DE RESPALDO ----------------
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
    for vieja in copias[:-10]:          # guarda solo las últimas 10 copias
        os.remove(os.path.join(destino, vieja))
    return nombre

# ---------------- VOZ (Capri habla) ----------------
def crear_motor():
    motor = pyttsx3.init()
    for v in motor.getProperty("voices"):
        if "spanish" in v.name.lower() or "es-" in v.id.lower() or "sabina" in v.name.lower():
            motor.setProperty("voice", v.id)
            break
    motor.setProperty("rate", 175)
    return motor

def hablar(motor, texto):
    global estado
    print("Capri:", texto)
    estado = "hablando"
    motor.say(texto)
    motor.runAndWait()

# ---------------- ACCIONES ----------------
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

def conversar(texto):
    if cliente is None:
        return random.choice(["Aquí estoy.", "Te escucho.", "Dime."])
    historial.append({"role": "user", "content": texto})
    try:
        r = cliente.messages.create(model="claude-sonnet-5-5", max_tokens=300,
                                    system=SISTEMA, messages=historial[-20:])
        respuesta = r.content[0].text
    except Exception:
        historial.pop()
        return "No pude conectar con mi cerebro. Revisa tu clave de API o tu internet."
    historial.append({"role": "assistant", "content": respuesta})
    guardar_memoria()
    return respuesta

def procesar(motor, orden):
    global salir, estado
    estado = "pensando"
    if any(p in orden for p in ("apágate", "apagate", "adiós", "adios", "hasta luego")):
        hablar(motor, "Hasta pronto.")
        salir = True
    elif orden.startswith(("abre ", "abrir ", "ejecuta ", "inicia ")):
        resto = orden.split(" ", 1)[1]
        apps = [a.strip() for a in resto.replace(" y ", ",").split(",")]
        hablar(motor, "Abriendo " + ", ".join(apps))
        for a in apps:
            abrir_app(a)
    elif orden.startswith("busca "):
        consulta = orden[6:].replace("en google", "").strip()
        webbrowser.open("https://www.google.com/search?q=" + consulta.replace(" ", "+"))
        hablar(motor, "Buscando " + consulta)
    elif "respaldo" in orden or "copia de seguridad" in orden:
        hablar(motor, "Copia creada: " + hacer_respaldo())
    elif "qué hora" in orden or "que hora" in orden:
        hablar(motor, "Son las " + datetime.datetime.now().strftime("%I:%M %p"))
    else:
        hablar(motor, conversar(orden))

# ---------------- OÍDOS (el ciclo que nunca se cierra) ----------------
def bucle_escucha():
    global estado
    motor = crear_motor()
    reconocedor = sr.Recognizer()
    hablar(motor, "Hola, soy Capri. Sistemas en línea. ¿En qué te ayudo?")
    try:
        hacer_respaldo()
    except Exception as e:
        print("Respaldo falló:", e)
    with sr.Microphone() as mic:
        reconocedor.adjust_for_ambient_noise(mic, duration=1)
        while not salir:
            estado = "escuchando"
            try:
                audio = reconocedor.listen(mic, timeout=5, phrase_time_limit=12)
                texto = reconocedor.recognize_google(audio, language="es-CO").lower()
                print("Escuché:", texto)
                encontrada = next((p for p in PALABRAS if p in texto), None)
                if encontrada:
                    orden = texto.split(encontrada, 1)[1].strip(" ,.")
                    if orden:
                        procesar(motor, orden)
                    else:
                        hablar(motor, "¿Sí?")
            except (sr.WaitTimeoutError, sr.UnknownValueError):
                continue
            except Exception as e:      # si algo falla, Capri sigue viva
                print("Error:", e)
                estado = "inactivo"
    ventana.after(0, ventana.destroy)

# ---------------- CUERPO (la figura en tu pantalla) ----------------
W, H = 180, 240
CLAVE = "#010101"   # este color se vuelve transparente en Windows
COLORES = {"inactivo": "#00e5ff", "escuchando": "#39ff14",
           "pensando": "#ffd600", "hablando": "#ff4081"}

ventana = tk.Tk()
ventana.overrideredirect(True)          # sin bordes de ventana
ventana.attributes("-topmost", True)    # siempre encima de todo
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

# Si hay una imagen en la carpeta "imagen", Capri la usa como cuerpo
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
    # Dibuja a Capri con formas (si no hay imagen)
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
    b = math.sin(t) * 4          # sube y baja suavemente (respira)
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
x, y = ancho // 2, alto // 2
destino = [x, y]
t = 0.0
pausa = 0

def animar():
    # Se ejecuta unas 30 veces por segundo: dibuja y mueve a Capri
    global x, y, t, pausa
    t += 0.15
    dibujar(t)
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

ventana.bind("<Button-3>", cerrar)   # clic derecho sobre Capri = cerrarla
animar()
threading.Thread(target=bucle_escucha, daemon=True).start()
ventana.mainloop()
