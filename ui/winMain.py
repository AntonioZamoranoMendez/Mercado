from tkinter import *
import sv_ttk
from models.window import Window
import sys
import os
# --- Archive
from ui.winHelp import WinHelp
# --- Catálogos
from ui.winCameras import WinCameras
# --- Reportes
from ui.winCamerasReport import WinCamerasRep
from ui.winEvenCamRep import WinEventCamRep
# --- Preferencias
from ui.winAbout import WinAbout

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class WinMain(Window):
    def __init__(self):
        super().__init__(title="Mercado")
        sv_ttk.set_theme("dark")
        self.menu = Menu()
        self.archive = Menu(self.menu, tearoff=False)
        self.reports = Menu(self.menu, tearoff=False)
        #self.preferences = Menu(self.menu, tearoff=False)

        self.menu.add_cascade(menu=self.archive, label="Archivo")
        self.menu.add_cascade(menu=self.reports, label="Reportes")
        #self.menu.add_cascade(menu=self.preferences, label="Preferencias")

        self.archive.add_command(label="Ayuda",command=lambda: WinHelp(self))
        self.archive.add_command(label="Salir", command=self.destroy)

        self.reports.add_command(label="Reporte de Cámaras", command=lambda: WinCamerasRep(self))
        self.reports.add_command(label="Reporte de Evento por Cámara", command=lambda: WinEventCamRep(self))

        #self.preferences.add_command(label="Términos y Condiciones")
        #self.preferences.add_command(label="Políticas de Privacidad")
        #self.preferences.add_command(label="Acerca de SISA", command=lambda: WinAbout(self))

        self.config(menu=self.menu)

        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # === Aquí reemplazamos la imagen por el diseño de WinCameras ===
        self.cameras_view = WinCameras(self)
        self.cameras_view.pack(fill=BOTH, expand=True)

        self.focus_force()
        self.mainloop()

    def _on_window_close(self):
            print("[WinMain] Interceptando cierre. Deteniendo hilo de video...")
            try:
                # Llama al método en WinCameras que detiene el hilo
                # de la cámara que se está visualizando.
                self.cameras_view._stop_video_thread()
            except Exception as e:
                print(f"Error al detener hilos de video: {e}")

            # Ahora sí, destruye la ventana principal
            self.destroy()
