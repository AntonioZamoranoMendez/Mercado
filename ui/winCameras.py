# --- winCameras.py ---
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import cv2
from PIL import Image, ImageTk
from ultralytics import YOLO
import sys, os, uuid
import glob
import os
from tkinter import filedialog
from models.camera import Camera
from database.database import Database
from models.event import Event
import math
import time
from datetime import datetime

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_storage_path():
    '''
    Retorna la ruta: C:/Users/Usuario/Documents/SistemaVigilancia
    Crea la carpeta si no existe.
    '''
    # Obtiene la ruta a "Mis Documentos" de forma universal
    user_docs = os.path.join(os.path.expanduser("~"), "Documents")
    # Define el nombre de tu carpeta principal
    app_folder = os.path.join(user_docs, "SistemaVigilancia")
    # Crea la carpeta si no existe
    if not os.path.exists(app_folder):
        os.makedirs(app_folder)
    return app_folder

class WinCameras(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)
        self.storage_dir = get_storage_path()
        print(f"[SISTEMA] Guardando datos en: {self.storage_dir}")
        self.current_stream_id = 0
        db_path = os.path.join(self.storage_dir, "vigilancia_data.db")

        self.db = Database(db_path)
        self.cameras_map = {}
        self.video_thread = None
        self.stop_thread = threading.Event()
        self.yolo_model = None
        self._shown_event_ids = set()  # Guardar eventos ya mostrados

        try:
            self.yolo_model = YOLO(resource_path('models/best.pt'))
            self.yolo_person = YOLO("yolov8n.pt")  # Detecta personas
        except Exception as e:
            messagebox.showerror("Error de Modelo", f"No se pudo cargar el modelo YOLO 'models/best.pt' o bien, 'yolov8n.pt'.\n{e}")
            return

        # === Layout principal ===
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        main_frame.columnconfigure(0, weight=2)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # Panel izquierdo (video)
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=(0, 0))

        self.camera_name_label = ttk.Label(left_frame, text="", font=("Helvetica", 12, "bold"))
        self.camera_name_label.pack(fill=tk.X, pady=(0, 5))

        self.video_label = ttk.Label(
            left_frame,
            text="Seleccione una cámara",
            font=("Helvetica", 14),
            anchor="center",
            background="black",
            foreground="white"
        )
        self.video_label.pack(fill=tk.BOTH, expand=True)

        # Panel derecho (lista de cámaras + eventos)
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky="nsew", pady=(0, 0))
        right_frame.rowconfigure(1, weight=1)

        ttk.Label(right_frame, text="Cámaras", font=("Helvetica", 12, "bold")).pack(pady=5)
        self.camera_listbox = tk.Listbox(right_frame, exportselection=False)
        self.camera_listbox.pack(fill=tk.X, padx=5)
        self.camera_listbox.bind("<<ListboxSelect>>", self._on_camera_select)

        ttk.Label(right_frame, text="Eventos", font=("Helvetica", 12, "bold")).pack(pady=5)
        columns = ("timestamp", "description")
        self.events_tree = ttk.Treeview(right_frame, columns=columns, show="headings")
        self.events_tree.heading("timestamp", text="Fecha/Hora")
        self.events_tree.heading("description", text="Descripción")
        self.events_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.events_tree.bind("<Configure>", self._adjust_event_columns)
        self.events_tree.bind("<<TreeviewSelect>>", self._on_event_select)

        # Botones inferiores
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
        self.add_button = ttk.Button(button_frame, text="Agregar", command=self._show_add_edit_window)
        self.add_button.pack(side=tk.LEFT, padx=5)
        self.edit_button = ttk.Button(button_frame, text="Editar", state="disabled",
                                    command=lambda: self._show_add_edit_window(edit_mode=True))
        self.edit_button.pack(side=tk.LEFT, padx=5)
        self.delete_button = ttk.Button(button_frame, text="Eliminar", state="disabled", command=self._delete_camera)
        self.delete_button.pack(side=tk.LEFT, padx=5)

        # Llenar lista inicial
        self._populate_camera_list()
        self._start_background_detection()

    # --- winCameras.py ---
    def _on_exit(self):
        # 🔹 Detener cualquier hilo activo de video
        self._stop_video_thread()

        # 🔹 Limpiar el contenido del video
        if hasattr(self, "video_label") and self.video_label.winfo_exists():
            self.video_label.config(image='', text="Selecciona una cámara o video")

        # 🔹 Limpiar etiquetas de título o cámara
        if hasattr(self, "camera_name_label") and self.camera_name_label.winfo_exists():
            self.camera_name_label.config(text="")
        if hasattr(self, "video_title_label") and self.video_title_label.winfo_exists():
            self.video_title_label.config(text="")

        # 🔹 Quitar los controles del video si existen
        if hasattr(self, "video_controls_frame") and self.video_controls_frame.winfo_exists():
            self.video_controls_frame.destroy()

        # 🔹 Finalmente destruir la ventana
        self.destroy()

    def _populate_camera_list(self):
        self._stop_video_thread()
        self.camera_listbox.delete(0, tk.END)
        self.cameras_map.clear()
        cameras = self.db.get_all_cameras()
        for cam in cameras:
            self.camera_listbox.insert(tk.END, cam.name)
            self.cameras_map[cam.name] = cam
        self._on_camera_select(None)

    def _on_camera_select(self, event):
        selected = self.camera_listbox.curselection()
        self._stop_video_thread()

        if selected:
            self.edit_button.config(state="normal")
            self.delete_button.config(state="normal")
            name = self.camera_listbox.get(selected[0])
            cam = self.cameras_map[name]

            self.current_camera = cam
            self.events_tree.delete(*self.events_tree.get_children())

            self.camera_name_label.config(text=f"Cámara: {cam.name}")

            self._start_video_thread(cam)
            self._refresh_events_loop(cam) # Esto cargará el historial

        else:
            self.current_camera = None
            self.edit_button.config(state="disabled")
            self.delete_button.config(state="disabled")
            self.camera_name_label.config(text="")
            self.events_tree.delete(*self.events_tree.get_children())

    def _start_video_thread(self, camera):
        """Inicia el hilo de video para visualización en pantalla principal."""
        # Si hay un hilo de video activo, detenerlo primero
        if self.video_thread:
            self._stop_video_thread()

        self.stop_thread.clear()
        self.current_camera = camera
        self.current_stream_id += 1
        stream_id = self.current_stream_id

        if camera.ip.strip() == "0":
                source = 0
        else:
            source = camera.get_rtsp_url()

        print(f"[INFO] Conectando a cámara: {camera.name} ({source})")

        # Destruir controles viejos si existen (limpieza)
        if hasattr(self, "video_controls_frame") and self.video_controls_frame.winfo_exists():
            self.video_controls_frame.destroy()

        self.video_thread = threading.Thread(
            target=self._video_loop, 
            args=(camera, stream_id), 
            daemon=True
        )
        self.video_thread.start()

    def _stop_video_thread(self):
        if self.video_thread and self.video_thread.is_alive():
            self.stop_thread.set()
            self.video_thread.join(timeout=1)

        self.video_thread = None
        self.current_video = None
        
        # Limpiar la etiqueta de video de forma segura
        if hasattr(self, "video_label") and self.video_label.winfo_exists():
            try:
                self.video_label.config(image='', text="Seleccione una cámara")
                self.video_label.image = None
            except Exception as e:
                print(f"Advertencia al limpiar video: {e}")

        if hasattr(self, "video_controls_frame") and self.video_controls_frame.winfo_exists():
            self.video_controls_frame.destroy()

        # Limpiar la etiqueta de video
        if hasattr(self, "video_label") and self.video_label.winfo_exists():
            self.video_label.config(image=None, text="Seleccione una cámara")
            self.video_label.image = None

        if hasattr(self, "video_controls_frame") and self.video_controls_frame.winfo_exists():
            self.video_controls_frame.destroy()

    def _video_loop(self, camera, stream_id):
        cap = None
        try:
            if stream_id != self.current_stream_id: return
            src = 0 if camera.ip.strip() == "0" else camera.get_rtsp_url()
            
            if stream_id == self.current_stream_id:
                self.video_label.after(0, lambda: self.video_label.config(text=f"Conectando {camera.name}..."))
            
            cap = cv2.VideoCapture(src)
            if not cap.isOpened():
                if stream_id == self.current_stream_id:
                    self.video_label.after(0, lambda: self.video_label.config(text="Error Conexión"))
                return

            # === VARIABLES PARA OPTIMIZACIÓN ===
            frame_count = 0
            SKIP_FRAMES = 10  # Detectar cada 10 frames (3 detect/seg aprox en 30fps)
            
            # Guardamos las detecciones para pintarlas en los frames que saltamos
            cached_persons = [] 
            cached_forklifts = []
            # ===================================

            while not self.stop_thread.is_set():
                if stream_id != self.current_stream_id: break
                ret, frame = cap.read()
                if not ret: break

                frame_count += 1

                # --- DETECCIÓN (Solo 1 de cada 10 frames) ---
                if frame_count % SKIP_FRAMES == 0:
                    
                    # 1. Reducir tamaño solo para la IA (Más rápido)
                    frame_small = cv2.resize(frame, (640, int(frame.shape[0]*(640/frame.shape[1]))))
                    
                    # 2. Inferir
                    res_p = self.yolo_person(frame_small, verbose=False)
                    res_f = self.yolo_model(frame_small, verbose=False, conf=0.5)
                    
                    # 3. Calcular escala para adaptar cajas al tamaño real
                    scale_x = frame.shape[1] / 640
                    scale_y = frame.shape[0] / frame_small.shape[0]

                    # 4. Limpiar y actualizar caché de detecciones
                    cached_persons = []
                    for box in res_p[0].boxes:
                        if int(box.cls[0]) == 0:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            # Guardamos coords reales
                            cached_persons.append([x1*scale_x, y1*scale_y, x2*scale_x, y2*scale_y])

                    cached_forklifts = []
                    for box in res_f[0].boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        # Guardamos coords reales
                        cached_forklifts.append([x1*scale_x, y1*scale_y, x2*scale_x, y2*scale_y])

                    # 5. Lógica de Alerta (Solo se calcula cuando detectamos)
                    alert = False
                    def get_center(b): return ((b[0]+b[2])/2, (b[1]+b[3])/2)
                    
                    for p in cached_persons:
                        cp = get_center(p)
                        for f in cached_forklifts:
                            cf = get_center(f)
                            if math.dist(cp, cf) < 120: alert = True
                    
                    if (len(cached_forklifts) > 1 and self._check_forklift_dist(cached_forklifts)) or alert:
                        msg = "⚠️ Choque Montacargas" if len(cached_forklifts)>1 else "⚠️ Persona en Riesgo"
                        # Guardamos el frame ORIGINAL actual
                        self._save_event_frame(camera, frame, msg)

                # --- DIBUJADO (En TODOS los frames usando caché) ---
                # Usamos las listas 'cached_' que contienen la info del último frame detectado
                for f in cached_forklifts:
                    cv2.rectangle(frame, (int(f[0]), int(f[1])), (int(f[2]), int(f[3])), (255,0,0), 2)
                for p in cached_persons:
                    cv2.rectangle(frame, (int(p[0]), int(p[1])), (int(p[2]), int(p[3])), (0,255,0), 2)

                # --- UI UPDATE (En TODOS los frames para video fluido) ---
                if stream_id != self.current_stream_id: break
                if self.video_label.winfo_exists():
                    lw, lh = self.video_label.winfo_width(), self.video_label.winfo_height()
                    if lw > 1 and lh > 1:
                        scale = min(lw/frame.shape[1], lh/frame.shape[0])
                        nw, nh = int(frame.shape[1]*scale), int(frame.shape[0]*scale)
                        if nw>0 and nh>0:
                            resized = cv2.resize(frame, (nw, nh))
                            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                            
                            pil_img = Image.fromarray(rgb)
                            self.video_label.after(0, self._update_video_label, pil_img, stream_id)

        except Exception as e: print(f"Video Error: {e}")
        finally: 
            if cap: cap.release()

    def _update_video_label(self, pil_image, stream_id):
        # Protección contra condición de carrera
        if stream_id != self.current_stream_id:
            return

        if not self.stop_thread.is_set():
            try:
                tk_image = ImageTk.PhotoImage(pil_image)
                
                self.video_label.config(image=tk_image, text="")
                self.video_label.image = tk_image # Referencia para evitar Garbage Collection
            except Exception as e:
                print(f"Error actualizando frame: {e}")

    def _check_forklift_distance(self, boxes, min_distance_px=100):
        """
        Verifica si hay dos montacargas demasiado cerca según sus cajas detectadas.
        boxes: lista de coordenadas [x1, y1, x2, y2]
        Retorna True si hay al menos un par demasiado cerca.
        """
        centers = []
        for b in boxes:
            x1, y1, x2, y2 = b
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            centers.append((cx, cy))

        # Comparar distancias entre todos los pares
        for i in range(len(centers)):
            for j in range(i + 1, len(centers)):
                x1, y1 = centers[i]
                x2, y2 = centers[j]
                distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                if distance < min_distance_px:
                    return True  # dos montacargas demasiado cerca
        return False

    def _save_event_frame(self, camera, frame, description):
        """Guarda un evento en disco Y en la base de datos con cooldown."""
        now = time.time()

        # Asegurar que existe el diccionario de tiempos por cámara
        if not hasattr(self, "last_event_times"):
            self.last_event_times = {}

        # Obtener clave única para el cooldown
        cam_key = getattr(camera, "name", str(camera))

        # Cooldown de 10 segundos
        last_time = self.last_event_times.get(cam_key, 0)
        if now - last_time < 10:
            return
        self.last_event_times[cam_key] = now

        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        safe_cam_name = "".join(c for c in cam_key if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
        filename = f"{safe_cam_name}_{filename_ts}.jpg"

        # 1. Guardar archivo en Documentos
        frames_folder = os.path.join(self.storage_dir, "event_frames")
        os.makedirs(frames_folder, exist_ok=True)
        path = os.path.join(frames_folder, filename)

        cv2.imwrite(path, frame)
        print(f"[EVENTO] Imagen guardada en: {path}")

        # 2. Guardar en Base de Datos y Actualizar UI
        if hasattr(camera, 'id') and camera.id is not None:
            try:
                # Crear objeto evento
                new_event = Event(
                    camera_id=camera.id,
                    timestamp=timestamp_str,
                    description=description,
                    image_path=path
                )

                # Guardar en DB (Esto sí se puede hacer en el hilo)
                event_id = self.db.add_event(new_event)

                # 3. Actualizar la Interfaz DE FORMA SEGURA
                # Usamos self.after para que la inserción ocurra en el hilo principal
                if self.current_camera and self.current_camera.id == camera.id:
                    self.after(0, lambda: self._safe_tree_insert(event_id, timestamp_str, description))

            except Exception as e:
                print(f"[ERROR DB] No se pudo guardar evento: {e}")

    def _safe_tree_insert(self, event_id, timestamp, description):
        """Función auxiliar para insertar en el Treeview desde el hilo principal."""
        try:
            if not self.events_tree.exists(event_id):
                self.events_tree.insert("", 0, iid=event_id, values=(timestamp, description))
        except Exception as e:
            print(f"Error UI Treeview: {e}")

    def _delete_camera(self):
        selected = self.camera_listbox.curselection()
        if not selected:
            return
        name = self.camera_listbox.get(selected[0])
        camera = self.cameras_map[name]
        if messagebox.askyesno("Confirmar", f"¿Está seguro de eliminar la cámara {name}?"):
            try:
                self.db.delete_camera(camera.id)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo eliminar la cámara {name}.\n{e}")
                return
            self._populate_camera_list()

    def _show_add_edit_window(self, edit_mode=False):
        """Muestra ventana para agregar o editar una cámara."""
        selected_cam = None
        if edit_mode:
            selected_indices = self.camera_listbox.curselection()
            if not selected_indices:
                return
            selected_name = self.camera_listbox.get(selected_indices[0])
            selected_cam = self.cameras_map[selected_name]

        win = tk.Toplevel(self)
        win.title("Editar Cámara" if edit_mode else "Agregar Cámara")
        win.grab_set()
        form_frame = ttk.Frame(win, padding=20)
        form_frame.pack(expand=True, fill=tk.BOTH)

        fields = ["Nombre", "IP", "Usuario", "Contraseña", "Puerto"]
        entries = {}

        for i, field in enumerate(fields):
            ttk.Label(form_frame, text=f"{field}:").grid(row=i, column=0, sticky="w", pady=2, padx=5)
            entry = ttk.Entry(form_frame, width=40)
            entry.grid(row=i, column=1, sticky="ew", pady=2, padx=5)
            entries[field] = entry

        if edit_mode and selected_cam:
            entries["Nombre"].insert(0, selected_cam.name)
            entries["IP"].insert(0, selected_cam.ip)
            entries["Usuario"].insert(0, selected_cam.username)
            entries["Contraseña"].insert(0, selected_cam.password)
            entries["Puerto"].insert(0, str(selected_cam.port))

        def on_save():
            try:
                name = entries["Nombre"].get()
                ip = entries["IP"].get()
                user = entries["Usuario"].get()
                pwd = entries["Contraseña"].get()
                port = int(entries["Puerto"].get())

                if not all([name, ip, user]):
                    tk.messagebox.showerror("Error", "Nombre, IP y Usuario son obligatorios.", parent=win)
                    return

                new_cam = Camera(
                    id=selected_cam.id if edit_mode else None,
                    name=name, ip=ip, username=user, password=pwd, port=port
                )

                if edit_mode:
                    self.db.update_camera(new_cam)
                else:
                    self.db.add_camera(new_cam)

                self._populate_camera_list()
                win.destroy()

            except ValueError:
                tk.messagebox.showerror("Error", "El puerto debe ser un número.", parent=win)
            except Exception as e:
                tk.messagebox.showerror("Error", f"No se pudo guardar la cámara.\n{e}", parent=win)

        save_button = ttk.Button(form_frame, text="Guardar", command=on_save)
        save_button.grid(row=len(fields), columnspan=2, pady=10)

    def _adjust_event_columns(self, event):
        if self.events_tree.winfo_width() > 0:
            self.events_tree.column("timestamp", width=int(self.events_tree.winfo_width() * 0.4))
            self.events_tree.column("description", width=int(self.events_tree.winfo_width() * 0.6))

    def _on_event_select(self, event):
        """Muestra la imagen del evento seleccionado consultando la BD."""
        selected = self.events_tree.selection()
        if not selected:
            return

        # El IID en el Treeview es el ID del evento en la Base de Datos
        event_id_str = selected[0]
        
        # Validar si es un ID de base de datos (número entero)
        if not str(event_id_str).isdigit():
            messagebox.showinfo("Info", "Este evento es de una sesión local y no tiene imagen persistente.")
            return

        event_id = int(event_id_str)

        # --- RECUPERAR RUTA DESDE LA BD ---
        event_obj = self.db.get_event_by_id(event_id)
        
        if not event_obj:
            messagebox.showerror("Error", "No se encontró el evento en la base de datos.")
            return

        img_path = event_obj.image_path
        timestamp = event_obj.timestamp
        description = event_obj.description

        # Crear ventana emergente
        win = tk.Toplevel(self)
        win.title("Detalles del Evento")
        # win.geometry("400x450") # Opcional: dejar que se ajuste sola
        win.grab_set()

        ttk.Label(win, text=f"Fecha: {timestamp}", font=("Helvetica", 10, "bold")).pack(pady=(10, 2))
        ttk.Label(win, text=f"Evento: {description}", font=("Helvetica", 10)).pack(pady=2)
        ttk.Label(win, text=f"Ruta: {img_path}", font=("Arial", 8), foreground="gray").pack(pady=2)

        # Cargar imagen
        if img_path and os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                # Redimensionar manteniendo proporción para que quepa en ventana
                img.thumbnail((400, 300)) 
                tk_img = ImageTk.PhotoImage(img)
                
                lbl_img = ttk.Label(win, image=tk_img)
                lbl_img.image = tk_img  # Referencia para evitar garbage collection
                lbl_img.pack(pady=10, padx=10)
            except Exception as e:
                ttk.Label(win, text=f"Error al abrir imagen:\n{e}", foreground="red").pack(pady=10)
        else:
            ttk.Label(win, text="❌ Archivo de imagen no encontrado en disco", foreground="red").pack(pady=20)

    def _refresh_events_loop(self, camera: Camera):
        """Carga eventos históricos y busca nuevos periódicamente."""
        def refresh():
            # 1. Verificar si el usuario sigue viendo ESTA cámara
            if self.current_camera is None or self.current_camera.id != camera.id:
                return # Si cambió de cámara, matamos este bucle

            try:
                # 2. Obtener eventos (Vienen ordenados: Nuevo -> Viejo)
                events = self.db.get_events_by_camera(camera.id)
                
                for ev in events:
                    # 3. Solo insertar si no existe en la lista
                    if not self.events_tree.exists(ev.id):
                        self.events_tree.insert("", tk.END, iid=ev.id, values=(ev.timestamp, ev.description))
            
            except Exception as e:
                print(f"Error refresh: {e}")
            finally:
                # 4. Repetir cada 3 segundos si seguimos en la misma cámara
                if self.current_camera and self.current_camera.id == camera.id:
                    self.after(3000, refresh)

        refresh() # Llamada inmediata inicial

    def _start_background_detection(self):
        """Inicia detección en segundo plano optimizada para ALTA CARGA (10+ cámaras)."""
        import random # Necesario para evitar picos de CPU

        def detect_forever(camera: Camera):
            # Retraso inicial aleatorio para que no arranquen las 10 hilos a la vez
            time.sleep(random.uniform(0.5, 5.0))
            
            cap = None
            rtsp_url = camera.get_rtsp_url()
            
            # Intentar conectar
            try:
                cap = cv2.VideoCapture(rtsp_url)
            except:
                pass # Se manejará en el bucle

            print(f"[HILO] Iniciado monitor para: {camera.name}")

            while True:
                # 1. PAUSA: Análisis cada 1.5 segundos para 10 cámaras (Ajustable)
                # Si tu PC es muy potente, puedes bajarlo a 1.0 o 0.5
                time.sleep(1.5) 

                try:
                    # 2. RECONEXIÓN ROBUSTA
                    if cap is None or not cap.isOpened():
                        cap = cv2.VideoCapture(rtsp_url)
                        if not cap.isOpened():
                            time.sleep(2) # Esperar antes de reintentar
                            continue
                    
                    # 3. LIMPIEZA DE BUFFER (Truco RTSP)
                    # Leemos y descartamos frames viejos acumulados durante el sleep
                    for _ in range(4):
                        cap.grab() 
                    
                    # Leemos el frame real
                    ret, frame = cap.read()
                    if not ret:
                        print(f"[{camera.name}] Señal perdida. Reconectando...")
                        cap.release()
                        cap = None
                        continue

                    # 4. OPTIMIZACIÓN CRÍTICA: Redimensionar
                    # Procesar 1080p x 10 cámaras mata la CPU. Usamos 640px.
                    # YOLO funciona excelente con 640x640 o similar.
                    h, w = frame.shape[:2]
                    scale = 640 / w
                    new_h = int(h * scale)
                    frame_small = cv2.resize(frame, (640, new_h))

                    # --- Detección sobre frame_small (Más rápido) ---
                    results_person = self.yolo_person(frame_small, verbose=False)
                    # Usamos conf=0.55 para ser más estrictos en background
                    results_forklift = self.yolo_model(frame_small, verbose=False, conf=0.55)

                    persons = [b.xyxy.cpu().numpy() for b in results_person[0].boxes if int(b.cls[0]) == 0]
                    forklifts = [b.xyxy.cpu().numpy() for b in results_forklift[0].boxes]

                    # Función center ajustada al frame pequeño
                    def center(box):
                        x1, y1, x2, y2 = box[:4]
                        return ((x1 + x2) / 2, (y1 + y2) / 2)

                    # Verificar cercanía
                    # Nota: Como redimensionamos la imagen, la distancia en píxeles cambia.
                    # 120px en 1080p es aprox 40px en 640p. Ajustamos el umbral a 45.
                    umbral_distancia = 45 
                    
                    alert_person_near_forklift = False
                    for p in persons:
                        cx_p, cy_p = center(p[0])
                        for f in forklifts:
                            cx_f, cy_f = center(f[0])
                            dist = ((cx_p - cx_f) ** 2 + (cy_p - cy_f) ** 2) ** 0.5
                            if dist < umbral_distancia:
                                alert_person_near_forklift = True

                    # --- Guardar evento ---
                    if (len(forklifts) > 1 and self._check_forklift_distance([b[0][:4] for b in forklifts], umbral_distancia)) or alert_person_near_forklift:
                        description = "⚠️ Dos montacargas cerca" if len(forklifts) > 1 else "⚠️ Persona cerca de maquina"
                        # Importante: Guardamos el frame ORIGINAL (alta calidad), no el pequeño
                        self._save_event_frame(camera, frame, description)

                except Exception as e:
                    # Evitar que un error en una cámara detenga el hilo
                    print(f"Error en hilo {camera.name}: {e}")
                    time.sleep(1)

        # --- Lanzar hilos ---
        cameras = self.db.get_all_cameras()
        
        def is_local_camera(cam: Camera) -> bool:
            if not cam.ip: return True
            if cam.ip.strip() in ["0", "1", "2", "localhost"] or "webcam" in cam.name.lower():
                return True
            return False
        
        count = 0
        for cam in cameras:
            if is_local_camera(cam):
                continue
            # Daemon=True asegura que los hilos mueran al cerrar la app
            threading.Thread(target=detect_forever, args=(cam,), daemon=True).start()
            count += 1
        
        print(f"[SISTEMA] Vigilancia activa en {count} cámaras (Modo Ahorro CPU activado)")