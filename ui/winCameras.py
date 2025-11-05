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
import threading

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class WinCameras(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)

        self.db = Database()
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

        self._event_lock = threading.Lock()
        self.last_event_times = {}  # inicializamos aquí para que no haga falta hasattr

        # --- Nuevo botón para subir video desde PC ---
        #self.test_video_button = ttk.Button(button_frame, text="Probar video local", command=self._load_local_video)
        #self.test_video_button.pack(side=tk.RIGHT, padx=5)

        #self.video_paused = False
        #self.video_position = 0
        #self.current_video = None

        # ---------------- Helpers para detección ----------------
    def _extract_boxes(self, results, classes=None, conf_thresh=0.3):
        """
        Extrae boxes en formato [x1,y1,x2,y2,cls,conf] de ultralytics.Results
        - classes: lista de IDs de clases a filtrar (None = todas)
        """
        boxes = []
        try:
            r = results[0]  # results es lista por imagen
            for box in r.boxes:
                xyxy = box.xyxy.cpu().numpy().flatten()[:4].tolist()
                cls = int(box.cls.cpu().numpy().item())
                conf = float(box.conf.cpu().numpy().item())
                if conf < conf_thresh:
                    continue
                if classes is None or cls in classes:
                    boxes.append([xyxy[0], xyxy[1], xyxy[2], xyxy[3], cls, conf])
        except Exception:
            pass
        return boxes

    def _center_from_box(self, box):
        x1, y1, x2, y2 = box[:4]
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def _get_class_index(self, model, target_name):
        """Obtiene el índice de clase según el nombre (p.ej. 'person' o 'forklift')"""
        for idx, name in model.names.items():
            if name.lower() == target_name.lower():
                return int(idx)
        return None

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
        self._shown_event_ids = set()  # Reiniciar eventos mostrados

        # Detener cualquier video activo
        self._stop_video_thread()

        if selected:
            self.edit_button.config(state="normal")
            self.delete_button.config(state="normal")
            name = self.camera_listbox.get(selected[0])
            cam = self.cameras_map[name]
            self.camera_name_label.config(text=f"Cámara: {cam.name}")
            self._start_video_thread(cam)
            self._refresh_events_loop(cam)
        else:
            self.edit_button.config(state="disabled")
            self.delete_button.config(state="disabled")
            self.camera_name_label.config(text="")
            self.events_tree.delete(*self.events_tree.get_children())

    def _start_video_thread(self, camera):
        """Inicia el hilo de video según el tipo de cámara (RTSP o webcam demo)."""
        if self.video_thread:
            self._stop_video_thread()

        self.stop_thread.clear()
        source = camera.get_rtsp_url()
        self.current_camera = camera

        is_webcam = isinstance(source, int) or (str(source).isdigit() and int(source) == 0)
        is_rtsp = str(source).startswith("rtsp://") and not is_webcam

        if is_webcam or is_rtsp:
            self.video_thread = threading.Thread(target=self._video_loop, args=(camera,), daemon=True)
            self.video_thread.start()
        else:
            print(f"[WARN] Fuente desconocida, no se reproduce: {source}")

    def _stop_video_thread(self):
        if self.video_thread and self.video_thread.is_alive():
            self.stop_thread.set()
            self.video_thread.join(timeout=1)

        self.video_thread = None

        # Limpiar la etiqueta de video
        if hasattr(self, "video_label") and self.video_label.winfo_exists():
            self.video_label.config(image=None, text="Seleccione una cámara")
            self.video_label.image = None

    def _on_exit(self):
        self._stop_video_thread()
        if hasattr(self, "video_label") and self.video_label.winfo_exists():
            self.video_label.config(image='', text="Seleccione una cámara")
        if hasattr(self, "camera_name_label") and self.camera_name_label.winfo_exists():
            self.camera_name_label.config(text="")
        self.destroy()

    def _video_loop(self, camera: Camera):
        cap = None
        try:
            rtsp_url = camera.get_rtsp_url()
            self.video_label.after(0, lambda: self.video_label.config(text=f"Conectando a {camera.name}..."))
            cap = cv2.VideoCapture(rtsp_url)
            if not cap.isOpened():
                self.video_label.after(0, lambda: self.video_label.config(text=f"No se pudo conectar a {camera.name}"))
                return

            while not self.stop_thread.is_set():
                ret, frame = cap.read()
                if not ret:
                    break

                # === Detección ===
                results_person = self.yolo_person(frame, verbose=False)
                results_forklift = self.yolo_model(frame, verbose=False)

                # Extraer coordenadas
                # --- Detectar personas ---
                person_idx = self._get_class_index(self.yolo_person, "person")
                persons = self._extract_boxes(results_person, classes=[person_idx] if person_idx is not None else None)

                # --- Detectar montacargas ---
                forklift_idx = self._get_class_index(self.yolo_model, "forklift")
                forklifts = self._extract_boxes(results_forklift, classes=[forklift_idx] if forklift_idx is not None else None)

                def center(box):
                    x1, y1, x2, y2 = box[:4]
                    return ((x1 + x2) / 2, (y1 + y2) / 2)

                # --- Dentro de _video_loop o _start_background_detection ---
                alert_person_near_forklift = False
                for p in persons:
                    cx_p, cy_p = self._center_from_box(p)
                    for f in forklifts:
                        cx_f, cy_f = self._center_from_box(f)
                        dist = ((cx_p - cx_f)**2 + (cy_p - cy_f)**2)**0.5
                        if dist < 120:
                            alert_person_near_forklift = True
                            #cv2.putText(frame, "⚠️ Persona cerca del montacargas!", (30, 50),
                                        #cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

                # === Registrar eventos ===
                if (len(forklifts) > 1 and self._check_forklift_distance([b[:4] for b in forklifts], 120)) or alert_person_near_forklift:
                    description = "⚠️ Dos montacargas demasiado cerca" if len(forklifts) > 1 else "⚠️ Persona cerca del montacargas"
                    self._save_event_frame(camera, frame, description)

                # === Mostrar frame en la interfaz ===
                annotated_frame = results_forklift[0].plot()
                h, w, _ = annotated_frame.shape
                aspect_ratio = w / h
                label_w = self.video_label.winfo_width()
                label_h = self.video_label.winfo_height()
                new_w = label_w
                new_h = int(new_w / aspect_ratio)
                if new_h > label_h:
                    new_h = label_h
                    new_w = int(new_h * aspect_ratio)
                if new_w > 0 and new_h > 0:
                    resized = cv2.resize(annotated_frame, (new_w, new_h))
                    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                    img = ImageTk.PhotoImage(Image.fromarray(rgb))
                    self.video_label.after(0, self._update_video_label, img)

        except Exception as e:
            print(f"Error en hilo de video: {e}")
        finally:
            if cap:
                cap.release()
            if not self.stop_thread.is_set():
                self.video_label.after(0, lambda: self.video_label.config(text=f"Se perdió conexión con {camera.name}"))

    def _update_video_label(self, tk_image):
        if not self.stop_thread.is_set():
            self.video_label.config(image=tk_image, text="")
            self.video_label.image = tk_image

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
        """Guarda un evento con cooldown de 10 s por cámara y lo inserta en la BD."""
        now = time.time()
        if not hasattr(self, "last_event_times"):
            self.last_event_times = {}

        cam_key = getattr(camera, "name", str(camera))
        
        with self._event_lock:  # <--- bloquear aquí
            last_time = self.last_event_times.get(cam_key, 0)
            if now - last_time < 10:  # cooldown 10s
                return
            self.last_event_times[cam_key] = now

        # Guardar imagen
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("event_frames", exist_ok=True)
        filename = f"{cam_key}_event_{timestamp}.jpg"
        path = os.path.join("event_frames", filename)
        cv2.imwrite(path, frame)

        # Guardar en BD
        try:
            ev = Event(
                id=None,
                camera_id=camera.id,
                timestamp=timestamp,
                description=description,
                image_path=path
            )
            event_id = self.db.add_event(ev)

            # Guardar en Treeview con iid = event_id
            self.events_tree.insert("", "end", iid=event_id, values=(timestamp, description))

        except Exception as e:
            print(f"No se pudo guardar evento en BD: {e}")

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
        selected = self.events_tree.selection()
        if not selected:
            return

        event_id = int(selected[0])  # IID del Treeview = event.id
        ev = self.db.get_event_by_id(event_id)
        if not ev:
            messagebox.showerror("Error", "No se encontró el evento en la BD")
            return

        # Obtener cámara para mostrar nombre
        camera = next((cam for cam in self.db.get_all_cameras() if cam.id == ev.camera_id), None)
        cam_name = camera.name if camera else "Desconocida"

        win = tk.Toplevel(self)
        win.title("Detalles del Evento")
        win.geometry("400x400")
        win.resizable(False, False)
        win.grab_set()

        ttk.Label(win, text=f"Cámara: {cam_name}", font=("Helvetica", 12, "bold")).pack(pady=5)
        ttk.Label(win, text=f"Fecha/Hora: {ev.timestamp}", font=("Helvetica", 10)).pack(pady=2)
        ttk.Label(win, text=f"{ev.description}", font=("Helvetica", 10)).pack(pady=2)

        # Mostrar imagen directamente desde el path guardado en BD
        if ev.image_path and os.path.exists(ev.image_path):
            try:
                img = Image.open(ev.image_path)
                img.thumbnail((350, 250))
                tk_img = ImageTk.PhotoImage(img)
                lbl_img = ttk.Label(win, image=tk_img)
                lbl_img.image = tk_img
                lbl_img.pack(pady=10)
            except Exception as e:
                ttk.Label(win, text=f"No se pudo cargar la imagen:\n{e}").pack(pady=10)
        else:
            ttk.Label(win, text="No se encontró la imagen del evento").pack(pady=10)

    def _refresh_events_loop(self, camera: Camera):
        def refresh():
            try:
                events = self.db.get_events_by_camera(camera.id)
                for ev in events:
                    if not self.events_tree.exists(ev.id):  # evita duplicados
                        self.events_tree.insert("", tk.END, iid=ev.id, values=(ev.timestamp, ev.description))
            except Exception as e:
                print(f"Error refrescando eventos: {e}")
            finally:
                # se llama a sí misma cada 5 segundos
                self.after(5000, refresh)

        refresh()  # llamada inicial

    def _start_background_detection(self):
        """Inicia hilos de detección continua para cámaras RTSP (excepto webcam)."""
        def detect_forever(camera: Camera):
            cap = None
            try:
                rtsp_url = camera.get_rtsp_url()
                cap = cv2.VideoCapture(rtsp_url)
                if not cap.isOpened():
                    print(f"[{camera.name}] No se pudo conectar al RTSP")
                    return

                while True:  # bucle infinito (sin depender de la interfaz)
                    ret, frame = cap.read()
                    if not ret:
                        print(f"[{camera.name}] Error de lectura, intentando reconectar...")
                        cap.release()
                        cv2.waitKey(2000)
                        cap = cv2.VideoCapture(rtsp_url)
                        continue

                    # Detección
                    results_person = self.yolo_person(frame, verbose=False)
                    results_forklift = self.yolo_model(frame, verbose=False)

                    # --- Detectar personas ---
                    person_idx = self._get_class_index(self.yolo_person, "person")
                    persons = self._extract_boxes(results_person, classes=[person_idx] if person_idx is not None else None)

                    # --- Detectar montacargas ---
                    forklift_idx = self._get_class_index(self.yolo_model, "forklift")
                    forklifts = self._extract_boxes(results_forklift, classes=[forklift_idx] if forklift_idx is not None else None)

                    def center(box):
                        x1, y1, x2, y2 = box[:4]
                        return ((x1 + x2) / 2, (y1 + y2) / 2)

                    # --- Dentro de _video_loop o _start_background_detection ---
                    alert_person_near_forklift = False
                    for p in persons:
                        cx_p, cy_p = self._center_from_box(p)
                        for f in forklifts:
                            cx_f, cy_f = self._center_from_box(f)
                            dist = ((cx_p - cx_f)**2 + (cy_p - cy_f)**2)**0.5
                            if dist < 120:
                                alert_person_near_forklift = True
                                #cv2.putText(frame, "⚠️ Persona cerca del montacargas!", (30, 50),
                                            #cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

                    # Guardar evento solo si hay al menos 1 montacargas
                    if len(forklifts) > 0:
                        if len(forklifts) > 1 and self._check_forklift_distance([b[0][:4] for b in forklifts], 120):
                            description = "⚠️ Dos montacargas demasiado cerca"
                            self._save_event_frame(camera, frame, description)
                        elif alert_person_near_forklift:
                            description = "⚠️ Persona cerca del montacargas"
                            self._save_event_frame(camera, frame, description)

                    cv2.waitKey(10)  # pequeña pausa para no saturar CPU

            except Exception as e:
                print(f"[{camera.name}] Error en detección en segundo plano: {e}")
            finally:
                if cap:
                    cap.release()

        # Crear un hilo por cámara RTSP
        # Crear un hilo por cámara RTSP (omitimos webcams locales)
        cameras = self.db.get_all_cameras()
        
        def is_local_camera(cam: Camera) -> bool:
            """Determina si una cámara es local (webcam o dispositivo sin IP)."""
            if not cam.ip:
                return True
            # si el campo IP es "0", "1", "2", "localhost", o el nombre es 'webcam'
            if cam.ip.strip() in ["0", "1", "2", "localhost"] or cam.name.lower() in ["webcam", "camara local"]:
                return True
            return False
        
        for cam in cameras:
            if is_local_camera(cam):
                print(f"⛔ Cámara local omitida: {cam.name} ({cam.ip})")
                continue
            threading.Thread(target=detect_forever, args=(cam,), daemon=True).start()
        
        print(f"[INFO] Detección en segundo plano iniciada para {len(cameras)} cámaras RTSP (sin incluir webcams)")
        

        print(f"[INFO] Detección en segundo plano iniciada para {len(cameras)} cámaras RTSP")
