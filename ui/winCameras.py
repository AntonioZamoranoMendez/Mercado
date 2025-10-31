import tkinter as tk
from tkinter import ttk, messagebox
import threading
import cv2
from PIL import Image, ImageTk
from ultralytics import YOLO
import sys
import os
import datetime
import uuid

from models.camera import Camera
from database.database import Database
from models.event import Event

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class WinCameras(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Administrador de Cámaras")
        self.geometry("1280x720")
        self.grab_set()

        self.db = Database()
        self.cameras_map = {}
        self.video_thread = None
        self.stop_thread = threading.Event()
        self.yolo_model = None

        try:
            self.yolo_model = YOLO(resource_path('models/best.pt'))
        except Exception as e:
            messagebox.showerror("Error de Modelo", f"No se pudo cargar el modelo YOLO 'models/best.pt'.\n{e}")
            self.destroy()
            return

        # Layout principal
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        main_frame.columnconfigure(0, weight=2)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # Panel izquierdo (video)
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0,5))
        self.video_label = ttk.Label(left_frame, text="Seleccione una cámara", font=("Helvetica", 14),
        anchor="center", background="black", foreground="white")
        self.video_label.pack(fill=tk.BOTH, expand=True)

        # Panel derecho (cámaras y eventos)
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky="nsew")

        # Lista de cámaras
        ttk.Label(right_frame, text="Cámaras", font=("Helvetica", 12, "bold")).pack(pady=5)
        self.camera_listbox = tk.Listbox(right_frame, exportselection=False)
        self.camera_listbox.pack(fill=tk.X, padx=5)
        self.camera_listbox.bind("<<ListboxSelect>>", self._on_camera_select)

        # Tabla de eventos
        ttk.Label(right_frame, text="Eventos", font=("Helvetica", 12, "bold")).pack(pady=5)
        columns = ("timestamp", "description")
        self.events_tree = ttk.Treeview(right_frame, columns=columns, show="headings", height=20)
        self.events_tree.heading("timestamp", text="Fecha/Hora")
        self.events_tree.heading("description", text="Descripción")
        self.events_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Botones
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
        self.add_button = ttk.Button(button_frame, text="Agregar", command=self._show_add_edit_window)
        self.add_button.pack(side=tk.LEFT, padx=5)
        self.edit_button = ttk.Button(button_frame, text="Editar", state="disabled",
        command=lambda: self._show_add_edit_window(edit_mode=True))
        self.edit_button.pack(side=tk.LEFT, padx=5)
        self.delete_button = ttk.Button(button_frame, text="Eliminar", state="disabled", command=self._delete_camera)
        self.delete_button.pack(side=tk.LEFT, padx=5)
        self.exit_button = ttk.Button(button_frame, text="Salir", command=self.close_window)
        self.exit_button.pack(side=tk.RIGHT, padx=5)

        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self._populate_camera_list()

    def close_window(self):
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
        if selected:
            self.edit_button.config(state="normal")
            self.delete_button.config(state="normal")
            name = self.camera_listbox.get(selected[0])
            cam = self.cameras_map[name]
            self._start_video_thread(cam)
            self._populate_events(cam)
        else:
            self.edit_button.config(state="disabled")
            self.delete_button.config(state="disabled")
            self._stop_video_thread()
            self.events_tree.delete(*self.events_tree.get_children())

    def _populate_events(self, camera):
        self.events_tree.delete(*self.events_tree.get_children())
        events = self.db.get_events_by_camera(camera.id)
        for ev in events:
            self.events_tree.insert("", tk.END, values=(ev.timestamp, ev.description))

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

    # Los métodos _delete_camera y _show_add_edit_window se mantienen iguales a tu código original
    # Igual con _save_event y _save_event_video si los necesitas
    
    # ...existing code...

    def save_camera(self, camera):
        """Guarda una nueva cámara o actualiza una existente"""
        # Por ahora solo guardamos en memoria
        self.cameras = getattr(self, 'cameras', [])
        # Verificar si ya existe
        for i, existing in enumerate(self.cameras):
            if existing.id == camera.id:
                self.cameras[i] = camera
                return
        # Si no existe, agregar nueva
        self.cameras.append(camera)

    def get_all_cameras(self):
        """Retorna todas las cámaras"""
        return getattr(self, 'cameras', [])

# ...existing code...

    def _delete_camera(self):
        selected = self.camera_listbox.curselection()
        if not selected:
            return
            
        name = self.camera_listbox.get(selected[0])
        camera = self.cameras_map[name]
        
        if messagebox.askyesno("Confirmar", f"¿Está seguro de eliminar la cámara {name}?"):
            try:
                self.db.delete_camera(camera.id)
                self._populate_camera_list()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo eliminar la cámara: {str(e)}")

    def _show_add_edit_window(self, edit_mode=False):
        dialog = tk.Toplevel(self)
        dialog.title("Editar Cámara" if edit_mode else "Agregar Cámara")
        dialog.geometry("400x350")
        dialog.grab_set()

        # Frame principal
        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Campos del formulario
        ttk.Label(main_frame, text="Nombre:").grid(row=0, column=0, sticky="w", pady=5)
        name_entry = ttk.Entry(main_frame, width=30)
        name_entry.grid(row=0, column=1, pady=5)

        ttk.Label(main_frame, text="Tipo:").grid(row=1, column=0, sticky="w", pady=5)
        camera_type = tk.StringVar(value="webcam")
        ttk.Radiobutton(main_frame, text="Webcam", variable=camera_type, 
                       value="webcam").grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(main_frame, text="IP Camera", variable=camera_type, 
                       value="ip").grid(row=2, column=1, sticky="w")

        # Frame para cámara IP
        ip_frame = ttk.LabelFrame(main_frame, text="Configuración IP", padding="5")
        ip_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=10)

        ttk.Label(ip_frame, text="IP:").grid(row=0, column=0, sticky="w")
        ip_entry = ttk.Entry(ip_frame, width=15)
        ip_entry.grid(row=0, column=1, padx=5)

        ttk.Label(ip_frame, text="Puerto:").grid(row=0, column=2, sticky="w")
        port_entry = ttk.Entry(ip_frame, width=6)
        port_entry.grid(row=0, column=3)

        ttk.Label(ip_frame, text="Usuario:").grid(row=1, column=0, sticky="w", pady=5)
        user_entry = ttk.Entry(ip_frame)
        user_entry.grid(row=1, column=1, columnspan=3, sticky="ew", pady=5)

        ttk.Label(ip_frame, text="Contraseña:").grid(row=2, column=0, sticky="w")
        pass_entry = ttk.Entry(ip_frame, show="*")
        pass_entry.grid(row=2, column=1, columnspan=3, sticky="ew")

        def update_fields(*args):
            state = "disabled" if camera_type.get() == "webcam" else "normal"
            for widget in [ip_entry, port_entry, user_entry, pass_entry]:
                widget.config(state=state)

        camera_type.trace("w", update_fields)
        update_fields()

        # Cargar datos si es modo edición
        if edit_mode:
            selected = self.camera_listbox.curselection()
            if selected:
                camera = self.cameras_map[self.camera_listbox.get(selected[0])]
                name_entry.insert(0, camera.name)
                if camera.url != "0":
                    camera_type.set("ip")
                    try:
                        # Parsear URL RTSP
                        if camera.url.startswith("rtsp://"):
                            url_parts = camera.url.replace("rtsp://", "").split("@")
                            if len(url_parts) == 2:
                                creds, addr = url_parts
                                user, pwd = creds.split(":")
                                ip, port = addr.split(":")[0], addr.split(":")[1].split("/")[0]
                                
                                user_entry.insert(0, user)
                                pass_entry.insert(0, pwd)
                                ip_entry.insert(0, ip)
                                port_entry.insert(0, port)
                    except:
                        pass

        def save_camera():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Error", "El nombre es obligatorio")
                return

            # Crear URL según el tipo de cámara
            if camera_type.get() == "webcam":
                url = "0"  # Webcam local
            else:
                # Validar campos obligatorios para cámara IP
                if not all([ip_entry.get(), port_entry.get()]):
                    messagebox.showerror("Error", "IP y puerto son obligatorios para cámaras IP")
                    return
                
                # Construir URL RTSP
                auth = f"{user_entry.get()}:{pass_entry.get()}@" if user_entry.get() else ""
                url = f"rtsp://{auth}{ip_entry.get()}:{port_entry.get()}/stream1"

            # Crear o actualizar cámara
            camera = Camera(
                id=str(uuid.uuid4()) if not edit_mode else self.cameras_map[self.camera_listbox.get(selected[0])].id,
                name=name,
                url=url
            )

            try:
                self.db.save_camera(camera)
                self._populate_camera_list()
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo guardar la cámara: {str(e)}")

        # Botones
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="Guardar", command=save_camera).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT)