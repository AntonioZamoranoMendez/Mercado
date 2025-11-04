# --- winCameras.py ---
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import cv2
from PIL import Image, ImageTk
from ultralytics import YOLO
import sys, os, datetime, uuid
import glob
import os
from tkinter import filedialog
from models.camera import Camera
from database.database import Database
from models.event import Event
import math

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
        except Exception as e:
            messagebox.showerror("Error de Modelo", f"No se pudo cargar el modelo YOLO 'models/best.pt'.\n{e}")
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

        # --- Nuevo botón para subir video desde PC ---
        self.test_video_button = ttk.Button(button_frame, text="Probar video local", command=self._load_local_video)
        self.test_video_button.pack(side=tk.RIGHT, padx=5)

    def _load_local_video(self):
        """Permite seleccionar un archivo de video y mostrar detecciones con YOLO."""
        file_path = filedialog.askopenfilename(
            title="Seleccionar video",
            filetypes=[("Archivos de video", "*.mp4 *.avi *.mov *.mkv")]
        )
        if not file_path:
            return

        self._stop_video_thread()  # Detiene cualquier cámara activa
        self.camera_name_label.config(text=f"Video local: {os.path.basename(file_path)}")

        self.stop_thread.clear()
        self.video_thread = threading.Thread(target=self._process_local_video, args=(file_path,), daemon=True)
        self.video_thread.start()

    def _process_local_video(self, file_path):
        """Procesa un video local usando el modelo YOLO."""
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            self.video_label.after(0, lambda: self.video_label.config(text="No se pudo abrir el video"))
            return

        while not self.stop_thread.is_set():
            ret, frame = cap.read()
            if not ret:
                break  # fin del video

            results = self.yolo_model(frame, verbose=False)
            annotated_frame = results[0].plot()

            # Redimensionar y mostrar
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

            if results[0].boxes and len(results[0].boxes) > 1:  # al menos 2 montacargas
                # Obtener coordenadas de las cajas
                boxes = results[0].boxes.xyxy.cpu().numpy()  # cada fila: [x1, y1, x2, y2, conf, cls]
                coords = [b[:4] for b in boxes]

                if self._check_forklift_distance(coords, min_distance_px=120):
                    description = "⚠️ Dos montacargas demasiado cerca"
                    self._save_event_frame(
                            Camera(id="local", name="VideoLocal", ip="", username="", password="", port=0), frame, description
                        )



        cap.release()
        self.video_label.after(0, lambda: self.video_label.config(text="Fin del video local"))

    def _on_exit(self):
        self._stop_video_thread()
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
        self._shown_event_ids = set()  # Reiniciar eventos mostrados al cambiar de cámara

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
            self._stop_video_thread()
            self.events_tree.delete(*self.events_tree.get_children())

    def _start_video_thread(self, camera):
        if self.video_thread:
            self._stop_video_thread()
        self.stop_thread.clear()
        self.video_thread = threading.Thread(target=self._video_loop, args=(camera,), daemon=True)
        self.video_thread.start()

    def _stop_video_thread(self):
        if self.video_thread and self.video_thread.is_alive():
            self.stop_thread.set()
            self.video_thread.join(timeout=1)
        self.video_thread = None
        self.video_label.config(image=None, text="Seleccione una cámara")
        self.video_label.image = None

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
                results = self.yolo_model(frame, verbose=False)
                if results[0].boxes and len(results[0].boxes) > 1:  # al menos 2 montacargas
                    # Obtener coordenadas de las cajas
                    boxes = results[0].boxes.xyxy.cpu().numpy()  # cada fila: [x1, y1, x2, y2, conf, cls]
                    coords = [b[:4] for b in boxes]

                    if self._check_forklift_distance(coords, min_distance_px=120):
                        description = "⚠️ Dos montacargas demasiado cerca"
                        self._save_event_frame(camera, frame, description)


                annotated_frame = results[0].plot()
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

    def _save_event_frame(self, camera: Camera, frame, description="Objeto detectado"):
        os.makedirs("events_images", exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{camera.name}_{timestamp}.jpg"
        path = os.path.join("events_images", filename)
    
        try:
            cv2.imwrite(path, frame)
            event = Event(
                id=str(uuid.uuid4()),
                camera_id=camera.id,
                timestamp=timestamp,
                description=description,
                image_path=path
            )
            self.db.add_event(event)  # <-- CORREGIDO
            return event
        except Exception as e:
            print(f"No se pudo guardar el evento: {e}")
            return None

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

        event_id = selected[0]  # IID del Treeview, que es ev.id
        values = self.events_tree.item(event_id, "values")
        timestamp, description = values

        # También necesitamos el nombre de la cámara
        selected_cam_index = self.camera_listbox.curselection()
        if not selected_cam_index:
            return
        cam_name = self.camera_listbox.get(selected_cam_index[0])

        win = tk.Toplevel(self)
        win.title("Detalles del Evento")
        win.geometry("400x400")
        win.resizable(False, False)
        win.grab_set()

        ttk.Label(win, text=f"Cámara: {cam_name}", font=("Helvetica", 12, "bold")).pack(pady=5)
        ttk.Label(win, text=f"Fecha/Hora: {timestamp}", font=("Helvetica", 10)).pack(pady=2)
        ttk.Label(win, text=f"Descripción: {description}", font=("Helvetica", 10)).pack(pady=2)

        # Buscar archivo en events_images/
        pattern = f"events_images/{cam_name}_{timestamp}*.jpg"
        files = glob.glob(pattern)
        if files:
            img_path = files[0]  # tomar el primero que coincida
            try:
                img = Image.open(img_path)
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
